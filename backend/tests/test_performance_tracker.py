"""Signal-oriented performance for BUY vs SELL.

Returns are stored as signal performance, not raw price change: a BUY is right
when price rises, a SELL is right when price falls. Success is side-aware alpha
vs SPY.
"""
from datetime import datetime, timezone

from app.services.performance_tracker import PerformanceTracker


def test_signal_return_keeps_buy_sign():
    assert PerformanceTracker._signal_return(5.0, "BUY") == 5.0
    assert PerformanceTracker._signal_return(-3.0, "BUY") == -3.0


def test_signal_return_inverts_sell():
    # Price fell 4% after a SELL → a +4% good call.
    assert PerformanceTracker._signal_return(-4.0, "SELL") == 4.0
    # Price rose 2% after a SELL → a -2% bad call (sold too early).
    assert PerformanceTracker._signal_return(2.0, "SELL") == -2.0


def _sent_at():
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_beat_benchmark_no_data_falls_back_to_absolute():
    t = PerformanceTracker()
    # No benchmark → SPY treated as 0%.
    assert t._beat_benchmark(3.0, _sent_at(), None, None, "BUY") is True    # up = good buy
    assert t._beat_benchmark(-3.0, _sent_at(), None, None, "BUY") is False
    assert t._beat_benchmark(-3.0, _sent_at(), None, None, "SELL") is True  # down = good sell
    assert t._beat_benchmark(3.0, _sent_at(), None, None, "SELL") is False


def test_beat_benchmark_is_side_aware_alpha():
    import pandas as pd

    idx = pd.to_datetime(["2025-12-30", "2026-01-05"])
    spy_df = pd.DataFrame({"close": [100.0, 105.0]}, index=idx)  # SPY +5%
    spy_now = 105.0
    t = PerformanceTracker()

    # Stock +6% beats SPY +5% → good BUY, bad SELL.
    assert t._beat_benchmark(6.0, _sent_at(), spy_df, spy_now, "BUY") is True
    assert t._beat_benchmark(6.0, _sent_at(), spy_df, spy_now, "SELL") is False
    # Stock +2% lags SPY +5% → bad BUY, good SELL (right to have exited).
    assert t._beat_benchmark(2.0, _sent_at(), spy_df, spy_now, "BUY") is False
    assert t._beat_benchmark(2.0, _sent_at(), spy_df, spy_now, "SELL") is True
