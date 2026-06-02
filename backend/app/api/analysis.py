from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
from app.services.scheduler import AnalysisScheduler
from app.services.mtf_engine import MTFEngine
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


@router.get("/mtf/{symbol}")
async def get_mtf_analysis(symbol: str, user_id: str = Depends(get_current_user_id)):
    """Get multi-timeframe analysis for a specific stock symbol.

    Returns trend/momentum/MACD state for Daily, 4H, and 1H timeframes,
    along with confluence scoring.
    """
    try:
        mtf_engine = MTFEngine()
        result = await mtf_engine.analyze(symbol.upper())

        # Build response
        timeframes = {}
        for tf_name, tf_data in [
            ("daily", result.daily),
            ("4h", result.four_hour),
            ("1h", result.one_hour),
        ]:
            if tf_data.is_valid and tf_data.indicators:
                timeframes[tf_name] = {
                    "is_valid": True,
                    "trend_direction": tf_data.trend_direction,
                    "momentum_state": tf_data.momentum_state,
                    "macd_state": tf_data.macd_state,
                    "rsi": round(tf_data.indicators.rsi, 1),
                    "ema_9": round(tf_data.indicators.ema_9, 2),
                    "ema_21": round(tf_data.indicators.ema_21, 2),
                    "supertrend": tf_data.indicators.supertrend_direction,
                    "macd_histogram": round(tf_data.indicators.macd_histogram, 4),
                }
            else:
                timeframes[tf_name] = {
                    "is_valid": False,
                    "trend_direction": "unknown",
                    "momentum_state": "unknown",
                    "macd_state": "unknown",
                }

        return {
            "symbol": symbol.upper(),
            "timeframes": timeframes,
            "confluence": {
                "trend_alignment": result.trend_alignment,
                "momentum_alignment": result.momentum_alignment,
                "bonus_score": result.mtf_bonus_score,
                "penalty_score": result.mtf_penalty_score,
                "reasons": result.confluence_reasons,
                "is_aligned_bullish": result.is_aligned_bullish,
                "has_divergence": result.has_divergence,
            },
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MTF analysis failed: {str(e)}")
