from datetime import datetime, timezone, timedelta
from typing import Optional
from app.core.database import get_supabase_client
from app.services.market_data import MarketDataService


class PerformanceTracker:
    """Tracks performance of buy signal alerts.

    Runs daily to check alerts from 1, 3, and 7 days ago
    and records the actual price change.
    """

    def __init__(self) -> None:
        self.market_data = MarketDataService()

    @property
    def supabase(self):
        return get_supabase_client()

    async def update_performance(self) -> None:
        """Update performance data for past alerts."""
        print(f"[{datetime.now(timezone.utc)}] Starting performance tracking...")

        await self._update_1d_performance()
        await self._update_3d_performance()
        await self._update_7d_performance()

        print(f"[{datetime.now(timezone.utc)}] Performance tracking complete.")

    async def _update_1d_performance(self) -> None:
        """Update 1-day performance for alerts sent ~1 day ago."""
        await self._update_for_period(
            days_ago=1,
            price_column="price_after_1d",
            return_column="return_1d",
        )

    async def _update_3d_performance(self) -> None:
        """Update 3-day performance for alerts sent ~3 days ago."""
        await self._update_for_period(
            days_ago=3,
            price_column="price_after_3d",
            return_column="return_3d",
        )

    async def _update_7d_performance(self) -> None:
        """Update 7-day performance for alerts sent ~7 days ago."""
        await self._update_for_period(
            days_ago=7,
            price_column="price_after_7d",
            return_column="return_7d",
        )

    async def _update_for_period(
        self,
        days_ago: int,
        price_column: str,
        return_column: str,
    ) -> None:
        """Update performance for alerts from N days ago."""
        try:
            # Get alerts from N days ago that haven't been tracked yet
            target_date = datetime.now(timezone.utc) - timedelta(days=days_ago)
            window_start = (target_date - timedelta(hours=12)).isoformat()
            window_end = (target_date + timedelta(hours=12)).isoformat()

            response = (
                self.supabase.table("alerts")
                .select("id, stock_symbol, alert_price")
                .eq("signal_type", "BUY")
                .is_(price_column, "null")
                .not_.is_("alert_price", "null")
                .gte("sent_at", window_start)
                .lte("sent_at", window_end)
                .execute()
            )

            if not response.data:
                return

            # Get unique symbols
            symbols = list({row["stock_symbol"] for row in response.data})

            # Fetch current prices
            current_prices: dict[str, float] = {}
            for symbol in symbols:
                price = await self._get_current_price(symbol)
                if price:
                    current_prices[symbol] = price

            # Update each alert
            for alert in response.data:
                symbol = alert["stock_symbol"]
                alert_price = alert["alert_price"]

                if symbol not in current_prices or not alert_price:
                    continue

                current_price = current_prices[symbol]
                return_pct = ((current_price - alert_price) / alert_price) * 100

                update_data = {
                    price_column: current_price,
                    return_column: round(return_pct, 2),
                }

                # Mark as successful if 7-day return is positive
                if days_ago == 7:
                    update_data["is_successful"] = return_pct > 0

                self.supabase.table("alerts").update(update_data).eq(
                    "id", alert["id"]
                ).execute()

        except Exception as e:
            print(f"Error updating {days_ago}d performance: {e}")

    async def _get_current_price(self, symbol: str) -> Optional[float]:
        """Get the latest closing price for a symbol."""
        try:
            df = await self.market_data.fetch_ohlcv(symbol, interval="1d", period="5d")
            if df is None or df.empty:
                return None
            return float(df["close"].iloc[-1])
        except Exception:
            return None
