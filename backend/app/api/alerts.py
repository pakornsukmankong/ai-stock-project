from fastapi import APIRouter, HTTPException, Depends
from app.core.database import get_supabase_client
from app.core.auth import get_current_user_id

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/")
async def get_alerts(
    page: int = 1,
    per_page: int = 20,
    user_id: str = Depends(get_current_user_id),
):
    """Get paginated alert history for a user.

    Args:
        page: Page number (1-based, default 1)
        per_page: Items per page (default 20, max 100)
    """
    try:
        supabase = get_supabase_client()

        # Clamp per_page
        per_page = max(1, min(per_page, 100))
        offset = (page - 1) * per_page

        # Get total count
        count_response = (
            supabase.table("alerts")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .execute()
        )
        total = count_response.count or 0

        # Get paginated data
        response = (
            supabase.table("alerts")
            .select("*")
            .eq("user_id", user_id)
            .order("sent_at", desc=True)
            .range(offset, offset + per_page - 1)
            .execute()
        )

        total_pages = (total + per_page - 1) // per_page if total > 0 else 1

        return {
            "alerts": response.data,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
            },
        }

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
async def get_performance_stats(
    page: int = 1,
    per_page: int = 20,
    user_id: str = Depends(get_current_user_id),
):
    """Get paginated performance statistics for user's alerts."""
    try:
        supabase = get_supabase_client()

        per_page = max(1, min(per_page, 100))
        offset = (page - 1) * per_page

        # Get total count of BUY alerts with price
        count_response = (
            supabase.table("alerts")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .eq("signal_type", "BUY")
            .not_.is_("alert_price", "null")
            .execute()
        )
        total = count_response.count or 0

        # Get paginated data
        response = (
            supabase.table("alerts")
            .select("stock_symbol, alert_price, price_after_1d, price_after_3d, price_after_7d, return_1d, return_3d, return_7d, is_successful, sent_at, confidence")
            .eq("user_id", user_id)
            .eq("signal_type", "BUY")
            .not_.is_("alert_price", "null")
            .order("sent_at", desc=True)
            .range(offset, offset + per_page - 1)
            .execute()
        )

        alerts_data = response.data

        # Calculate overall stats (from all data, not just current page)
        all_response = (
            supabase.table("alerts")
            .select("is_successful, return_7d")
            .eq("user_id", user_id)
            .eq("signal_type", "BUY")
            .not_.is_("alert_price", "null")
            .execute()
        )
        all_data = all_response.data

        tracked = [a for a in all_data if a.get("is_successful") is not None]
        successful = [a for a in tracked if a["is_successful"]]
        win_rate = (len(successful) / len(tracked) * 100) if tracked else 0

        avg_return_7d = 0
        returns_7d = [a["return_7d"] for a in all_data if a.get("return_7d") is not None]
        if returns_7d:
            avg_return_7d = sum(returns_7d) / len(returns_7d)

        total_pages = (total + per_page - 1) // per_page if total > 0 else 1

        return {
            "total_alerts": total,
            "tracked": len(tracked),
            "successful": len(successful),
            "win_rate": round(win_rate, 1),
            "avg_return_7d": round(avg_return_7d, 2),
            "alerts": alerts_data,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
            },
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


@router.delete("/performance/clear")
async def clear_performance_data(user_id: str = Depends(get_current_user_id)):
    """Clear all performance tracking alerts (BUY signals with price data) for the user."""
    try:
        supabase = get_supabase_client()

        # Delete all BUY alerts that have alert_price (performance tracked ones)
        supabase.table("alerts").delete().eq(
            "user_id", user_id
        ).eq(
            "signal_type", "BUY"
        ).not_.is_(
            "alert_price", "null"
        ).execute()

        return {"message": "Performance tracking data cleared successfully"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
