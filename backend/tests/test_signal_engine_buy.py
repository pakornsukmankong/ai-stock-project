"""Buy-on-dip reversal requirement (backtest fix C).

A dip is only buyable once it shows a leading turn-up signal — being oversold in
an uptrend is not enough on its own. This mirrors the AI dip-zone prompt at the
rule level and cuts "catching a still-falling knife" on momentum names.
"""
from app.services.indicator_engine import IndicatorResult, PivotLevels, CandlestickPattern
from app.services.signal_engine import SignalEngine


def _dip(**overrides) -> IndicatorResult:
    """An oversold dip in an intact uptrend. Reversal flags default OFF."""
    ind = IndicatorResult()
    ind.current_price = 98.0
    ind.ema_9 = 99.0
    ind.ema_21 = 99.0        # price at/just below EMA21 (pulled back)
    ind.ema_50 = 95.0
    ind.ema_200 = 85.0       # uptrend intact (EMA50 > EMA200, price > EMA200)
    ind.rsi = 38.0           # pulled back
    ind.stoch_k = 18.0
    ind.stoch_d = 22.0
    ind.bb_position = "near_lower"
    ind.current_volume = 70.0   # low-volume dip at lower BB (sellers exhausted)
    ind.avg_volume = 100.0
    ind.pivot_levels = PivotLevels(pivot=98.0, r1=104.0, r2=108.0, s1=97.0, s2=94.0)
    ind.candle_patterns = CandlestickPattern()
    for k, v in overrides.items():
        setattr(ind, k, v)
    return ind


def test_oversold_dip_without_reversal_does_not_fire():
    engine = SignalEngine()
    result = engine.evaluate(_dip())
    assert result.has_reversal is False
    assert result.is_buy_signal is False   # oversold alone is not a buy


def test_dip_with_macd_turning_up_fires():
    engine = SignalEngine()
    result = engine.evaluate(_dip(macd_turning_up=True))
    assert result.has_reversal is True
    assert result.total_score >= 60
    assert result.is_buy_signal is True


def test_dip_with_bullish_divergence_fires():
    engine = SignalEngine()
    result = engine.evaluate(_dip(rsi_bullish_divergence=True))
    assert result.is_buy_signal is True
