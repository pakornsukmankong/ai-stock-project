from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from app.api import user, watchlist, alerts, analysis, market, search
from app.services.scheduler import AnalysisScheduler
from app.services.cleanup import cleanup_old_alerts
from app.core.config import get_settings
from app.core.scheduler_instance import scheduler
from app.core.rate_limiter import api_limiter
from app.core.error_monitor import monitor


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle - start/stop scheduler."""
    settings = get_settings()

    # Only start scheduler if Supabase is configured
    if settings.supabase_url and settings.supabase_service_role_key:
        try:
            analysis_scheduler = AnalysisScheduler()
            scheduler.add_job(
                analysis_scheduler.run_analysis_cycle,
                "interval",
                minutes=settings.analysis_interval_minutes,
                id="stock_analysis",
                replace_existing=True,
            )
            scheduler.add_job(
                cleanup_old_alerts,
                "interval",
                hours=6,
                id="cleanup_old_alerts",
                replace_existing=True,
            )
            scheduler.add_job(
                api_limiter.cleanup,
                "interval",
                minutes=5,
                id="rate_limiter_cleanup",
                replace_existing=True,
            )
            scheduler.start()
            monitor.set_scheduler_running(True)
            print(f"Scheduler started: running every {settings.analysis_interval_minutes} minutes")
            print("Cleanup job: runs every 6 hours (retention: 7 days)")
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


app = FastAPI(
    title="AI Stock Alert API",
    description="AI-assisted stock alert platform with LINE notifications",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://*.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Rate limiting middleware
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Apply rate limiting to all API requests."""
    # Skip rate limiting for health check and docs
    if request.url.path in ("/", "/health", "/docs", "/openapi.json"):
        return await call_next(request)

    try:
        api_limiter.check(request)
    except Exception as e:
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests. Please try again later."},
            headers={"Retry-After": "60"},
        )

    return await call_next(request)


# Register routers
app.include_router(user.router, prefix="/api/v1")
app.include_router(watchlist.router, prefix="/api/v1")
app.include_router(alerts.router, prefix="/api/v1")
app.include_router(analysis.router, prefix="/api/v1")
app.include_router(market.router, prefix="/api/v1")
app.include_router(search.router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"message": "AI Stock Alert API", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    """Health check with system status."""
    health = monitor.get_health()
    status_code = 200 if health["status"] in ("healthy", "degraded") else 503
    return JSONResponse(content=health, status_code=status_code)
