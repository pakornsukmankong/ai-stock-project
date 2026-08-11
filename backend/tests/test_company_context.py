"""Rendering of the news/fundamentals context block into the AI prompt."""
from app.services.ai_analysis import AIAnalysisService
from app.services.company_context import CompanyContext


def test_empty_context_renders_nothing():
    ai = AIAnalysisService()
    assert ai._build_context_section(None) == ""
    assert ai._build_context_section(CompanyContext()) == ""


def test_context_is_empty_flag():
    assert CompanyContext().is_empty is True
    assert CompanyContext(news=[{"title": "x"}]).is_empty is False
    assert CompanyContext(fundamentals={"P/E (TTM)": "40.0"}).is_empty is False
    assert CompanyContext(next_earnings="2026-10-28").is_empty is False


def test_full_context_renders_all_sections():
    ai = AIAnalysisService()
    ctx = CompanyContext(
        news=[{"title": "Amazon beats on Q2", "source": "Reuters", "date": "2026-08-10"}],
        fundamentals={"P/E (TTM)": "42.1", "Net margin (TTM)": "8.2%"},
        next_earnings="2026-10-28",
        days_to_earnings=12,
    )
    out = ai._build_context_section(ctx)
    assert "--- FUNDAMENTALS ---" in out
    assert "P/E (TTM): 42.1" in out
    assert "Next earnings: 2026-10-28 (~12 trading days away)" in out
    assert "--- RECENT NEWS (last 7 days) ---" in out
    assert "[2026-08-10] Amazon beats on Q2 (Reuters)" in out


def test_context_is_woven_into_the_full_prompt():
    """The context block must land inside the message the AI actually receives."""
    from types import SimpleNamespace

    ai = AIAnalysisService()
    # Minimal StockSignalSummary-like object with the fields the builder reads.
    s = SimpleNamespace(
        symbol="AMZN", price=278.0, score=72,
        ema_9=267.0, ema_21=257.0, ema_50=251.0, ema_200=239.0,
        macd_value=8.3, macd_signal=4.4, macd_histogram=3.9,
        supertrend_direction="bullish", supertrend_value=242.0,
        rsi=48.0, rsi_state="neutral", stoch_k=25.0, stoch_d=30.0,
        atr=9.1, bb_upper=289.0, bb_middle=253.0, bb_lower=216.0, bb_position="near_lower",
        volume_ratio=0.7, pivot=275.0, r1=277.0, r2=280.0, s1=272.0, s2=269.0,
        candle_patterns=[], signal_reasons=["divergence dip"],
        mtf_trend_alignment="not_available",
        mtf_4h_trend="n/a", mtf_1h_trend="n/a", mtf_4h_rsi=0.0, mtf_1h_rsi=0.0,
        mtf_bonus=0, mtf_penalty=0, weekly_candles=[], daily_candles=[],
    )
    ctx = CompanyContext(news=[{"title": "Amazon beats on Q2", "source": "Reuters", "date": "2026-08-10"}])
    msg = ai._build_indicator_message(s, ctx)
    assert "RECENT NEWS" in msg and "Amazon beats on Q2" in msg
    # And with no context, no news section leaks in.
    assert "RECENT NEWS" not in ai._build_indicator_message(s, None)
