from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.core.database import get_supabase_client, db


async def cleanup_old_alerts() -> None:
    """Delete alerts past the retention window and expired analysis cache."""
    try:
        retention_days = get_settings().alerts_retention_days

        supabase = get_supabase_client()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()

        # Delete old alerts
        await db(supabase.table("alerts").delete().lt("sent_at", cutoff))

        # Delete expired cache entries
        now = datetime.now(timezone.utc).isoformat()
        await db(supabase.table("analysis_cache").delete().lt("expires_at", now))

        print(f"Cleanup complete: removed alerts older than {retention_days} days")

    except Exception as e:
        print(f"Cleanup error: {e}")
