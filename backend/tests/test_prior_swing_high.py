"""The take-profit target must sit above the entry price."""
import numpy as np
import pandas as pd

from app.services.indicator_engine import IndicatorEngine, MIN_TARGET_UPSIDE


def _df(closes):
    closes = np.asarray(closes, dtype=float)
    idx = pd.date_range("2025-01-01", periods=len(closes), freq="D")
    return pd.DataFrame({"open": closes, "high": closes + 1, "low": closes - 1,
                         "close": closes, "volume": 1e6}, index=idx)


def _series(*legs):
    return np.concatenate([np.linspace(a, b, n) for a, b, n in legs])


def test_target_is_the_high_the_dip_fell_from():
    # rise to 150, fall back to 130 -> target is the 150 peak (high = 151)
    ind = IndicatorEngine().calculate(_df(_series((100, 150, 200), (150, 130, 40))))
    assert ind.prior_swing_high == 151.0
    assert ind.prior_swing_high >= ind.current_price * (1 + MIN_TARGET_UPSIDE)


def test_a_broken_swing_high_is_not_used_as_the_target():
    """Price has already cleared the latest pivot (the TSM case): the target must
    come from a higher prior high, never from the pivot below price."""
    closes = _series((100, 160, 150), (160, 120, 40), (120, 130, 20), (130, 125, 10), (125, 140, 20))
    ind = IndicatorEngine().calculate(_df(closes))
    assert ind.current_price == 140.0
    assert ind.prior_swing_high == 161.0        # the 160 peak, not the 130 one


def test_no_target_when_price_is_at_the_top_of_the_window():
    ind = IndicatorEngine().calculate(_df(np.linspace(100, 200, 260)))
    assert ind.prior_swing_high == 0.0
