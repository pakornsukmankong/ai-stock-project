"""Sell-at-the-top rule gate.

The gate fires only when the stock is overbought/extended at resistance AND a
bearish reversal turn is present. "Overbought alone" must NOT fire — strong
trends stay overbought for a long time.
"""
from app.services.indicator_engine import IndicatorResult, PivotLevels, CandlestickPattern
from app.services.signal_engine import SignalEngine


def _indicators(**overrides) -> IndicatorResult:
    """An overbought, extended-at-resistance base. Reversal flags default off so
    each test opts into the confirmation it wants."""
    ind = IndicatorResult()
    ind.current_price = 120.0
    ind.ema_9 = 118.0
    ind.ema_21 = 110.0        # price ~9% above EMA21 → very extended
    ind.ema_50 = 100.0
    ind.ema_200 = 90.0
    ind.rsi = 74.0            # overbought
    ind.stoch_k = 88.0
    ind.stoch_d = 85.0
    ind.bb_position = "above_upper"
    ind.pivot_levels = PivotLevels(pivot=115.0, r1=120.5, r2=125.0, s1=110.0, s2=105.0)
    ind.candle_patterns = CandlestickPattern()
    for k, v in overrides.items():
        setattr(ind, k, v)
    return ind


def test_overbought_alone_does_not_fire():
    """No bearish turn → HOLD, even though it is overbought and extended."""
    engine = SignalEngine()
    result = engine.evaluate_sell_with_mtf(_indicators(), None)
    assert result.has_confirmation is False
    assert result.is_sell_signal is False


def test_overbought_plus_bearish_divergence_fires():
    engine = SignalEngine()
    ind = _indicators(rsi_bearish_divergence=True)
    result = engine.evaluate_sell_with_mtf(ind, None)
    assert result.has_confirmation is True
    assert result.total_score >= 60
    assert result.is_sell_signal is True


def test_macd_bearish_cross_is_a_valid_confirmation():
    engine = SignalEngine()
    ind = _indicators(macd_bearish_cross=True)
    result = engine.evaluate_sell_with_mtf(ind, None)
    assert result.is_sell_signal is True


def test_bearish_candle_is_a_valid_confirmation():
    engine = SignalEngine()
    patterns = CandlestickPattern()
    patterns.shooting_star = True
    ind = _indicators(candle_patterns=patterns)
    result = engine.evaluate_sell_with_mtf(ind, None)
    assert result.has_confirmation is True
    assert result.is_sell_signal is True


def test_not_a_top_does_not_fire_even_with_bearish_signal():
    """A mid-range, non-overbought stock with a bearish flicker scores too low."""
    engine = SignalEngine()
    ind = _indicators(
        current_price=95.0, ema_9=95.0, ema_21=95.0, rsi=48.0, stoch_k=45.0,
        bb_position="middle", macd_bearish_cross=True,
        pivot_levels=PivotLevels(pivot=95.0, r1=105.0, r2=110.0, s1=90.0, s2=85.0),
    )
    result = engine.evaluate_sell_with_mtf(ind, None)
    assert result.is_sell_signal is False
