"""Pairing alerts into round trips for the Performance page.

A BUY opens a position, the next SELL on that symbol closes it. The round trip —
not a fixed 1d/3d/7d window — is the unit the strategy is judged on: backtested
holdings ran ~93 trading days, far longer than a week.
"""
from app.api.alerts import _pair_round_trips


def _a(symbol, side, price, at, target=None):
    return {"stock_symbol": symbol, "signal_type": side, "alert_price": price,
            "sent_at": at, "target_high": target}


def test_buy_then_sell_closes_a_round_trip():
    # Newest-first, as the API receives it.
    rows = [
        _a("AMZN", "SELL", 120.0, "2026-05-01T00:00:00+00:00"),
        _a("AMZN", "BUY", 100.0, "2026-01-01T00:00:00+00:00", target=118.0),
    ]
    (pos,) = _pair_round_trips(rows)
    assert pos["status"] == "closed"
    assert pos["entry_price"] == 100.0 and pos["exit_price"] == 120.0
    assert pos["round_trip_return"] == 20.0
    assert pos["days_held"] == 120
    assert pos["target_high"] == 118.0


def test_unclosed_buy_stays_open():
    (pos,) = _pair_round_trips([_a("LLY", "BUY", 900.0, "2026-08-01T00:00:00+00:00", 980.0)])
    assert pos["status"] == "open"
    assert pos["round_trip_return"] is None


def test_second_buy_while_open_is_ignored():
    """One position at a time per symbol — a re-buy must not spawn a second."""
    rows = [
        _a("MU", "BUY", 110.0, "2026-03-01T00:00:00+00:00"),
        _a("MU", "BUY", 100.0, "2026-01-01T00:00:00+00:00"),
    ]
    positions = _pair_round_trips(rows)
    assert len(positions) == 1
    assert positions[0]["entry_price"] == 100.0   # the original entry is kept


def test_sell_without_an_open_buy_is_skipped():
    assert _pair_round_trips([_a("KO", "SELL", 70.0, "2026-02-01T00:00:00+00:00")]) == []


def test_losing_round_trip_is_negative():
    rows = [
        _a("TSLA", "SELL", 90.0, "2026-02-01T00:00:00+00:00"),
        _a("TSLA", "BUY", 100.0, "2026-01-01T00:00:00+00:00"),
    ]
    (pos,) = _pair_round_trips(rows)
    assert pos["round_trip_return"] == -10.0


def test_symbols_are_paired_independently():
    rows = [
        _a("B", "SELL", 55.0, "2026-04-01T00:00:00+00:00"),
        _a("A", "SELL", 110.0, "2026-03-01T00:00:00+00:00"),
        _a("B", "BUY", 50.0, "2026-02-01T00:00:00+00:00"),
        _a("A", "BUY", 100.0, "2026-01-01T00:00:00+00:00"),
    ]
    got = {p["symbol"]: p["round_trip_return"] for p in _pair_round_trips(rows)}
    assert got == {"A": 10.0, "B": 10.0}
