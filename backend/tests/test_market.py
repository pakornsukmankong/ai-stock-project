"""Market data tests — the 4h interval is synthesized, not fetched from Yahoo."""
import pandas as pd
import pytest

from app.services.market_data import MarketDataService


def _hourly_frame(hours: int) -> pd.DataFrame:
    idx = pd.date_range("2026-01-05 13:30", periods=hours, freq="1h")
    return pd.DataFrame(
        {
            "open": range(hours),
            "high": [v + 2 for v in range(hours)],
            "low": [v - 1 for v in range(hours)],
            "close": [v + 1 for v in range(hours)],
            "volume": [100] * hours,
        },
        index=idx,
    )


def test_resample_to_4h_aggregates_ohlcv():
    svc = MarketDataService()
    df = svc._resample_to_4h(_hourly_frame(8))

    # 8 hourly bars anchored at the session open collapse into 2 four-hour bars.
    assert len(df) == 2
    first = df.iloc[0]
    assert first["open"] == 0          # first open of the bucket
    assert first["high"] == 5          # max high across the 4 hours
    assert first["low"] == -1          # min low
    assert first["close"] == 4         # last close
    assert first["volume"] == 400      # summed volume


@pytest.mark.asyncio
async def test_fetch_ohlcv_4h_resamples_from_1h(monkeypatch):
    svc = MarketDataService()
    captured = {}

    async def fake_raw(symbol, interval, period):
        captured["interval"] = interval
        return _hourly_frame(8)

    monkeypatch.setattr(svc, "_fetch_raw", fake_raw)

    out = await svc.fetch_ohlcv("AAPL", interval="4h", period="3mo")

    # 4h must be sourced from a 1h fetch (Yahoo has no native 4h interval).
    assert captured["interval"] == "1h"
    assert out is not None and len(out) == 2


@pytest.mark.asyncio
async def test_fetch_ohlcv_passes_native_interval_through(monkeypatch):
    svc = MarketDataService()
    captured = {}

    async def fake_raw(symbol, interval, period):
        captured["interval"] = interval
        return _hourly_frame(4)

    monkeypatch.setattr(svc, "_fetch_raw", fake_raw)

    await svc.fetch_ohlcv("AAPL", interval="1d", period="1y")
    assert captured["interval"] == "1d"


@pytest.mark.asyncio
async def test_fetch_ohlcv_rejects_bad_symbol():
    svc = MarketDataService()
    assert await svc.fetch_ohlcv("../evil", interval="1d") is None
