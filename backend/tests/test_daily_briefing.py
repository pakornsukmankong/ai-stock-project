"""Daily briefing tests — market-aware type + message formatting (offline)."""
import pytest

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


# --------------------------------------------------------------------------- #
# Manual ("send briefing now") trigger
# --------------------------------------------------------------------------- #
def test_manual_type_cannot_trip_the_scheduled_guard():
    # The scheduled 'already sent today' guard is GLOBAL (no user filter), so a
    # manual send must record under a distinct type — otherwise one user's
    # force-send would suppress the day's briefing for everyone else.
    assert DailyBriefingService._briefing_type(US_MARKET, manual=True) == "DAILY_BRIEFING:US:MANUAL"
    assert DailyBriefingService._briefing_type(
        US_MARKET, manual=True
    ) != DailyBriefingService._briefing_type(US_MARKET)


@pytest.mark.asyncio
async def test_send_briefing_now_requires_linked_line(monkeypatch):
    svc = _svc()

    async def no_user(_user_id):
        return None

    monkeypatch.setattr(svc, "_get_user_with_line", no_user)

    result = await svc.send_briefing_now("user-without-line")
    assert result["sent_markets"] == []
    assert "LINE account not connected" in result["detail"]


@pytest.mark.asyncio
async def test_send_briefing_now_targets_only_the_caller(monkeypatch):
    svc = _svc()
    pushes = []

    async def one_user(user_id):
        return {"id": user_id, "line_user_id": "Ucaller"}

    async def stocks(_user_id, market):
        return ["AAPL"] if market.code == "US" else ["PTT.BK"]

    async def news(_symbol):
        return ["headline"]

    async def generated(_all_news):
        return "body"

    async def push(line_user_id, _message):
        pushes.append(line_user_id)
        return True

    async def noop_db(_query):
        return None

    monkeypatch.setattr(svc, "_get_user_with_line", one_user)
    monkeypatch.setattr(svc, "_get_user_stocks", stocks)
    monkeypatch.setattr(svc, "_fetch_stock_news", news)
    monkeypatch.setattr(svc, "_generate_news_briefing", generated)
    monkeypatch.setattr(svc.line_service, "_send_push_message", push)
    monkeypatch.setattr("app.services.daily_briefing.db", noop_db)

    result = await svc.send_briefing_now("u1")

    assert result["sent_markets"] == ["US", "SET"]
    # One push per market, and never to anyone but the caller.
    assert pushes == ["Ucaller", "Ucaller"]


@pytest.mark.asyncio
async def test_send_briefing_now_reports_ai_failure_not_empty_watchlist(monkeypatch):
    """A failing AI call must not be reported as an empty watchlist."""
    svc = _svc()

    async def one_user(user_id):
        return {"id": user_id, "line_user_id": "Ucaller"}

    async def stocks(_user_id, market):
        return ["AAPL"] if market.code == "US" else []

    async def news(_symbol):
        return ["headline"]

    async def ai_down(_all_news):
        return None  # e.g. 400, or an empty reasoning-model response

    monkeypatch.setattr(svc, "_get_user_with_line", one_user)
    monkeypatch.setattr(svc, "_get_user_stocks", stocks)
    monkeypatch.setattr(svc, "_fetch_stock_news", news)
    monkeypatch.setattr(svc, "_generate_news_briefing", ai_down)

    result = await svc.send_briefing_now("u1")

    assert result["sent_markets"] == []
    assert "Could not send" in result["detail"]
    assert "AI briefing generation failed" in result["detail"]
    # SET had no stocks — a normal outcome, not reported as a failure.
    assert "SET" not in result["detail"]


@pytest.mark.asyncio
async def test_send_briefing_now_with_truly_empty_watchlist(monkeypatch):
    svc = _svc()

    async def one_user(user_id):
        return {"id": user_id, "line_user_id": "Ucaller"}

    async def no_stocks(_user_id, _market):
        return []

    monkeypatch.setattr(svc, "_get_user_with_line", one_user)
    monkeypatch.setattr(svc, "_get_user_stocks", no_stocks)

    result = await svc.send_briefing_now("u1")
    assert result["sent_markets"] == []
    assert "No enabled stocks" in result["detail"]
