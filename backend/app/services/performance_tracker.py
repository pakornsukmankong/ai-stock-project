import logging
import asyncio
import pandas as pd
from datetime import datetime, timezone, timedelta
from typing import Optional
from app.core.logging_config import local_now
from app.core.config import get_settings
from app.core.database import get_supabase_client, db
from app.services.market_data import MarketDataService

logger = logging.getLogger(__name__)

BENCHMARK_SYMBOL = "SPY"


class PerformanceTracker:
    """Tracks performance of buy AND sell signal alerts.

    Runs daily to check all alerts that are missing return data and updates them
    based on how many days have passed.

    Returns are stored as SIGNAL performance, not raw price change: a BUY is
    "right" when price rises, a SELL is "right" when price falls. So for a SELL
    the sign is inverted before storing — a positive return_Nd always means "the
    signal was correct", which lets win-rate/avg-return aggregate uniformly
    across both sides.
    """

    def __init__(self) -> None:
        self.market_data = MarketDataService()

    @staticmethod
    def _signal_return(raw_return_pct: float, signal_type: str) -> float:
        """Convert a raw price return into signal performance.

        BUY keeps the sign (up = good); SELL inverts it (down = good)."""
        return -raw_return_pct if signal_type == "SELL" else raw_return_pct

    @property
    def supabase(self):
        return get_supabase_client()

    async def update_performance(self) -> None:
        """Update performance data for all pending alerts."""
        print(f"[{local_now():%Y-%m-%d %H:%M:%S %Z}] Starting performance tracking...")

        try:
            # Get all BUY and SELL alerts with alert_price that still need tracking
            response = await db(
                self.supabase.table("alerts")
                .select("id, stock_symbol, signal_type, alert_price, sent_at, return_1d, return_3d, return_7d")
                .not_.is_("alert_price", "null")
                .order("sent_at", desc=True)
                .limit(100)
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

            # Get unique symbols and fetch current prices concurrently (bounded,
            # so we don't trip Yahoo's rate limiting).
            symbols = list({row["stock_symbol"] for row in response.data})
            semaphore = asyncio.Semaphore(max(1, get_settings().analysis_concurrency))

            async def fetch(symbol: str) -> tuple[str, Optional[float]]:
                async with semaphore:
                    return symbol, await self._get_current_price(symbol)

            fetched = await asyncio.gather(*(fetch(symbol) for symbol in symbols))
            current_prices = {symbol: price for symbol, price in fetched if price}

            updated_count = 0

            for alert in response.data:
                symbol = alert["stock_symbol"]
                alert_price = alert["alert_price"]

                if symbol not in current_prices or not alert_price:
                    continue

                current_price = current_prices[symbol]
                signal_type = alert.get("signal_type", "BUY")
                sent_at = datetime.fromisoformat(alert["sent_at"].replace("Z", "+00:00"))
                days_passed = (now - sent_at).days

                # Raw price move, then signal performance (inverted for SELL).
                raw_return_pct = ((current_price - alert_price) / alert_price) * 100
                signal_return_pct = self._signal_return(raw_return_pct, signal_type)

                update_data = {}

                # Update 1D return if >= 1 day passed and not yet set
                if days_passed >= 1 and alert.get("return_1d") is None:
                    update_data["price_after_1d"] = current_price
                    update_data["return_1d"] = round(signal_return_pct, 2)

                # Update 3D return if >= 3 days passed and not yet set
                if days_passed >= 3 and alert.get("return_3d") is None:
                    update_data["price_after_3d"] = current_price
                    update_data["return_3d"] = round(signal_return_pct, 2)

                # Update 7D return if >= 7 days passed and not yet set
                if days_passed >= 7 and alert.get("return_7d") is None:
                    update_data["price_after_7d"] = current_price
                    update_data["return_7d"] = round(signal_return_pct, 2)
                    update_data["is_successful"] = self._beat_benchmark(
                        raw_return_pct, sent_at, spy_df, spy_now, signal_type
                    )

                if update_data:
                    await db(
                        self.supabase.table("alerts")
                        .update(update_data)
                        .eq("id", alert["id"])
                    )
                    updated_count += 1

            print(f"[{local_now():%Y-%m-%d %H:%M:%S %Z}] Performance tracking complete. Updated {updated_count} alerts.")

        except Exception as e:
            logger.error(f"Error in performance tracking: {e}")

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
        signal_type: str = "BUY",
    ) -> bool:
        """Success is side-aware alpha vs SPY over the same window:

        - BUY  succeeds when the stock OUTperformed SPY (you were right to hold).
        - SELL succeeds when the stock UNDERperformed SPY (you were right to exit).

        `stock_return_pct` is the RAW price move (not the inverted signal return).
        Falls back to SPY=0 (absolute move) when benchmark data is missing.
        """
        spy_return_pct = 0.0
        if spy_df is not None and spy_now is not None:
            spy_at_alert = self._close_on_or_before(spy_df, sent_at)
            if spy_at_alert:
                spy_return_pct = ((spy_now - spy_at_alert) / spy_at_alert) * 100

        outperformed = stock_return_pct > spy_return_pct
        return outperformed if signal_type != "SELL" else not outperformed

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
