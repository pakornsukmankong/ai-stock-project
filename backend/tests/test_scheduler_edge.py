"""Signal → AI → alert flow in _analyze_symbol.

Edge-triggering was removed: a persistently-active signal used to be locked out
after a single AI HOLD and never re-evaluated (strong-uptrend symbols stay a
"dip buy candidate" for days). Now every active signal is sent to the AI each
cycle; the analysis cache bounds cost and the 24h cooldown bounds alert spam.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.scheduler import AnalysisScheduler


def _signal(is_buy=True):
    return SimpleNamespace(
        is_buy_signal=is_buy,
        total_score=70,
        mtf_adjusted_score=70,
        mtf_bonus=0,
        mtf_penalty=0,
        mtf_confluence="aligned",
        reasons=["dip in uptrend"],
    )


def _no_sell():
    """A non-firing sell result, so these buy-focused tests never take the
    SELL branch."""
    return SimpleNamespace(
        is_sell_signal=False,
        total_score=0,
        reasons=[],
        mtf_confluence="n/a",
    )


class _FakeDF:
    empty = False


_INDICATORS = SimpleNamespace(
    current_price=100.0, ema_9=1.0, ema_21=1.0, ema_50=1.0, ema_200=1.0,
    macd_value=0.0, macd_signal=0.0, macd_histogram=0.0,
    supertrend_direction="bullish", supertrend_value=1.0,
    rsi=45.0, rsi_state="neutral", stoch_k=20.0, stoch_d=25.0,
    atr=1.0, bb_upper=1.0, bb_middle=1.0, bb_lower=1.0, bb_position="lower",
    current_volume=100.0, avg_volume=100.0,
    pivot_levels=SimpleNamespace(pivot=1.0, r1=1.0, r2=1.0, s1=1.0, s2=1.0),
    candle_patterns=SimpleNamespace(get_detected=lambda: []),
)


def _build_scheduler(monkeypatch, *, analysis, is_buy=True):
    sch = AnalysisScheduler()
    monkeypatch.setattr(sch.market_data, "fetch_ohlcv", AsyncMock(return_value=_FakeDF()))
    monkeypatch.setattr(sch.indicator_engine, "calculate", lambda df: _INDICATORS)
    monkeypatch.setattr(sch.mtf_engine, "analyze", AsyncMock(return_value=None))
    monkeypatch.setattr(sch.signal_engine, "evaluate_with_mtf", lambda i, m: _signal(is_buy))
    monkeypatch.setattr(sch.signal_engine, "evaluate_sell_with_mtf", lambda i, m: _no_sell())
    monkeypatch.setattr(sch, "_build_weekly_candles", lambda df: [])
    monkeypatch.setattr(sch, "_build_recent_daily_candles", lambda df: [])
    monkeypatch.setattr(sch.ai_service, "analyze", AsyncMock(return_value=analysis))
    return sch


_WATCHERS = {
    "AMZN": [
        {
            "user_id": "u1",
            "line_user_id": "U1",
            "min_confidence": "All",
            "notify_buy": True,
            "notify_sell": False,
        }
    ]
}


@pytest.mark.asyncio
async def test_ai_buy_queues_alert(monkeypatch):
    buy = SimpleNamespace(action="BUY", confidence="High", summary="dip", reasons=["x"])
    sch = _build_scheduler(monkeypatch, analysis=buy)
    pending = {}

    await sch._analyze_symbol("AMZN", pending, _WATCHERS, set())

    assert "u1" in pending
    assert pending["u1"]["items"][0]["symbol"] == "AMZN"


@pytest.mark.asyncio
async def test_ai_hold_does_not_alert(monkeypatch):
    hold = SimpleNamespace(action="HOLD", confidence="Low", summary="", reasons=[])
    sch = _build_scheduler(monkeypatch, analysis=hold)
    pending = {}

    await sch._analyze_symbol("AMZN", pending, _WATCHERS, set())
    assert pending == {}


@pytest.mark.asyncio
async def test_persistent_hold_is_re_evaluated_every_cycle(monkeypatch):
    """The core fix: a still-active signal is NOT locked out after one HOLD."""
    hold = SimpleNamespace(action="HOLD", confidence="Low", summary="", reasons=[])
    sch = _build_scheduler(monkeypatch, analysis=hold)

    # Three consecutive cycles, signal stays active the whole time.
    for _ in range(3):
        await sch._analyze_symbol("AMZN", {}, _WATCHERS, set())

    # The AI was consulted every cycle (old code would have skipped after #1).
    assert sch.ai_service.analyze.await_count == 3


@pytest.mark.asyncio
async def test_hold_flips_to_buy_and_alerts(monkeypatch):
    """A symbol the AI held earlier still alerts once its verdict turns BUY."""
    hold = SimpleNamespace(action="HOLD", confidence="Low", summary="", reasons=[])
    sch = _build_scheduler(monkeypatch, analysis=hold)

    await sch._analyze_symbol("AMZN", {}, _WATCHERS, set())  # HOLD, no alert

    buy = SimpleNamespace(action="BUY", confidence="High", summary="dip", reasons=["x"])
    sch.ai_service.analyze = AsyncMock(return_value=buy)
    pending = {}
    await sch._analyze_symbol("AMZN", pending, _WATCHERS, set())

    assert "u1" in pending  # not locked out — alerts on the flip


@pytest.mark.asyncio
async def test_cooldown_blocks_repeat_alert(monkeypatch):
    """With edge-trigger gone, the 24h cooldown is what prevents re-alerting."""
    buy = SimpleNamespace(action="BUY", confidence="High", summary="dip", reasons=["x"])
    sch = _build_scheduler(monkeypatch, analysis=buy)
    pending = {}

    # This user+symbol+side already alerted within the cooldown window.
    await sch._analyze_symbol("AMZN", pending, _WATCHERS, {("u1", "AMZN", "BUY")})
    assert pending == {}


def _sell(is_sell=True):
    return SimpleNamespace(
        is_sell_signal=is_sell,
        total_score=72,
        reasons=["overbought + bearish divergence"],
        mtf_confluence="n/a",
    )


def _build_sell_scheduler(monkeypatch, *, analysis):
    """Buy gate OFF, sell gate ON — exercises the SELL branch."""
    sch = AnalysisScheduler()
    monkeypatch.setattr(sch.market_data, "fetch_ohlcv", AsyncMock(return_value=_FakeDF()))
    monkeypatch.setattr(sch.indicator_engine, "calculate", lambda df: _INDICATORS)
    monkeypatch.setattr(sch.mtf_engine, "analyze", AsyncMock(return_value=None))
    monkeypatch.setattr(sch.signal_engine, "evaluate_with_mtf", lambda i, m: _signal(is_buy=False))
    monkeypatch.setattr(sch.signal_engine, "evaluate_sell_with_mtf", lambda i, m: _sell())
    monkeypatch.setattr(sch, "_build_weekly_candles", lambda df: [])
    monkeypatch.setattr(sch, "_build_recent_daily_candles", lambda df: [])
    monkeypatch.setattr(sch.ai_service, "analyze", AsyncMock(return_value=analysis))
    return sch


def _sell_watchers(notify_sell: bool):
    return {
        "AMZN": [
            {
                "user_id": "u1",
                "line_user_id": "U1",
                "min_confidence": "All",
                "notify_buy": True,
                "notify_sell": notify_sell,
            }
        ]
    }


@pytest.mark.asyncio
async def test_ai_sell_queues_alert_when_opted_in(monkeypatch):
    sell = SimpleNamespace(action="SELL", confidence="High", summary="top", reasons=["x"])
    sch = _build_sell_scheduler(monkeypatch, analysis=sell)
    pending = {}

    await sch._analyze_symbol("AMZN", pending, _sell_watchers(True), set())

    assert "u1" in pending
    assert pending["u1"]["items"][0]["analysis"].action == "SELL"


@pytest.mark.asyncio
async def test_sell_not_analyzed_when_no_one_opted_in(monkeypatch):
    """The sell side is opt-in: with notify_sell off, the AI is never called."""
    sell = SimpleNamespace(action="SELL", confidence="High", summary="top", reasons=["x"])
    sch = _build_sell_scheduler(monkeypatch, analysis=sell)
    pending = {}

    await sch._analyze_symbol("AMZN", pending, _sell_watchers(False), set())

    assert pending == {}
    sch.ai_service.analyze.assert_not_awaited()  # token saving


@pytest.mark.asyncio
async def test_sell_cooldown_is_independent_of_buy(monkeypatch):
    """A BUY already sent must not suppress a SELL on the same symbol."""
    sell = SimpleNamespace(action="SELL", confidence="High", summary="top", reasons=["x"])
    sch = _build_sell_scheduler(monkeypatch, analysis=sell)
    pending = {}

    # Only the BUY side is on cooldown; the SELL should still go through.
    await sch._analyze_symbol("AMZN", pending, _sell_watchers(True), {("u1", "AMZN", "BUY")})

    assert "u1" in pending


@pytest.mark.asyncio
async def test_ai_failure_does_not_alert_and_is_retried(monkeypatch):
    sch = _build_scheduler(monkeypatch, analysis=None)  # AI down
    pending = {}

    await sch._analyze_symbol("AMZN", pending, _WATCHERS, set())
    assert pending == {}
    # No verdict remembered, so the next cycle re-asks rather than caching a miss.
    assert ("AMZN", "BUY") not in sch._last_ai_action
