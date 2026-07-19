"""Edge-trigger state management in _analyze_symbol.

The rule: a signal's "edge" (inactive -> active transition) is consumed only
once the AI has actually reached a decision. If the AI call fails, the edge must
survive so the next cycle retries — otherwise an AI outage silently swallows
every buy signal and leaves it stuck as "still active".
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


def _build_scheduler(monkeypatch, *, analysis):
    """A scheduler whose pipeline yields a buy signal and the given AI result."""
    sch = AnalysisScheduler()

    monkeypatch.setattr(sch.market_data, "fetch_ohlcv", AsyncMock(return_value=_FakeDF()))
    monkeypatch.setattr(sch.indicator_engine, "calculate", lambda df: _INDICATORS)
    monkeypatch.setattr(sch.mtf_engine, "analyze", AsyncMock(return_value=None))
    monkeypatch.setattr(sch.signal_engine, "evaluate_with_mtf", lambda i, m: _signal(True))
    monkeypatch.setattr(sch, "_build_weekly_candles", lambda df: [])
    monkeypatch.setattr(sch, "_build_recent_daily_candles", lambda df: [])
    monkeypatch.setattr(sch.ai_service, "analyze", AsyncMock(return_value=analysis))
    return sch


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


@pytest.mark.asyncio
async def test_ai_failure_does_not_consume_the_edge(monkeypatch):
    sch = _build_scheduler(monkeypatch, analysis=None)  # AI down
    pending = {}

    await sch._analyze_symbol("AMZN", pending, {"AMZN": []}, set())

    # Edge preserved -> next cycle still sees a fresh edge and retries.
    assert sch._signal_active.get("AMZN") is not True
    assert pending == {}


@pytest.mark.asyncio
async def test_ai_hold_consumes_the_edge_without_notifying(monkeypatch):
    hold = SimpleNamespace(action="HOLD", confidence="Low", summary="", reasons=[])
    sch = _build_scheduler(monkeypatch, analysis=hold)
    pending = {}

    await sch._analyze_symbol("AMZN", pending, {"AMZN": []}, set())

    # A decision was reached, so don't re-ask every cycle — but no alert.
    assert sch._signal_active["AMZN"] is True
    assert pending == {}


@pytest.mark.asyncio
async def test_ai_buy_consumes_edge_and_queues_alert(monkeypatch):
    buy = SimpleNamespace(action="BUY", confidence="High", summary="dip", reasons=["x"])
    sch = _build_scheduler(monkeypatch, analysis=buy)
    watchers = {"AMZN": [{"user_id": "u1", "line_user_id": "U1", "min_confidence": "All"}]}
    pending = {}

    await sch._analyze_symbol("AMZN", pending, watchers, set())

    assert sch._signal_active["AMZN"] is True
    assert "u1" in pending
    assert pending["u1"]["items"][0]["symbol"] == "AMZN"


@pytest.mark.asyncio
async def test_edge_retried_next_cycle_after_ai_recovers(monkeypatch):
    """Reproduces the outage: fail, then succeed on the retry."""
    sch = _build_scheduler(monkeypatch, analysis=None)
    watchers = {"AMZN": [{"user_id": "u1", "line_user_id": "U1", "min_confidence": "All"}]}

    # Cycle 1: AI down -> edge not consumed, nothing queued.
    await sch._analyze_symbol("AMZN", {}, watchers, set())
    assert sch._signal_active.get("AMZN") is not True

    # Cycle 2: AI recovers -> the still-active signal alerts.
    buy = SimpleNamespace(action="BUY", confidence="High", summary="dip", reasons=["x"])
    sch.ai_service.analyze = AsyncMock(return_value=buy)
    pending = {}
    await sch._analyze_symbol("AMZN", pending, watchers, set())

    assert sch._signal_active["AMZN"] is True
    assert "u1" in pending
