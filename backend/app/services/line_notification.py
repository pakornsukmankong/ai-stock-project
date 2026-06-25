import asyncio
import httpx
from typing import Optional
from app.core.config import get_settings
from app.schemas.stock import AIAnalysisResult


class LineNotificationService:
    """LINE Messaging API push/multicast notification service with rate-limit handling."""

    PUSH_URL = "https://api.line.me/v2/bot/message/push"
    MULTICAST_URL = "https://api.line.me/v2/bot/message/multicast"
    MAX_MULTICAST_RECIPIENTS = 500  # LINE API hard limit

    MAX_RETRIES = 3
    INITIAL_RETRY_DELAY = 1.0  # seconds; doubles each attempt (1 → 2 → 4)

    def __init__(self) -> None:
        self.settings = get_settings()
        # Limit concurrent outbound requests to avoid bursting the rate limit
        self._semaphore = asyncio.Semaphore(5)

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    async def send_alert(
        self,
        line_user_id: str,
        analysis: AIAnalysisResult,
        price: float,
    ) -> bool:
        """Send a single push alert to one LINE user."""
        message = self._format_message(analysis, price)
        return await self._push_with_retry(line_user_id, message)

    async def send_bulk_alerts(
        self,
        targets: list[tuple[str, AIAnalysisResult, float]],
        batch_size: int = 10,
        batch_delay: float = 1.0,
    ) -> dict[str, bool]:
        """
        Send alerts to many users efficiently.

        Uses multicast (up to 500 recipients per call) when all targets share the
        same analysis + price; falls back to batched push otherwise.
        """
        if not targets:
            return {}

        # Fast path: same analysis for everyone → multicast
        analyses = {id(a) for _, a, _ in targets}
        prices = {p for _, _, p in targets}
        if len(analyses) == 1 and len(prices) == 1:
            _, analysis, price = targets[0]
            user_ids = [uid for uid, _, _ in targets]
            return await self._multicast_batched(user_ids, analysis, price)

        # General path: individual pushes in controlled batches
        return await self._push_batched(targets, batch_size, batch_delay)

    # ------------------------------------------------------------------ #
    #  Multicast helpers                                                   #
    # ------------------------------------------------------------------ #

    async def _multicast_batched(
        self,
        user_ids: list[str],
        analysis: AIAnalysisResult,
        price: float,
    ) -> dict[str, bool]:
        """Split recipients into ≤500-user chunks and multicast each chunk."""
        message = self._format_message(analysis, price)
        results: dict[str, bool] = {}

        for i in range(0, len(user_ids), self.MAX_MULTICAST_RECIPIENTS):
            chunk = user_ids[i : i + self.MAX_MULTICAST_RECIPIENTS]
            ok = await self._multicast_with_retry(chunk, message)
            results.update({uid: ok for uid in chunk})

            if i + self.MAX_MULTICAST_RECIPIENTS < len(user_ids):
                await asyncio.sleep(1.0)  # brief pause between chunks

        return results

    async def _multicast_with_retry(self, user_ids: list[str], message: str) -> bool:
        delay = self.INITIAL_RETRY_DELAY
        for attempt in range(self.MAX_RETRIES):
            async with self._semaphore:
                status = await self._call_multicast(user_ids, message)

            if status is True:
                return True
            if status == 429:
                wait = delay * (2**attempt)
                print(f"[LINE] Multicast rate-limited. Retrying in {wait}s ({attempt + 1}/{self.MAX_RETRIES})")
                await asyncio.sleep(wait)
            else:
                return False

        print(f"[LINE] Multicast failed after {self.MAX_RETRIES} retries ({len(user_ids)} recipients)")
        return False

    async def _call_multicast(self, user_ids: list[str], message: str) -> bool | int:
        try:
            payload = {
                "to": user_ids,
                "messages": [{"type": "text", "text": message}],
            }
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.MULTICAST_URL,
                    json=payload,
                    headers=self._headers(),
                    timeout=10.0,
                )

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    await asyncio.sleep(float(retry_after))
                return 429

            response.raise_for_status()
            return True

        except httpx.HTTPStatusError as e:
            print(f"[LINE] Multicast HTTP error: {e}")
            return False
        except Exception as e:
            print(f"[LINE] Multicast unexpected error: {e}")
            return False

    # ------------------------------------------------------------------ #
    #  Push helpers                                                        #
    # ------------------------------------------------------------------ #

    async def _push_batched(
        self,
        targets: list[tuple[str, AIAnalysisResult, float]],
        batch_size: int,
        batch_delay: float,
    ) -> dict[str, bool]:
        results: dict[str, bool] = {}

        for i in range(0, len(targets), batch_size):
            batch = targets[i : i + batch_size]
            tasks = [self.send_alert(uid, analysis, price) for uid, analysis, price in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for (uid, _, _), result in zip(batch, batch_results):
                results[uid] = result if isinstance(result, bool) else False

            if i + batch_size < len(targets):
                await asyncio.sleep(batch_delay)

        return results

    async def _push_with_retry(self, line_user_id: str, message: str) -> bool:
        delay = self.INITIAL_RETRY_DELAY
        for attempt in range(self.MAX_RETRIES):
            async with self._semaphore:
                status = await self._call_push(line_user_id, message)

            if status is True:
                return True
            if status == 429:
                wait = delay * (2**attempt)
                print(f"[LINE] Push rate-limited for {line_user_id}. Retrying in {wait}s ({attempt + 1}/{self.MAX_RETRIES})")
                await asyncio.sleep(wait)
            else:
                return False

        print(f"[LINE] Push failed after {self.MAX_RETRIES} retries for {line_user_id}")
        return False

    async def _call_push(self, line_user_id: str, message: str) -> bool | int:
        try:
            payload = {
                "to": line_user_id,
                "messages": [{"type": "text", "text": message}],
            }
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.PUSH_URL,
                    json=payload,
                    headers=self._headers(),
                    timeout=10.0,
                )

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    await asyncio.sleep(float(retry_after))
                return 429

            response.raise_for_status()
            return True

        except httpx.HTTPStatusError as e:
            print(f"[LINE] Push HTTP error for {line_user_id}: {e}")
            return False
        except Exception as e:
            print(f"[LINE] Push unexpected error for {line_user_id}: {e}")
            return False

    # ------------------------------------------------------------------ #
    #  Shared utilities                                                    #
    # ------------------------------------------------------------------ #

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.settings.line_channel_access_token}",
        }

    def _format_message(self, analysis: AIAnalysisResult, price: float) -> str:
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