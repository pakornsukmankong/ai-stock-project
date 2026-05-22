from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
from app.services.scheduler import AnalysisScheduler
from app.services.market_hours import get_market_status
from app.core.scheduler_instance import scheduler as app_scheduler
from app.core.error_monitor import monitor
from app.core.auth import get_current_user_id

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("/trigger")
async def trigger_analysis(user_id: str = Depends(get_current_user_id)):
    """Manually trigger an analysis cycle (requires auth)."""
    try:
        analysis_scheduler = AnalysisScheduler()
        await analysis_scheduler.run_analysis_cycle()
        return {"message": "Analysis cycle completed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_analysis_status(user_id: str = Depends(get_current_user_id)):
    """Get current analysis scheduler status with real job info."""
    is_running = app_scheduler.running
    market = get_market_status()

    jobs = []
    if is_running:
        for job in app_scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "interval": str(job.trigger),
            })

    return {
        "scheduler_running": is_running,
        "market": market,
        "jobs": jobs,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health")
async def get_system_health(user_id: str = Depends(get_current_user_id)):
    """Get detailed system health and error info (requires auth)."""
    return {
        "health": monitor.get_health(),
        "recent_errors": monitor.get_recent_errors(limit=10),
    }
