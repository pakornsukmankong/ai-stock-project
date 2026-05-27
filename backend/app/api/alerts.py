from fastapi import APIRouter, HTTPException, Depends
from app.core.database import get_supabase_client
from app.core.auth import get_current_user_id

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/")
async def get_alerts(limit: int = 20, offset: int = 0, user_id: str = Depends(get_current_user_id)):
    """Get alert history for a user."""
    try:
        supabase = get_supabase_client()

        response = (
            supabase.table("alerts")
            .select("*")
            .eq("user_id", user_id)
            .order("sent_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )

        return {"alerts": response.data, "total": len(response.data)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_alert_stats(user_id: str = Depends(get_current_user_id)):
    """Get alert statistics for today."""
    try:
        supabase = get_supabase_client()
        from datetime import datetime, timezone

        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0).isoformat()

        response = (
            supabase.table("alerts")
            .select("id")
            .eq("user_id", user_id)
            .gte("sent_at", today_start)
            .execute()
        )

        return {"signals_today": len(response.data)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance")
async def get_performance_stats(user_id: str = Depends(get_current_user_id)):
    """Get performance statistics for user's alerts."""
    try:
        supabase = get_supabase_client()

        response = (
            supabase.table("alerts")
            .select("stock_symbol, alert_price, price_after_1d, price_after_3d, price_after_7d, return_1d, return_3d, return_7d, is_successful, sent_at, confidence")
            .eq("user_id", user_id)
            .eq("signal_type", "BUY")
            .not_.is_("alert_price", "null")
            .order("sent_at", desc=True)
            .limit(50)
            .execute()
        )

        alerts_data = response.data

        # Calculate overall stats
        tracked = [a for a in alerts_data if a.get("is_successful") is not None]
        successful = [a for a in tracked if a["is_successful"]]
        win_rate = (len(successful) / len(tracked) * 100) if tracked else 0

        avg_return_7d = 0
        returns_7d = [a["return_7d"] for a in alerts_data if a.get("return_7d") is not None]
        if returns_7d:
            avg_return_7d = sum(returns_7d) / len(returns_7d)

        return {
            "total_alerts": len(alerts_data),
            "tracked": len(tracked),
            "successful": len(successful),
            "win_rate": round(win_rate, 1),
            "avg_return_7d": round(avg_return_7d, 2),
            "alerts": alerts_data,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recent")
async def get_recent_alerts(user_id: str = Depends(get_current_user_id)):
    """Get the 5 most recent alerts for a user."""
    try:
        supabase = get_supabase_client()

        response = (
            supabase.table("alerts")
            .select("*")
            .eq("user_id", user_id)
            .order("sent_at", desc=True)
            .limit(5)
            .execute()
        )

        return {"alerts": response.data}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
