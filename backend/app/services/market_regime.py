"""Broad-market regime gate for SELL alerts.

Backtest (Jan 2020→2026) finding: sell-at-top signals only pay off when the
market is actually falling — SELL was right ~80% of the time in the 2022 bear and
~61% in the 2026 pullback, but only ~28% in the 2025 bull. So SELL alerts are
gated to a WEAK regime: SPY below its 200-EMA. In an uptrend they are suppressed.

The check fails CLOSED (returns False → SELL suppressed) so a data hiccup can
never spam sells.
"""
import logging
from typing import Optional

import pandas as pd

from app.services.market_data import MarketDataService

logger = logging.getLogger(__name__)

REGIME_BENCHMARK = "SPY"   # S&P 500 ETF — proxy for the US market
_EMA_SPAN = 200


def is_risk_off_from_df(df: Optional[pd.DataFrame]) -> bool:
    """True when the benchmark's last close is below its 200-EMA (weak regime)."""
    if df is None or "close" not in df or len(df) < _EMA_SPAN:
        return False
    close = df["close"]
    ema = close.ewm(span=_EMA_SPAN, adjust=False).mean()
    return bool(close.iloc[-1] < ema.iloc[-1])


async def us_market_risk_off(market_data: MarketDataService) -> bool:
    """True when the US market (SPY) is in a weak/bear regime (below its 200-EMA).

    Used to gate SELL alerts for US symbols. Fails closed (False) on any error.
    """
    try:
        # 2y of daily bars so the 200-EMA is well-seeded.
        df = await market_data.fetch_ohlcv(REGIME_BENCHMARK, interval="1d", period="2y")
        return is_risk_off_from_df(df)
    except Exception as e:
        logger.warning(f"[regime] SPY regime check failed, treating as risk-on: {e}")
        return False
