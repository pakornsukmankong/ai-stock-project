"""Market registry tests — symbol routing, session hours, currency/time labels.

All times are built as timezone-aware UTC and a fixed winter Wednesday
(2026-01-14) so US Eastern is EST (UTC-5) and results are deterministic.
Asia/Bangkok has no DST (UTC+7 year-round).
"""
from datetime import datetime, timezone

from app.services import markets as m


def _utc(hour, minute=0, day=14):
    # 2026-01-14 is a Wednesday; 2026-01-17 is a Saturday.
    return datetime(2026, 1, day, hour, minute, tzinfo=timezone.utc)


def test_symbol_routing():
    assert m.market_for_symbol("AAPL").code == "US"
    assert m.market_for_symbol("brk.b").code == "US"
    assert m.market_for_symbol("PTT.BK").code == "SET"
    assert m.market_for_symbol("ptt.bk").code == "SET"  # case-insensitive


def test_us_session_hours():
    # US regular 9:30–16:00 ET = 14:30–21:00 UTC in winter.
    assert m.is_market_open(m.US_MARKET, _utc(15, 0)) is True
    assert m.is_market_open(m.US_MARKET, _utc(13, 0)) is False   # before open
    assert m.is_market_open(m.US_MARKET, _utc(21, 30)) is False  # after close


def test_set_session_hours_and_lunch_break():
    # SET 10:00–12:30 & 14:30–16:30 ICT = 03:00–05:30 & 07:30–09:30 UTC.
    assert m.is_market_open(m.SET_MARKET, _utc(4, 0)) is True    # morning
    assert m.is_market_open(m.SET_MARKET, _utc(8, 0)) is True    # afternoon
    assert m.is_market_open(m.SET_MARKET, _utc(6, 0)) is False   # lunch break
    assert m.is_market_open(m.SET_MARKET, _utc(2, 0)) is False   # before open


def test_markets_do_not_overlap():
    # During SET morning, US is closed; during US session, SET is closed.
    assert m.open_market_codes(_utc(4, 0)) == {"SET"}
    assert m.open_market_codes(_utc(15, 0)) == {"US"}
    # Lunch break + US closed = nothing open.
    assert m.open_market_codes(_utc(6, 0)) == set()
    assert m.any_market_open(_utc(6, 0)) is False


def test_weekend_closed():
    # Saturday 2026-01-17, a normally-open UTC hour for both.
    assert m.is_market_open(m.US_MARKET, _utc(15, 0, day=17)) is False
    assert m.is_market_open(m.SET_MARKET, _utc(4, 0, day=17)) is False


def test_currency_and_time_label():
    assert m.US_MARKET.currency_symbol == "$"
    assert m.SET_MARKET.currency_symbol == "฿"
    # SET morning 04:00 UTC = 11:00 ICT.
    label = m.market_local_time(m.SET_MARKET, _utc(4, 0))
    assert "11:00 ICT" in label
    assert "2026" in label
