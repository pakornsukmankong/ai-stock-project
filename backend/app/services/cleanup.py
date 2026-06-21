from datetime import datetime, timedelta, timezone
from app.core.database import get_supabase_client

ALERTS_RETENTION_DAYS = 30


async def cleanup_old_alerts() -> None:
    """Delete alerts older than 30 days and expired analysis cache."""
    try:
        supabase = get_supabase_client()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=ALERTS_RETENTION_DAYS)).isoformat()

        # Delete old alerts
        supabase.table("alerts").delete().lt("sent_at", cutoff).execute()

        # Delete expired cache entries
        now = datetime.now(timezone.utc).isoformat()
        supabase.table("analysis_cache").delete().lt("expires_at", now).execute()

        print(f"Cleanup complete: removed alerts older than {ALERTS_RETENTION_DAYS} days")

    except Exception as e:
        print(f"Cleanup error: {e}")
