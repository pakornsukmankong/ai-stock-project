"""LINE account-linking codes.

A user proves ownership of a LINE identity by sending a short code (shown in the
web app) to the Official Account. The webhook then knows which web user the
inbound `userId` belongs to. Codes are single-use and short-lived.
"""
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.config import get_settings
from app.core.database import get_supabase_client, db

# Unambiguous alphabet: no 0/O, 1/I/L — the code is read off a screen and typed
# into a phone, so lookalikes cause failed links.
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 6

# What counts as a code when parsing an inbound chat message.
CODE_PATTERN = re.compile(rf"^[{_ALPHABET}]{{{CODE_LENGTH}}}$")

_MAX_ALLOC_ATTEMPTS = 5


def generate_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(CODE_LENGTH))


def normalize_code(text: str) -> str:
    """Uppercase and strip whitespace so 'ab cd ef' / 'abcdef' both match."""
    return re.sub(r"\s+", "", (text or "")).upper()


def looks_like_code(text: str) -> bool:
    return bool(CODE_PATTERN.match(normalize_code(text)))


async def create_link_code(user_id: str) -> dict:
    """Create (or replace) the active linking code for a user.

    Returns {"code", "expires_at"}. One code per user — regenerating overwrites
    the previous one (UPSERT on user_id). Retries if the random code collides
    with another user's active code (UNIQUE(code)).
    """
    settings = get_settings()
    supabase = get_supabase_client()
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.line_link_code_ttl_minutes
    )

    last_error: Optional[Exception] = None
    for _ in range(_MAX_ALLOC_ATTEMPTS):
        code = generate_code()
        try:
            await db(
                supabase.table("line_link_codes").upsert(
                    {
                        "user_id": user_id,
                        "code": code,
                        "expires_at": expires_at.isoformat(),
                    },
                    on_conflict="user_id",
                )
            )
            return {"code": code, "expires_at": expires_at.isoformat()}
        except Exception as e:  # noqa: BLE001 - inspect message to decide retry
            last_error = e
            msg = str(e).lower()
            if "duplicate" in msg or "unique" in msg or "conflict" in msg:
                continue  # code collided with another user's — try a new one
            raise

    raise RuntimeError(f"Could not allocate a unique link code: {last_error}")


async def consume_link_code(code: str) -> Optional[str]:
    """Redeem a code: return the owning user_id and delete it (single-use).

    Returns None if the code is unknown or expired. The row is deleted whether
    or not it was still valid, so an expired code cannot be retried.
    """
    supabase = get_supabase_client()
    normalized = normalize_code(code)

    resp = await db(
        supabase.table("line_link_codes")
        .select("user_id, expires_at")
        .eq("code", normalized)
        .limit(1)
    )
    if not resp.data:
        return None

    row = resp.data[0]
    await db(supabase.table("line_link_codes").delete().eq("code", normalized))

    if _parse_ts(row["expires_at"]) < datetime.now(timezone.utc):
        return None
    return row["user_id"]


async def delete_expired_codes() -> int:
    """Delete codes past their expiry. Returns the number removed."""
    supabase = get_supabase_client()
    now_iso = datetime.now(timezone.utc).isoformat()
    resp = await db(
        supabase.table("line_link_codes").delete().lt("expires_at", now_iso)
    )
    return len(resp.data or [])


def _parse_ts(value: str) -> datetime:
    """Parse a Postgres timestamptz string into an aware UTC datetime."""
    text = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
