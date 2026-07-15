"""LINE Messaging API webhook.

Receives events from the Official Account. Its one job today is account
linking: when a user sends their linking code, match it to a web user and store
that user's LINE `userId` so alerts can be pushed to them.

Security: every request is authenticated by the `X-Line-Signature` header, an
HMAC-SHA256 of the *raw* request body keyed with the channel secret. No JWT is
involved (LINE's servers call this), so the signature is the only trust anchor —
requests that fail it are rejected before anything is parsed.
"""
import base64
import hashlib
import hmac
import json

from fastapi import APIRouter, HTTPException, Request

from app.core.config import get_settings
from app.core.database import get_supabase_client, db
from app.core.error_monitor import monitor
from app.services.line_linking import consume_link_code, looks_like_code
from app.services.line_notification import LineNotificationService

router = APIRouter(prefix="/webhook", tags=["webhook"])

_LINK_SUCCESS = (
    "✅ Your LINE account is now linked. You'll receive buy-signal alerts here."
)
_LINK_INVALID = (
    "⚠️ That code is invalid or has expired. Generate a new one on the Settings "
    "page and send it here within a few minutes."
)
_HELP = (
    "Send the 6-character linking code from the app's Settings page to connect "
    "your account and start receiving stock alerts."
)


def _verify_signature(channel_secret: str, body: bytes, signature: str) -> bool:
    """Constant-time check of LINE's X-Line-Signature over the raw body."""
    if not channel_secret or not signature:
        return False
    digest = hmac.new(channel_secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature)


@router.post("/line")
async def line_webhook(request: Request):
    """Handle inbound LINE events. Always 200 once the signature checks out —
    LINE retries on any non-2xx, and per-event problems are reported in-chat,
    not via HTTP status."""
    settings = get_settings()
    body = await request.body()
    signature = request.headers.get("X-Line-Signature", "")

    if not _verify_signature(settings.line_channel_secret, body, signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        payload = json.loads(body)
    except Exception:
        return {"ok": True}

    for event in payload.get("events", []):
        try:
            await _handle_event(event)
        except Exception as e:  # one bad event must not fail the whole delivery
            monitor.log_error("line_webhook.event", str(e))

    return {"ok": True}


async def _handle_event(event: dict) -> None:
    line_service = LineNotificationService()
    event_type = event.get("type")
    reply_token = event.get("replyToken", "")

    if event_type == "follow":
        # User just added the OA as a friend — tell them how to link.
        await line_service.reply_text(reply_token, _HELP)
        return

    if event_type != "message":
        return

    message = event.get("message", {})
    if message.get("type") != "text":
        return

    text = message.get("text", "")
    line_user_id = event.get("source", {}).get("userId")

    if not line_user_id or not looks_like_code(text):
        await line_service.reply_text(reply_token, _HELP)
        return

    user_id = await consume_link_code(text)
    if not user_id:
        await line_service.reply_text(reply_token, _LINK_INVALID)
        return

    await _link_account(user_id, line_user_id)
    await line_service.reply_text(reply_token, _LINK_SUCCESS)


async def _link_account(user_id: str, line_user_id: str) -> None:
    supabase = get_supabase_client()
    await db(
        supabase.table("users")
        .update({"line_user_id": line_user_id})
        .eq("id", user_id)
    )
