"""Daily briefing tests — market-aware type + message formatting (offline)."""
from app.services.daily_briefing import DailyBriefingService
from app.services.markets import US_MARKET, SET_MARKET


def _svc():
    # __init__ builds an AsyncOpenAI client but makes no network call here.
    return DailyBriefingService()


def test_briefing_type_is_per_market():
    assert DailyBriefingService._briefing_type(US_MARKET) == "DAILY_BRIEFING:US"
    assert DailyBriefingService._briefing_type(SET_MARKET) == "DAILY_BRIEFING:SET"


def test_message_labels_us_market():
    msg = _svc()._format_briefing_message("body", ["AAPL", "MSFT"], US_MARKET)
    assert "US Daily News Briefing" in msg
    assert "US market opens in ~1 hour (ET)" in msg
    assert "AAPL" in msg and "MSFT" in msg


def test_message_labels_set_market():
    msg = _svc()._format_briefing_message("body", ["PTT.BK"], SET_MARKET)
    assert "SET Daily News Briefing" in msg
    assert "SET market opens in ~1 hour (ICT)" in msg
    assert "PTT.BK" in msg
