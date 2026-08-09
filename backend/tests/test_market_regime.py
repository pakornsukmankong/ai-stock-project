"""Broad-market regime gate — SPY below its 200-EMA = weak (SELL allowed)."""
import numpy as np
import pandas as pd

from app.services.market_regime import is_risk_off_from_df


def _df(closes):
    idx = pd.date_range("2020-01-01", periods=len(closes), freq="D")
    return pd.DataFrame({"close": closes}, index=idx)


def test_downtrend_is_risk_off():
    # 300 bars trending DOWN → last close well below the 200-EMA.
    closes = np.linspace(300, 100, 300)
    assert is_risk_off_from_df(_df(closes)) is True


def test_uptrend_is_not_risk_off():
    # 300 bars trending UP → last close above the 200-EMA.
    closes = np.linspace(100, 300, 300)
    assert is_risk_off_from_df(_df(closes)) is False


def test_insufficient_history_fails_closed():
    # Fewer than 200 bars → cannot judge → not risk-off (SELL stays suppressed).
    assert is_risk_off_from_df(_df(np.linspace(300, 100, 50))) is False
    assert is_risk_off_from_df(None) is False
