from datetime import datetime, timezone
from typing import Optional
from openai import AsyncOpenAI
from app.core.config import get_settings
from app.core.database import get_supabase_client, db
from app.core.http_client import get_http_client
from app.core.validation import is_valid_symbol
from app.services.line_notification import LineNotificationService
from app.services.markets import market_for_symbol, US_MARKET, Market


class DailyBriefingService:
    """Sends a daily AI-powered news briefing to users before market open.

    Runs once per market per day, ~1 hour before that market opens (US at
    12:30 UTC, SET at 02:00 UTC). Each run only covers the stocks that belong
    to that market and only reaches users who actually hold one, so a Thai
    watchlist gets a Thai-timed briefing and a US watchlist a US-timed one.
    """

    SYSTEM_PROMPT = """You are a concise stock news analyst.
Given recent news headlines for stocks in a watchlist, provide a brief daily news briefing.
You MUST cover ALL stocks listed — do not skip any.
For each stock:
- Summarize the most important news in 1-2 sentences
- Give sentiment: 🟢 Bullish / 🟡 Neutral / 🔴 Bearish
- Note any catalysts or risks
- If no news available, state "No major news" and give a neutral outlook

Keep each stock to 2-3 lines max. Be direct and actionable."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = AsyncOpenAI(api_key=self.settings.openai_api_key)
        self.line_service = LineNotificationService()

    @property
    def supabase(self):
        return get_supabase_client()

    async def send_daily_briefings(self, market: Market = US_MARKET) -> None:
        """Send the pre-open news briefing for one market to eligible users."""
        print(f"[{datetime.now(timezone.utc)}] Starting {market.code} daily news briefing...")

        # Check if this market's briefing already went out today (its local day).
        if await self._already_sent_today(market):
            print(f"{market.code} daily briefing already sent today. Skipping.")
            return

        try:
            users = await self._get_users_with_line()
            if not users:
                print("No users with LINE connected.")
                return

            sent = 0
            for user in users:
                if await self._send_briefing_to_user(user, market):
                    sent += 1

            print(f"[{datetime.now(timezone.utc)}] {market.code} daily briefing complete. Sent to {sent} users.")

        except Exception as e:
            print(f"Error sending {market.code} daily briefings: {e}")

    @staticmethod
    def _briefing_type(market: Market) -> str:
        """Per-market signal_type so each market's 'already sent' guard is independent."""
        return f"DAILY_BRIEFING:{market.code}"

    async def _already_sent_today(self, market: Market) -> bool:
        """Check if this market's briefing was already sent during its local day."""
        try:
            today_local = datetime.now(market.tz).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            today_start = today_local.astimezone(timezone.utc).isoformat()

            response = await db(
                self.supabase.table("alerts")
                .select("id")
                .eq("signal_type", self._briefing_type(market))
                .gte("sent_at", today_start)
                .limit(1)
            )

            return len(response.data) > 0

        except Exception:
            return False

    async def _get_users_with_line(self) -> list[dict]:
        """Get all active users with LINE connected."""
        try:
            response = await db(
                self.supabase.table("users")
                .select("id, line_user_id")
                .not_.is_("line_user_id", "null")
                .eq("is_active", True)
            )
            return response.data

        except Exception as e:
            print(f"Error fetching users: {e}")
            return []

    async def _get_user_stocks(self, user_id: str, market: Market) -> list[str]:
        """Get the user's enabled stocks that belong to `market`."""
        try:
            response = await db(
                self.supabase.table("watchlists")
                .select("id")
                .eq("user_id", user_id)
                .limit(1)
            )

            if not response.data:
                return []

            watchlist_id = response.data[0]["id"]

            stocks_response = await db(
                self.supabase.table("watchlist_stocks")
                .select("symbol")
                .eq("watchlist_id", watchlist_id)
                .eq("is_enabled", True)
            )

            return [
                row["symbol"]
                for row in stocks_response.data
                if market_for_symbol(row["symbol"]).code == market.code
            ]

        except Exception:
            return []

    async def _send_briefing_to_user(self, user: dict, market: Market) -> bool:
        """Generate and send this market's briefing to one user. Returns True if sent."""
        user_id = user["id"]
        line_user_id = user["line_user_id"]

        symbols = await self._get_user_stocks(user_id, market)
        if not symbols:
            return False  # user holds nothing in this market — nothing to send

        # Fetch news for all stocks (include even if no news)
        all_news: dict[str, list[str]] = {}
        for symbol in symbols:
            news = await self._fetch_stock_news(symbol)
            all_news[symbol] = news if news else ["No recent news found"]

        # Generate AI briefing from news
        briefing = await self._generate_news_briefing(all_news)
        if not briefing:
            return False

        # Format and send
        message = self._format_briefing_message(briefing, symbols, market)
        is_sent = await self.line_service._send_push_message(line_user_id, message)

        if is_sent:
            try:
                await db(
                    self.supabase.table("alerts").insert({
                        "user_id": user_id,
                        "stock_symbol": ",".join(symbols[:5]),
                        "signal_type": self._briefing_type(market),
                        "ai_summary": briefing[:500],
                        "confidence": "—",
                        "reasons": symbols,
                        "sent_at": datetime.now(timezone.utc).isoformat(),
                    })
                )
            except Exception:
                pass

        return is_sent

    async def _fetch_stock_news(self, symbol: str) -> list[str]:
        """Fetch recent news headlines for a stock from Yahoo Finance."""
        if not is_valid_symbol(symbol):
            return []

        try:
            url = "https://query1.finance.yahoo.com/v1/finance/search"
            params = {
                "q": symbol,
                "quotesCount": 0,
                "newsCount": 5,
                "listsCount": 0,
            }

            client = get_http_client()
            response = await client.get(url, params=params, timeout=10.0)
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
                model=self.settings.openai_model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                max_tokens=5000,
                temperature=0.3,
            )

            return response.choices[0].message.content or ""

        except Exception as e:
            print(f"Error generating news briefing: {e}")
            return None

    def _format_briefing_message(
        self, briefing: str, symbols: list[str], market: Market
    ) -> str:
        """Format the daily briefing for LINE notification (market-local date)."""
        today = datetime.now(market.tz).strftime("%d %b %Y")
        return (
            f"📰 {market.code} Daily News Briefing — {today}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"Watchlist: {', '.join(symbols[:8])}\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"{briefing}\n\n"
            f"━━━━━━━━━━━━━━━\n"
            f"⏰ {market.code} market opens in ~1 hour ({market.tz_label})"
        )
