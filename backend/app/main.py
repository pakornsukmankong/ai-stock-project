from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from app.api import user, watchlist, alerts, analysis, market, search, line_webhook
from app.services.scheduler import get_analysis_scheduler
from app.services.daily_briefing import DailyBriefingService
from app.services.performance_tracker import PerformanceTracker
from app.services.cleanup import cleanup_old_alerts
from app.core.config import get_settings
from app.core.http_client import close_http_client
from app.core.scheduler_instance import scheduler
from app.core.rate_limiter import api_limiter, trigger_limiter
from app.core.error_monitor import monitor


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle - start/stop scheduler."""
    settings = get_settings()

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
            # Daily briefing: runs at 8:30 AM ET (12:30 UTC) every weekday
            daily_briefing = DailyBriefingService()
            scheduler.add_job(
                daily_briefing.send_daily_briefings,
                "cron",
                hour=12,
                minute=30,
                day_of_week="mon-fri",
                id="daily_briefing",
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
            print("Daily briefing: runs at 8:30 AM ET (Mon-Fri)")
        except Exception as e:
            monitor.log_error("startup", f"Scheduler failed to start: {e}")
            print(f"Warning: Scheduler failed to start: {e}")
    else:
        print("Warning: Supabase not configured. Scheduler disabled.")

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
