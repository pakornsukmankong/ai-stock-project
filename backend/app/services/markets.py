"""Market registry: trading hours, timezone and currency per exchange.

Symbols are routed to a market by their Yahoo suffix — `.BK` = SET (Thailand),
everything else defaults to US (NYSE/NASDAQ). This lets the scheduler analyze a
symbol only while its *own* exchange is open, and lets notifications show the
right currency and local time instead of assuming US/USD.

Add a market by appending to MARKETS and _SUFFIX_MARKETS (e.g. `.HK`, `.T`).
"""
from dataclasses import dataclass
from datetime import datetime, time, timezone
from typing import Optional, Tuple

import pytz


@dataclass(frozen=True)
class Market:
    code: str                # "US", "SET"
    tz: pytz.BaseTzInfo      # exchange-local timezone
    tz_label: str            # short label for messages, e.g. "ET", "ICT"
    currency_symbol: str     # "$", "฿"
    currency: str            # "USD", "THB"
    # Local trading sessions as (open, close), inclusive. SET breaks for lunch,
    # so it has two sessions; US has one continuous regular session.
    sessions: Tuple[Tuple[time, time], ...]


ET = pytz.timezone("US/Eastern")
ICT = pytz.timezone("Asia/Bangkok")

US_MARKET = Market(
    code="US",
    tz=ET,
    tz_label="ET",
    currency_symbol="$",
    currency="USD",
    sessions=((time(9, 30), time(16, 0)),),
)
SET_MARKET = Market(
    code="SET",
    tz=ICT,
    tz_label="ICT",
    currency_symbol="฿",
    currency="THB",
    sessions=((time(10, 0), time(12, 30)), (time(14, 30), time(16, 30))),
)

MARKETS: Tuple[Market, ...] = (US_MARKET, SET_MARKET)

# Yahoo symbol suffix -> market. Extendable for other exchanges.
_SUFFIX_MARKETS = {".BK": SET_MARKET}


def market_for_symbol(symbol: str) -> Market:
    """Route a ticker to its market by suffix (defaults to US)."""
    s = (symbol or "").upper()
    for suffix, market in _SUFFIX_MARKETS.items():
        if s.endswith(suffix):
            return market
    return US_MARKET


def is_market_open(market: Market, at: Optional[datetime] = None) -> bool:
    """True if `market` is in a trading session at `at` (default: now, UTC)."""
    moment = at or datetime.now(timezone.utc)
    local = moment.astimezone(market.tz)
    if local.weekday() >= 5:  # Saturday/Sunday
        return False
    t = local.time()
    return any(open_ <= t <= close_ for open_, close_ in market.sessions)


def open_market_codes(at: Optional[datetime] = None) -> set:
    """Codes of every market currently open (e.g. {"US"} or {"SET"})."""
    return {m.code for m in MARKETS if is_market_open(m, at)}


def any_market_open(at: Optional[datetime] = None) -> bool:
    return any(is_market_open(m, at) for m in MARKETS)


def market_local_time(market: Market, at: Optional[datetime] = None) -> str:
    """Exchange-local timestamp for messages, e.g. '15 Jul 2026, 15:30 ICT'."""
    moment = at or datetime.now(timezone.utc)
    local = moment.astimezone(market.tz)
    return f"{local:%d %b %Y, %H:%M} {market.tz_label}"
