import pandas as pd
from typing import Optional

from app.core.config import get_settings
from app.core.http_client import get_http_client
from app.core.validation import is_valid_symbol


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
            interval: Data interval (1m, 5m, 15m, 1h, 1d)
            period: Data period (1d, 5d, 1mo, 3mo, 6mo, 1y)

        Returns:
            DataFrame with columns: open, high, low, close, volume
        """
        # The symbol lands in the request path, so it is validated here as well as
        # at the API boundary — this is also reachable from the scheduler and DB.
        if not is_valid_symbol(symbol):
            print(f"Refusing to fetch market data for invalid symbol: {symbol!r}")
            return None

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
            print(f"Error fetching market data for {symbol}: {e}")
            return None
