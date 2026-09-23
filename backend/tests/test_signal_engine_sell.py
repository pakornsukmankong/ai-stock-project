"""Take-profit rule: SELL when price recovers to the prior swing high.

Replaces the old "sell at the top" scoring (overbought + bearish reversal), which
backtested at 40-46% win as a top-caller and — behind its market-regime gate —
never fired once in production.
"""
from app.services.indicator_engine import IndicatorResult
from app.services.signal_engine import SignalEngine


def _ind(price, target) -> IndicatorResult:
    ind = IndicatorResult()
    ind.current_price = price
    ind.prior_swing_high = target
    return ind


def test_fires_when_price_reaches_the_prior_high():
    r = SignalEngine().evaluate_sell_with_mtf(_ind(100.0, 100.0), None)
    assert r.is_sell_signal is True
    assert r.target_high == 100.0
    assert "take-profit target reached" in r.reasons[0]


def test_fires_when_price_exceeds_the_prior_high():
    r = SignalEngine().evaluate_sell_with_mtf(_ind(105.0, 100.0), None)
    assert r.is_sell_signal is True
    assert r.pct_of_target == 105.0


def test_does_not_fire_below_the_prior_high():
    r = SignalEngine().evaluate_sell_with_mtf(_ind(92.0, 100.0), None)
    assert r.is_sell_signal is False
    assert r.pct_of_target == 92.0
    assert "92.0% of the way back" in r.reasons[0]


def test_no_target_yet_never_fires():
    """No confirmed swing high in the window -> nothing to take profit at."""
    r = SignalEngine().evaluate_sell_with_mtf(_ind(150.0, 0.0), None)
    assert r.is_sell_signal is False
    assert r.target_high == 0.0


def test_is_independent_of_overbought_readings():
    """The old rule needed RSI/divergence; the target rule must ignore them."""
    ind = _ind(101.0, 100.0)
    ind.rsi = 35.0                      # nowhere near overbought
    ind.rsi_bearish_divergence = False  # no bearish turn at all
    assert SignalEngine().evaluate_sell_with_mtf(ind, None).is_sell_signal is True
