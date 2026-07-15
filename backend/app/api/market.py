import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends

from app.core.auth import get_current_user_id
from app.core.config import get_settings
from app.core.error_monitor import monitor
from app.core.validation import clean_symbol, clean_interval, clean_period
from app.services.market_data import MarketDataService

router = APIRouter(prefix="/market", tags=["market"])

market_data = MarketDataService()

# Chart responses are identical for every user and change at most once per bar,
# but the dashboard re-requests them on every symbol-tab switch. Cache the
# serialized payload briefly so tab-switching doesn't hammer Yahoo Finance.
_chart_cache: dict[tuple[str, str, str], tuple[float, dict]] = {}
_CACHE_MAX_ENTRIES = 200


def _cache_get(key: tuple[str, str, str]) -> Optional[dict]:
    entry = _chart_cache.get(key)
    if not entry:
        return None

    expires_at, payload = entry
    if expires_at < time.monotonic():
        _chart_cache.pop(key, None)
        return None

    return payload


def _cache_put(key: tuple[str, str, str], payload: dict) -> None:
    if len(_chart_cache) >= _CACHE_MAX_ENTRIES:
        # Drop whatever expires soonest rather than growing without bound.
        oldest = min(_chart_cache, key=lambda k: _chart_cache[k][0])
        _chart_cache.pop(oldest, None)

    ttl = get_settings().chart_cache_ttl_seconds
    _chart_cache[key] = (time.monotonic() + ttl, payload)


@router.get("/chart/{symbol}")
async def get_chart_data(
    symbol: str,
    interval: str = "1d",
    period: str = "3mo",
    user_id: str = Depends(get_current_user_id),
):
    """Get OHLCV chart data for a stock symbol."""
    ticker = clean_symbol(symbol)
    interval = clean_interval(interval)
    period = clean_period(period)

    cache_key = (ticker, interval, period)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        df = await market_data.fetch_ohlcv(
            symbol=ticker,
            interval=interval,
            period=period,
        )

        if df is None or df.empty:
            raise HTTPException(status_code=404, detail=f"No data found for {ticker}")

        # Single pass over the frame; candles and volumes share the same rows.
        candles = []
        volumes = []
        for timestamp, row in df.iterrows():
            unix_time = int(timestamp.timestamp())
            open_, close = round(row["open"], 2), round(row["close"], 2)

            candles.append({
                "time": unix_time,
                "open": open_,
                "high": round(row["high"], 2),
                "low": round(row["low"], 2),
                "close": close,
            })
            volumes.append({
                "time": unix_time,
                "value": int(row["volume"]),
                "color": "rgba(34,197,94,0.3)" if close >= open_ else "rgba(239,68,68,0.3)",
            })

        payload = {
            "symbol": ticker,
            "candles": candles,
            "volumes": volumes,
        }
        _cache_put(cache_key, payload)
        return payload

    except HTTPException:
        raise
    except Exception as e:
        monitor.log_error("market.chart", f"{ticker}: {e}")
        raise HTTPException(status_code=500, detail="Failed to load chart data")
