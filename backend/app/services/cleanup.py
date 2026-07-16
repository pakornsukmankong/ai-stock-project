import logging
from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.core.database import get_supabase_client, db
from app.services.line_linking import delete_expired_codes

logger = logging.getLogger(__name__)


async def cleanup_old_alerts() -> None:
    """Delete alerts past the retention window, expired cache, and stale codes."""
    try:
        retention_days = get_settings().alerts_retention_days

        supabase = get_supabase_client()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()

        # Delete old alerts
        await db(supabase.table("alerts").delete().lt("sent_at", cutoff))

        # Delete expired cache entries
        now = datetime.now(timezone.utc).isoformat()
        await db(supabase.table("analysis_cache").delete().lt("expires_at", now))

        # Delete expired LINE linking codes
        await delete_expired_codes()

        print(f"Cleanup complete: removed alerts older than {retention_days} days")

    except Exception as e:
        logger.error(f"Cleanup error: {e}")
