import asyncio
import httpx
from typing import Optional
from app.core.config import get_settings
from app.schemas.stock import AIAnalysisResult


# Outcome of a LINE push attempt.
SENT = "sent"
RATE_LIMITED = "rate_limited"      # transient 429 — safe to retry
MONTHLY_LIMIT = "monthly_limit"    # quota exhausted — retrying is pointless
FAILED = "failed"                  # other error — retry next cycle


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
            async with httpx.AsyncClient() as client:
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
            print(f"[LINE] Failed to fetch quota: {e}")
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
        """Perform one push request and classify the outcome."""
        payload = {
            "to": line_user_id,
            "messages": [{"type": "text", "text": message}],
        }

        try:
            async with httpx.AsyncClient() as client:
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

            print(f"[LINE] Push failed {response.status_code}: {response.text[:200]}")
            return FAILED

        except Exception as e:
            print(f"[LINE] Push error for {line_user_id}: {e}")
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

        return (
            f"{action_emoji} {analysis.action} SIGNAL: {analysis.symbol}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💰 Price: ${price:.2f}\n"
            f"📊 Confidence: {analysis.confidence}\n"
            f"🎯 Action: {analysis.action}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📋 Reasons:\n{reasons_text}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💡 {analysis.summary[:200]}"
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
            lines.append(f"📈 {analysis.symbol}  ${price:.2f}  ·  {analysis.confidence}")
            lines.append(f"💡 {analysis.summary[:160]}")
            for reason in analysis.reasons[:3]:
                lines.append(f"• {reason}")
            lines.append("")  # blank line between stocks

        return "\n".join(lines).rstrip()
