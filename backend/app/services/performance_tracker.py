import pandas as pd
from datetime import datetime, timezone, timedelta
from typing import Optional
from app.core.database import get_supabase_client
from app.services.market_data import MarketDataService

BENCHMARK_SYMBOL = "SPY"


class PerformanceTracker:
    """Tracks performance of buy signal alerts.

    Runs daily to check all alerts that are missing return data
    and updates them based on how many days have passed.
    """

    def __init__(self) -> None:
        self.market_data = MarketDataService()

    @property
    def supabase(self):
        return get_supabase_client()

    async def update_performance(self) -> None:
        """Update performance data for all pending alerts."""
        print(f"[{datetime.now(timezone.utc)}] Starting performance tracking...")

        try:
            # Get all BUY alerts with alert_price that still need tracking
            response = (
                self.supabase.table("alerts")
                .select("id, stock_symbol, alert_price, sent_at, return_1d, return_3d, return_7d")
                .eq("signal_type", "BUY")
                .not_.is_("alert_price", "null")
                .order("sent_at", desc=True)
                .limit(100)
                .execute()
            )

            if not response.data:
                print("No alerts to track.")
                return

            now = datetime.now(timezone.utc)

            # Fetch the benchmark once so success can be measured as alpha vs SPY
            # (beating the market) rather than just an absolute positive return.
            spy_df = await self.market_data.fetch_ohlcv(
                BENCHMARK_SYMBOL, interval="1d", period="3mo"
            )
            spy_now = (
                float(spy_df["close"].iloc[-1])
                if spy_df is not None and not spy_df.empty
                else None
            )

            # Get unique symbols and fetch current prices
            symbols = list({row["stock_symbol"] for row in response.data})
            current_prices = {}
            for symbol in symbols:
                price = await self._get_current_price(symbol)
                if price:
                    current_prices[symbol] = price

            updated_count = 0

            for alert in response.data:
                symbol = alert["stock_symbol"]
                alert_price = alert["alert_price"]

                if symbol not in current_prices or not alert_price:
                    continue

                current_price = current_prices[symbol]
                sent_at = datetime.fromisoformat(alert["sent_at"].replace("Z", "+00:00"))
                days_passed = (now - sent_at).days

                update_data = {}

                # Update 1D return if >= 1 day passed and not yet set
                if days_passed >= 1 and alert.get("return_1d") is None:
                    return_pct = ((current_price - alert_price) / alert_price) * 100
                    update_data["price_after_1d"] = current_price
                    update_data["return_1d"] = round(return_pct, 2)

                # Update 3D return if >= 3 days passed and not yet set
                if days_passed >= 3 and alert.get("return_3d") is None:
                    return_pct = ((current_price - alert_price) / alert_price) * 100
                    update_data["price_after_3d"] = current_price
                    update_data["return_3d"] = round(return_pct, 2)

                # Update 7D return if >= 7 days passed and not yet set
                if days_passed >= 7 and alert.get("return_7d") is None:
                    return_pct = ((current_price - alert_price) / alert_price) * 100
                    update_data["price_after_7d"] = current_price
                    update_data["return_7d"] = round(return_pct, 2)
                    update_data["is_successful"] = self._beat_benchmark(
                        return_pct, sent_at, spy_df, spy_now
                    )

                if update_data:
                    self.supabase.table("alerts").update(update_data).eq(
                        "id", alert["id"]
                    ).execute()
                    updated_count += 1

            print(f"[{datetime.now(timezone.utc)}] Performance tracking complete. Updated {updated_count} alerts.")

        except Exception as e:
            print(f"Error in performance tracking: {e}")

    async def _get_current_price(self, symbol: str) -> Optional[float]:
        """Get the latest closing price for a symbol."""
        try:
            df = await self.market_data.fetch_ohlcv(symbol, interval="1d", period="5d")
            if df is None or df.empty:
                return None
            return float(df["close"].iloc[-1])
        except Exception:
            return None

    def _beat_benchmark(
        self,
        stock_return_pct: float,
        sent_at: datetime,
        spy_df: Optional[pd.DataFrame],
        spy_now: Optional[float],
    ) -> bool:
        """Success = the alert beat SPY over the same window (positive alpha).

        Falls back to an absolute positive return when benchmark data is missing.
        """
        if spy_df is None or spy_now is None:
            return stock_return_pct > 0

        spy_at_alert = self._close_on_or_before(spy_df, sent_at)
        if not spy_at_alert:
            return stock_return_pct > 0

        spy_return_pct = ((spy_now - spy_at_alert) / spy_at_alert) * 100
        return stock_return_pct > spy_return_pct

    def _close_on_or_before(self, df: pd.DataFrame, dt: datetime) -> Optional[float]:
        """Latest close at or before `dt` (nearest prior trading day)."""
        try:
            ts = pd.Timestamp(dt)
            if ts.tzinfo is not None:
                ts = ts.tz_convert("UTC").tz_localize(None)
            sub = df.loc[df.index <= ts]
            if sub.empty:
                return None
            return float(sub["close"].iloc[-1])
        except Exception:
            return None
