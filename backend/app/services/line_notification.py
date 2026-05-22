import httpx
from typing import Optional
from app.core.config import get_settings
from app.schemas.stock import AIAnalysisResult


class LineNotificationService:
    """Sends push notifications via LINE Official Account Messaging API."""

    LINE_API_URL = "https://api.line.me/v2/bot/message/push"

    def __init__(self) -> None:
        self.settings = get_settings()

    async def send_buy_alert(
        self,
        line_user_id: str,
        analysis: AIAnalysisResult,
        price: float,
    ) -> bool:
        """Send a buy signal notification to a LINE user.

        Args:
            line_user_id: The LINE user ID to send notification to
            analysis: AI analysis result containing summary and reasons
            price: Current stock price

        Returns:
            True if notification was sent successfully
        """
        message = self._format_message(analysis, price)
        return await self._send_push_message(line_user_id, message)

    def _format_message(self, analysis: AIAnalysisResult, price: float) -> str:
        """Format the buy alert message for LINE notification."""
        reasons_text = "\n".join(f"• {reason}" for reason in analysis.reasons)

        return (
            f"🚀 BUY SIGNAL: {analysis.symbol}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💰 Price: ${price:.2f}\n"
            f"📊 Confidence: {analysis.confidence}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📋 Reasons:\n{reasons_text}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💡 {analysis.summary[:200]}"
        )

    async def _send_push_message(self, line_user_id: str, message: str) -> bool:
        """Send push message via LINE Messaging API."""
        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.settings.line_channel_access_token}",
            }

            payload = {
                "to": line_user_id,
                "messages": [
                    {
                        "type": "text",
                        "text": message,
                    }
                ],
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.LINE_API_URL,
                    json=payload,
                    headers=headers,
                    timeout=10.0,
                )
                response.raise_for_status()

            return True

        except Exception as e:
            print(f"Error sending LINE notification to {line_user_id}: {e}")
            return False
