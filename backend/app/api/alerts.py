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
