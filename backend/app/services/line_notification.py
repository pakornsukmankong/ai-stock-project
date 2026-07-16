import logging
import asyncio
from typing import Optional
from app.core.config import get_settings
from app.core.http_client import get_http_client
from app.services.markets import market_for_symbol, market_local_time
from app.schemas.stock import AIAnalysisResult

logger = logging.getLogger(__name__)


# Outcome of a LINE push attempt.
SENT = "sent"
RATE_LIMITED = "rate_limited"      # transient 429 — safe to retry
MONTHLY_LIMIT = "monthly_limit"    # quota exhausted — retrying is pointless
FAILED = "failed"                  # other error — retry next cycle

# LINE hard limits: one text message is at most 5000 characters, and a single
# push request carries at most 5 message objects. Exceeding either is a 400 —
# a big watchlist's briefing (or a digest with many signals) blows past 5000.
MAX_TEXT_LENGTH = 5000
MAX_MESSAGES_PER_PUSH = 5
_TRUNCATION_NOTICE = "\n… (truncated)"


def chunk_text(text: str, limit: int = MAX_TEXT_LENGTH) -> list:
    """Split text into <=limit chunks, breaking on line boundaries where possible."""
    if len(text) <= limit:
        return [text]

    chunks: list = []
    current = ""
    for line in text.split("\n"):
        # A single line longer than the limit has no boundary to break on.
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]

        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            chunks.append(current)
            current = line
        else:
            current = candidate

    if current:
        chunks.append(current)
    return chunks


class LineNotificationService:
    """Sends push notifications via LINE Official Account Messaging API.

    Distinguishes the two kinds of HTTP 429 LINE returns:
    - a transient rate limit (too many requests/sec) → short retry, and
    - the monthly free-tier message quota being exhausted
      ("You have reached your monthly limit.") → never retried.

    Also exposes the LINE quota endpoints so callers can skip sending
    entirely once the monthly limit is reached.
    """

    PUSH_URL = "https://api.line.me/v2/bot/message/push"
    REPLY_URL = "https://api.line.me/v2/bot/message/reply"
    QUOTA_URL = "https://api.line.me/v2/bot/message/quota"
    QUOTA_CONSUMPTION_URL = "https://api.line.me/v2/bot/message/quota/consumption"

    MAX_RETRIES = 2
    RETRY_WAIT_SECONDS = 2

    def __init__(self) -> None:
        self.settings = get_settings()

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.settings.line_channel_access_token}",
        }

    # ------------------------------------------------------------------ #
    # Quota
    # ------------------------------------------------------------------ #
    async def get_quota_status(self) -> dict:
        """Fetch the monthly message quota and how much has been consumed.

        Returns a dict:
        - type: "limited" | "none" | "unknown"
        - limit: int | None  (monthly cap; None when unlimited/unknown)
        - used: int          (messages consumed this month)
        - remaining: int | None

        On error returns type="unknown" so callers can choose to proceed
        (fail-open) rather than silently dropping notifications.
        """
        try:
            client = get_http_client()

            quota_resp = await client.get(
                self.QUOTA_URL, headers=self._headers(), timeout=10.0
            )
            quota_resp.raise_for_status()
            quota = quota_resp.json()

            if quota.get("type") != "limited":
                # "none" = unlimited plan
                return {"type": quota.get("type", "none"), "limit": None, "used": 0, "remaining": None}

            limit = quota.get("value")

            cons_resp = await client.get(
                self.QUOTA_CONSUMPTION_URL, headers=self._headers(), timeout=10.0
            )
            cons_resp.raise_for_status()
            used = cons_resp.json().get("totalUsage", 0)

            remaining = max(0, limit - used) if limit is not None else None
            return {"type": "limited", "limit": limit, "used": used, "remaining": remaining}

        except Exception as e:
            logger.error(f"[LINE] Failed to fetch quota: {e}")
            return {"type": "unknown", "limit": None, "used": 0, "remaining": None}

    # ------------------------------------------------------------------ #
    # Sending
    # ------------------------------------------------------------------ #
    async def send_text(self, line_user_id: str, message: str) -> str:
        """Send a text push message. Returns one of SENT/RATE_LIMITED/MONTHLY_LIMIT/FAILED."""
        for attempt in range(self.MAX_RETRIES + 1):
            status = await self._call_push(line_user_id, message)

            if status == SENT or status == MONTHLY_LIMIT:
                # Success, or a quota exhaustion that retrying cannot fix.
                return status

            # RATE_LIMITED or FAILED → retry a couple of times with backoff.
            if attempt < self.MAX_RETRIES:
                await asyncio.sleep(self.RETRY_WAIT_SECONDS)

        return status

    async def reply_text(self, reply_token: str, message: str) -> bool:
        """Reply to an inbound webhook event using its reply token.

        Replies are free (they don't count against the monthly push quota) and
        are the natural way to acknowledge an account-linking message. LINE's
        "Verify" button and already-consumed tokens yield a non-200; we treat any
        failure as best-effort and never raise.
        """
        if not reply_token:
            return False

        payload = {
            "replyToken": reply_token,
            "messages": [
                {"type": "text", "text": chunk}
                for chunk in chunk_text(message)[:MAX_MESSAGES_PER_PUSH]
            ],
        }
        try:
            client = get_http_client()
            response = await client.post(
                self.REPLY_URL,
                json=payload,
                headers=self._headers(),
                timeout=10.0,
            )
            if response.status_code != 200:
                logger.error(f"[LINE] Reply failed {response.status_code}: {response.text[:200]}")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"[LINE] Reply error: {e}")
            return False

    async def send_buy_alert(
        self,
        line_user_id: str,
        analysis: AIAnalysisResult,
        price: float,
    ) -> str:
        """Send a single buy-signal notification. Returns a send-status string."""
        message = self._format_message(analysis, price)
        return await self.send_text(line_user_id, message)

    async def _call_push(self, line_user_id: str, message: str) -> str:
        """Perform one push request and classify the outcome.

        Long messages are split across message objects rather than rejected:
        LINE 400s anything over 5000 characters, which a large watchlist's
        briefing exceeds. Beyond the 5-object ceiling the tail is dropped with a
        notice — a truncated briefing beats no briefing.
        """
        chunks = chunk_text(message)
        if len(chunks) > MAX_MESSAGES_PER_PUSH:
            chunks = chunks[:MAX_MESSAGES_PER_PUSH]
            tail = chunks[-1][: MAX_TEXT_LENGTH - len(_TRUNCATION_NOTICE)]
            chunks[-1] = tail + _TRUNCATION_NOTICE

        payload = {
            "to": line_user_id,
            "messages": [{"type": "text", "text": chunk} for chunk in chunks],
        }

        try:
            client = get_http_client()
            response = await client.post(
                self.PUSH_URL,
                json=payload,
                headers=self._headers(),
                timeout=10.0,
            )

            if response.status_code == 200:
                return SENT

            if response.status_code == 429:
                body = (response.text or "").lower()
                if "monthly limit" in body:
                    print("[LINE] Monthly message quota reached — skipping further LINE sends.")
                    return MONTHLY_LIMIT
                print(f"[LINE] Rate limited (429): {response.text[:200]}")
                return RATE_LIMITED

            logger.error(f"[LINE] Push failed {response.status_code}: {response.text[:200]}")
            return FAILED

        except Exception as e:
            logger.error(f"[LINE] Push error for {line_user_id}: {e}")
            return FAILED

    # Backward-compatible bool wrapper (used by daily briefing).
    async def _send_push_message(self, line_user_id: str, message: str) -> bool:
        return await self.send_text(line_user_id, message) == SENT

    # ------------------------------------------------------------------ #
    # Formatting
    # ------------------------------------------------------------------ #
    def _format_message(self, analysis: AIAnalysisResult, price: float) -> str:
        """Format a single-signal alert message."""
        reasons_text = "\n".join(f"• {reason}" for reason in analysis.reasons)
        action_emoji = {"BUY": "🚀", "SELL": "🔴", "HOLD": "⏸️"}.get(analysis.action, "📊")
        # Currency + timestamp follow the stock's own exchange (US → $/ET,
        # Thai .BK → ฿/ICT), not a hardcoded US assumption.
        market = market_for_symbol(analysis.symbol)

        return (
            f"{action_emoji} {analysis.action} SIGNAL: {analysis.symbol}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💰 Price: {market.currency_symbol}{price:.2f}\n"
            f"📊 Confidence: {analysis.confidence}\n"
            f"🎯 Action: {analysis.action}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📋 Reasons:\n{reasons_text}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💡 {analysis.summary[:200]}\n"
            f"🕐 {market_local_time(market)}"
        )

    def format_digest(self, items: list[dict]) -> str:
        """Combine multiple buy signals for one user into a single message.

        Sending one digest instead of N separate pushes is the main lever for
        staying under the LINE monthly message quota.

        Args:
            items: list of {"symbol", "analysis": AIAnalysisResult, "price": float}
        """
        if len(items) == 1:
            it = items[0]
            return self._format_message(it["analysis"], it["price"])

        lines = [f"🚀 BUY SIGNALS ({len(items)})", "━━━━━━━━━━━━━━━"]
        for it in items:
            analysis: AIAnalysisResult = it["analysis"]
            price = it["price"]
            market = market_for_symbol(analysis.symbol)
            lines.append(
                f"📈 {analysis.symbol}  {market.currency_symbol}{price:.2f}  ·  {analysis.confidence}"
            )
            lines.append(f"💡 {analysis.summary[:160]}")
            for reason in analysis.reasons[:3]:
                lines.append(f"• {reason}")
            lines.append("")  # blank line between stocks

        # A cycle only bundles symbols from open exchanges, and US/SET don't
        # overlap — so one timestamp in the batch's market is accurate.
        footer_market = market_for_symbol(items[0]["analysis"].symbol)
        lines.append(f"🕐 {market_local_time(footer_market)}")

        return "\n".join(lines).rstrip()
