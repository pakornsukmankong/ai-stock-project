import logging
import pandas as pd
from typing import Optional

from app.core.config import get_settings
from app.core.http_client import get_http_client
from app.core.validation import is_valid_symbol

logger = logging.getLogger(__name__)


class MarketDataService:
    """Fetches market data (OHLCV) for stock symbols."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_url = "https://query1.finance.yahoo.com/v8/finance/chart"

    async def fetch_ohlcv(
        self,
        symbol: str,
        interval: str = "1d",
        period: str = "1y",
    ) -> Optional[pd.DataFrame]:
        """Fetch OHLCV data for a given stock symbol.

        Args:
            symbol: Stock ticker symbol (e.g., 'AAPL')
            interval: Data interval (1m, 5m, 15m, 1h, 4h, 1d)
            period: Data period (1d, 5d, 1mo, 3mo, 6mo, 1y)

        Returns:
            DataFrame with columns: open, high, low, close, volume
        """
        # The symbol lands in the request path, so it is validated here as well as
        # at the API boundary — this is also reachable from the scheduler and DB.
        if not is_valid_symbol(symbol):
            logger.warning(f"Refusing to fetch market data for invalid symbol: {symbol!r}")
            return None

        # Yahoo Finance has no native 4h interval — synthesize it by resampling
        # 1h bars, the same way the MTF engine does for its 4h timeframe.
        if interval == "4h":
            hourly = await self._fetch_raw(symbol, "1h", period)
            if hourly is None or hourly.empty:
                return None
            return self._resample_to_4h(hourly)

        return await self._fetch_raw(symbol, interval, period)

    async def _fetch_raw(
        self,
        symbol: str,
        interval: str,
        period: str,
    ) -> Optional[pd.DataFrame]:
        """Fetch a Yahoo-native interval directly (no resampling)."""
        try:
            url = f"{self.base_url}/{symbol.upper()}"
            params = {
                "interval": interval,
                "range": period,
            }

            client = get_http_client()
            response = await client.get(url, params=params, timeout=10.0)
            response.raise_for_status()

            data = response.json()
            result = data["chart"]["result"][0]

            # Check if timestamp exists (market might be closed)
            if "timestamp" not in result or result["timestamp"] is None:
                return None

            timestamps = result["timestamp"]
            quotes = result["indicators"]["quote"][0]

            df = pd.DataFrame(
                {
                    "timestamp": pd.to_datetime(timestamps, unit="s"),
                    "open": quotes["open"],
                    "high": quotes["high"],
                    "low": quotes["low"],
                    "close": quotes["close"],
                    "volume": quotes["volume"],
                }
            )
            df.set_index("timestamp", inplace=True)
            df.dropna(inplace=True)

            return df

        except Exception as e:
            logger.error(f"Error fetching market data for {symbol}: {e}")
            return None

    def _resample_to_4h(self, df: pd.DataFrame) -> pd.DataFrame:
        """Resample 1H bars to 4H candles anchored to the US cash session.

        Yahoo 1H bars are tz-naive UTC; a plain resample buckets on midnight UTC
        and straddles the session. Anchoring buckets to ~09:30 ET (13:30 UTC)
        lines them up with what a trader sees on a 4H chart. DST is ignored
        (an acceptable approximation for charting). Mirrors MTFEngine's resampler.
        """
        return (
            df.resample(
                "4h", origin="start_day", offset=pd.Timedelta(hours=13, minutes=30)
            )
            .agg(
                {
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                }
            )
            .dropna()
        )
