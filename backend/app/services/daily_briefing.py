from datetime import datetime, timezone, date
from typing import Optional
import httpx
from openai import AsyncOpenAI
from app.core.config import get_settings
from app.core.database import get_supabase_client
from app.services.line_notification import LineNotificationService


class DailyBriefingService:
    """Sends a daily AI-powered news briefing to users before market open.

    Runs once per day at 8:30 AM ET (1 hour before market open).
    Fetches latest news for each stock in user's watchlist,
    then uses AI to summarize and analyze sentiment.
    """

    SYSTEM_PROMPT = """You are a concise stock news analyst.
Given recent news headlines for stocks in a watchlist, provide a brief daily news briefing.
For each stock:
- Summarize the most important news in 1-2 sentences
- Give sentiment: 🟢 Bullish / 🟡 Neutral / 🔴 Bearish
- Note any catalysts or risks

Keep the total response under 400 words. Be direct and actionable.
If no significant news, say "No major news" for that stock."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = AsyncOpenAI(api_key=self.settings.openai_api_key)
        self.line_service = LineNotificationService()

    @property
    def supabase(self):
        return get_supabase_client()

    async def send_daily_briefings(self) -> None:
        """Send daily news briefing to all users with LINE connected."""
        print(f"[{datetime.now(timezone.utc)}] Starting daily news briefing...")

        # Check if already sent today
        if await self._already_sent_today():
            print("Daily briefing already sent today. Skipping.")
            return

        try:
            users = await self._get_users_with_line()
            if not users:
                print("No users with LINE connected.")
                return

            for user in users:
                await self._send_briefing_to_user(user)

            print(f"[{datetime.now(timezone.utc)}] Daily briefing complete. Sent to {len(users)} users.")

        except Exception as e:
            print(f"Error sending daily briefings: {e}")

    async def _already_sent_today(self) -> bool:
        """Check if daily briefing was already sent today."""
        try:
            today_start = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            ).isoformat()

            response = (
                self.supabase.table("alerts")
                .select("id")
                .eq("signal_type", "DAILY_BRIEFING")
                .gte("sent_at", today_start)
                .limit(1)
                .execute()
            )

            return len(response.data) > 0

        except Exception:
            return False

    async def _get_users_with_line(self) -> list[dict]:
        """Get all active users with LINE connected."""
        try:
            response = (
                self.supabase.table("users")
                .select("id, line_user_id")
                .not_.is_("line_user_id", "null")
                .eq("is_active", True)
                .execute()
            )
            return response.data

        except Exception as e:
            print(f"Error fetching users: {e}")
            return []

    async def _get_user_stocks(self, user_id: str) -> list[str]:
        """Get all enabled stocks for a user."""
        try:
            response = (
                self.supabase.table("watchlists")
                .select("id")
                .eq("user_id", user_id)
                .execute()
            )

            if not response.data:
                return []

            watchlist_id = response.data[0]["id"]

            stocks_response = (
                self.supabase.table("watchlist_stocks")
                .select("symbol")
                .eq("watchlist_id", watchlist_id)
                .eq("is_enabled", True)
                .execute()
            )

            return [row["symbol"] for row in stocks_response.data]

        except Exception:
            return []

    async def _send_briefing_to_user(self, user: dict) -> None:
        """Generate and send daily news briefing to a single user."""
        user_id = user["id"]
        line_user_id = user["line_user_id"]

        symbols = await self._get_user_stocks(user_id)
        if not symbols:
            return

        # Fetch news for all stocks
        all_news: dict[str, list[str]] = {}
        for symbol in symbols:
            news = await self._fetch_stock_news(symbol)
            if news:
                all_news[symbol] = news

        if not all_news:
            return

        # Generate AI briefing from news
        briefing = await self._generate_news_briefing(all_news)
        if not briefing:
            return

        # Format and send
        message = self._format_briefing_message(briefing, symbols)
        is_sent = await self.line_service._send_push_message(line_user_id, message)

        if is_sent:
            try:
                self.supabase.table("alerts").insert({
                    "user_id": user_id,
                    "stock_symbol": ",".join(symbols[:5]),
                    "signal_type": "DAILY_BRIEFING",
                    "ai_summary": briefing[:500],
                    "confidence": "—",
                    "reasons": symbols,
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                }).execute()
            except Exception:
                pass

    async def _fetch_stock_news(self, symbol: str) -> list[str]:
        """Fetch recent news headlines for a stock from Yahoo Finance."""
        try:
            url = f"https://query1.finance.yahoo.com/v1/finance/search"
            params = {
                "q": symbol,
                "quotesCount": 0,
                "newsCount": 5,
                "listsCount": 0,
            }

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    params=params,
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=10.0,
                )
                response.raise_for_status()

            data = response.json()
            news_items = data.get("news", [])

            headlines = []
            for item in news_items[:5]:
                title = item.get("title", "")
                publisher = item.get("publisher", "")
                if title:
                    headlines.append(f"{title} ({publisher})")

            return headlines

        except Exception:
            return []

    async def _generate_news_briefing(self, all_news: dict[str, list[str]]) -> Optional[str]:
        """Generate AI news briefing from collected headlines."""
        try:
            news_text = ""
            for symbol, headlines in all_news.items():
                news_text += f"\n{symbol}:\n"
                for h in headlines:
                    news_text += f"  - {h}\n"

            user_message = (
                f"Today's news for my watchlist:\n"
                f"{news_text}\n"
                "Provide a daily pre-market news briefing with sentiment for each stock."
            )

            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                max_tokens=500,
                temperature=0.3,
            )

            return response.choices[0].message.content or ""

        except Exception as e:
            print(f"Error generating news briefing: {e}")
            return None

    def _format_briefing_message(self, briefing: str, symbols: list[str]) -> str:
        """Format the daily briefing for LINE notification."""
        today = date.today().strftime("%d %b %Y")
        return (
            f"� Daily News Briefing — {today}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"Watchlist: {', '.join(symbols[:8])}\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"{briefing}\n\n"
            f"━━━━━━━━━━━━━━━\n"
            f"⏰ Market opens in 1 hour"
        )
