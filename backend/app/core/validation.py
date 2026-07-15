import re

from fastapi import HTTPException

# Tickers are uppercase alphanumerics plus '.' and '-' (e.g. BRK.B, RDS-A).
# Anything else must never reach an outbound URL: symbols are interpolated into
# the Yahoo Finance path, so unconstrained input (e.g. '..%2F..%2Fv7%2Fquote')
# lets a caller redirect the request to a different endpoint.
SYMBOL_PATTERN = r"^[A-Z0-9][A-Z0-9.\-]{0,9}$"
_SYMBOL_RE = re.compile(SYMBOL_PATTERN)

# Yahoo Finance only accepts a fixed set of these; whitelist rather than forward
# whatever the client sends.
ALLOWED_INTERVALS = frozenset({"1m", "5m", "15m", "30m", "1h", "1d", "1wk", "1mo"})
ALLOWED_PERIODS = frozenset({"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "max"})


def clean_symbol(symbol: str) -> str:
    """Normalize and validate a ticker, or raise 400."""
    candidate = (symbol or "").strip().upper()
    if not _SYMBOL_RE.match(candidate):
        raise HTTPException(status_code=400, detail="Invalid stock symbol")
    return candidate


def clean_interval(interval: str) -> str:
    if interval not in ALLOWED_INTERVALS:
        raise HTTPException(status_code=400, detail="Unsupported interval")
    return interval


def clean_period(period: str) -> str:
    if period not in ALLOWED_PERIODS:
        raise HTTPException(status_code=400, detail="Unsupported period")
    return period


def is_valid_symbol(symbol: str) -> bool:
    """Non-raising variant, for internal callers (scheduler, services)."""
    return bool(_SYMBOL_RE.match((symbol or "").strip().upper()))
