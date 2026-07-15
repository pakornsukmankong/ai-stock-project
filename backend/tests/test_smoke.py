"""Smoke tests — import safety plus the security-critical input guards.

Intentionally offline: no Supabase, OpenAI, LINE or Yahoo calls, so CI needs no
secrets. These lock in the validation/normalization behaviour added alongside
the hardening work.
"""
import pytest

from app.core.validation import is_valid_symbol, clean_symbol, clean_interval, clean_period
from app.schemas.stock import WatchlistStockRequest
from app.schemas.user import ConnectLineRequest


def test_app_imports_without_env():
    """The FastAPI app must construct without any secrets configured."""
    from app.main import app

    assert app.title == "AI Stock Alert API"
    # All six routers mounted under /api/v1 plus root/health.
    paths = {route.path for route in app.routes}
    assert "/health" in paths
    assert any(p.startswith("/api/v1/watchlist") for p in paths)


@pytest.mark.parametrize("symbol", ["AAPL", "aapl", "BRK.B", "RDS-A", " msft "])
def test_valid_symbols_accepted(symbol):
    assert is_valid_symbol(symbol)


@pytest.mark.parametrize(
    "symbol",
    ["../../v7/quote", "AAPL/../x", "A A", "toolongsymbol123", "", "AAPL;DROP"],
)
def test_malicious_symbols_rejected(symbol):
    assert not is_valid_symbol(symbol)


def test_clean_symbol_normalizes_and_raises():
    from fastapi import HTTPException

    assert clean_symbol(" aapl ") == "AAPL"
    with pytest.raises(HTTPException):
        clean_symbol("../evil")


def test_interval_period_whitelist():
    from fastapi import HTTPException

    assert clean_interval("1d") == "1d"
    assert clean_period("3mo") == "3mo"
    with pytest.raises(HTTPException):
        clean_interval("evil")
    with pytest.raises(HTTPException):
        clean_period("9999y")


def test_watchlist_request_normalizes_symbol():
    assert WatchlistStockRequest(symbol=" aapl ").symbol == "AAPL"
    with pytest.raises(Exception):
        WatchlistStockRequest(symbol="../evil")


def test_connect_line_requires_valid_line_id():
    ok = ConnectLineRequest(line_user_id="U" + "0" * 32)
    assert ok.line_user_id.startswith("U")
    with pytest.raises(Exception):
        ConnectLineRequest(line_user_id="not-a-line-id")


def test_rate_limiter_ignores_spoofed_forwarded_for():
    """A rotating client-supplied X-Forwarded-For must not bypass the limit."""
    from app.core.rate_limiter import RateLimiter
    from fastapi import HTTPException

    rl = RateLimiter(max_requests=3, window_seconds=60)

    class Req:
        def __init__(self, xff):
            self.headers = {"X-Forwarded-For": xff}
            self.client = type("C", (), {"host": "203.0.113.7"})()

    blocked_at = None
    for i in range(10):
        try:
            # trusted_proxy_hops defaults to 1 → only the rightmost hop counts,
            # so the spoofed leftmost address does not create fresh buckets.
            rl.check(Req(xff=f"1.2.3.{i}, 203.0.113.7"))
        except HTTPException:
            blocked_at = i
            break

    assert blocked_at == 3
