import logging
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from app.api import user, watchlist, alerts, analysis, market, search, line_webhook
from app.services.scheduler import get_analysis_scheduler
from app.services.daily_briefing import DailyBriefingService
from app.services.performance_tracker import PerformanceTracker
from app.services.cleanup import cleanup_old_alerts
from app.services.ai_health import check_openai_model_access
from app.services.markets import US_MARKET, SET_MARKET
from app.core.config import get_settings
from app.core.http_client import close_http_client
from app.core.logging_config import adopt_uvicorn_loggers
from app.core.scheduler_instance import scheduler
from app.core.rate_limiter import api_limiter, trigger_limiter
from app.core.error_monitor import monitor

logger = logging.getLogger(__name__)

# At import, not in the lifespan: uvicorn configures its loggers in Config(),
# then imports this module, and only *then* logs "Started server process" /
# "Waiting for application startup." before handing over to the lifespan. Doing
# this any later leaves those first lines on stderr, reported as errors.
adopt_uvicorn_loggers()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle - start/stop scheduler."""
    settings = get_settings()

    # Again for the programmatic path (uvicorn.run(app)), where the app object is
    # imported *before* Config() re-installs uvicorn's own handlers. Idempotent.
    adopt_uvicorn_loggers()

    # Verify the configured AI model is reachable, so a bad/unentitled
    # OPENAI_MODEL surfaces at boot instead of failing silently every cycle.
    ok, message = await check_openai_model_access()
    if ok:
        print(f"OpenAI model check: OK — {message}")
    else:
        monitor.log_error("startup", f"OpenAI model check failed: {message}")
        print(f"⚠️  OpenAI model check: {message}")

    # Only start scheduler if Supabase is configured
    if settings.supabase_url and settings.supabase_service_role_key:
        try:
            analysis_scheduler = get_analysis_scheduler()
            scheduler.add_job(
                analysis_scheduler.run_analysis_cycle,
                "interval",
                minutes=settings.analysis_interval_minutes,
                id="stock_analysis",
                replace_existing=True,
                # A slow cycle must never stack up behind itself.
                max_instances=1,
                coalesce=True,
            )
            scheduler.add_job(
                cleanup_old_alerts,
                "interval",
                hours=6,
                id="cleanup_old_alerts",
                replace_existing=True,
            )
            # Daily briefing: one pre-open run per market (schedules are UTC).
            daily_briefing = DailyBriefingService()
            # US: 8:30 AM ET ≈ 12:30 UTC (1h before the 9:30 ET open).
            scheduler.add_job(
                daily_briefing.send_daily_briefings,
                "cron",
                hour=12,
                minute=30,
                day_of_week="mon-fri",
                args=[US_MARKET],
                id="daily_briefing_us",
                replace_existing=True,
            )
            # SET: 9:00 AM ICT = 02:00 UTC (1h before the 10:00 ICT open; ICT has
            # no DST, so this is exact year-round).
            scheduler.add_job(
                daily_briefing.send_daily_briefings,
                "cron",
                hour=2,
                minute=0,
                day_of_week="mon-fri",
                args=[SET_MARKET],
                id="daily_briefing_set",
                replace_existing=True,
            )
            # Performance tracker: runs at 10:00 PM ET (02:00 UTC) every weekday
            perf_tracker = PerformanceTracker()
            scheduler.add_job(
                perf_tracker.update_performance,
                "cron",
                hour=2,
                minute=0,
                day_of_week="mon-fri",
                id="performance_tracker",
                replace_existing=True,
            )
            scheduler.add_job(
                _cleanup_rate_limiters,
                "interval",
                minutes=5,
                id="rate_limiter_cleanup",
                replace_existing=True,
            )
            scheduler.start()
            monitor.set_scheduler_running(True)
            print(f"Scheduler started: running every {settings.analysis_interval_minutes} minutes")
            print(
                f"Cleanup job: runs every 6 hours "
                f"(retention: {settings.alerts_retention_days} days)"
            )
            print("Daily briefing: US 12:30 UTC & SET 02:00 UTC (Mon-Fri)")
        except Exception as e:
            monitor.log_error("startup", f"Scheduler failed to start: {e}")
            logger.error(f"Scheduler failed to start: {e}")
    else:
        logger.warning("Supabase not configured. Scheduler disabled.")

    yield

    # Shutdown
    if scheduler.running:
        scheduler.shutdown()
        monitor.set_scheduler_running(False)
        print("Scheduler stopped")

    await close_http_client()


def _cleanup_rate_limiters() -> None:
    api_limiter.cleanup()
    trigger_limiter.cleanup()


settings = get_settings()

app = FastAPI(
    title="AI Stock Alert API",
    description="AI-assisted stock alert platform with LINE notifications",
    version="1.0.0",
    lifespan=lifespan,
    # Don't publish the full API surface in production.
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
    ],
    # Match this project's Vercel deployments (production + previews).
    # CORSMiddleware does exact-string matching on allow_origins, so a literal
    # "https://*.vercel.app" entry never matches — a regex is required. The regex
    # must stay narrow: a blanket `https://.*\.vercel\.app` would let ANY site
    # deployed on Vercel (i.e. anyone) make credentialed calls to this API.
    allow_origin_regex=settings.cors_allow_origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# Rate limiting middleware
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Apply rate limiting to all API requests."""
    # Skip rate limiting for health check and docs
    if request.url.path in ("/", "/health", "/docs", "/redoc", "/openapi.json"):
        return await call_next(request)

    # The LINE webhook is authenticated by request signature and called by LINE's
    # servers (a small set of source IPs). IP-based throttling would drop
    # legitimate event bursts, so it is exempt — the signature check is the gate.
    if request.url.path == "/api/v1/webhook/line":
        return await call_next(request)

    # Preflight requests carry no credentials and must not be throttled, or the
    # browser reports a CORS failure instead of a 429.
    if request.method == "OPTIONS":
        return await call_next(request)

    try:
        api_limiter.check(request)
    except HTTPException as e:
        return JSONResponse(
            status_code=e.status_code,
            content={"detail": e.detail},
            headers=e.headers or {"Retry-After": "60"},
        )

    return await call_next(request)


# Register routers
app.include_router(user.router, prefix="/api/v1")
app.include_router(watchlist.router, prefix="/api/v1")
app.include_router(alerts.router, prefix="/api/v1")
app.include_router(analysis.router, prefix="/api/v1")
app.include_router(market.router, prefix="/api/v1")
app.include_router(search.router, prefix="/api/v1")
app.include_router(line_webhook.router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"message": "AI Stock Alert API", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    """Health check with system status."""
    health = monitor.get_health()
    status_code = 200 if health["status"] in ("healthy", "degraded") else 503
    return JSONResponse(content=health, status_code=status_code)
