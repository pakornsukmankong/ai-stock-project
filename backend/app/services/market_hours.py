from datetime import datetime, time
import pytz

# US Eastern Time (NYSE/NASDAQ)
ET = pytz.timezone("US/Eastern")

# Market hours: Mon-Fri, 9:30 AM - 4:00 PM ET
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)

# Extended: include pre-market (4:00 AM) and after-hours (8:00 PM)
PRE_MARKET_OPEN = time(4, 0)
AFTER_HOURS_CLOSE = time(20, 0)


def is_market_open(include_extended: bool = True) -> bool:
    """Check if the US stock market is currently open.

    Args:
        include_extended: If True, includes pre-market and after-hours.

    Returns:
        True if market is open (or in extended hours if enabled).
    """
    now_et = datetime.now(ET)

    # Weekend check (Saturday=5, Sunday=6)
    if now_et.weekday() >= 5:
        return False

    current_time = now_et.time()

    if include_extended:
        return PRE_MARKET_OPEN <= current_time <= AFTER_HOURS_CLOSE
    else:
        return MARKET_OPEN <= current_time <= MARKET_CLOSE


def get_market_status() -> dict:
    """Get detailed market status info."""
    now_et = datetime.now(ET)
    current_time = now_et.time()
    is_weekend = now_et.weekday() >= 5

    if is_weekend:
        status = "closed"
        reason = "Weekend"
    elif current_time < PRE_MARKET_OPEN:
        status = "closed"
        reason = "Before pre-market"
    elif current_time < MARKET_OPEN:
        status = "pre-market"
        reason = "Pre-market session"
    elif current_time <= MARKET_CLOSE:
        status = "open"
        reason = "Regular trading hours"
    elif current_time <= AFTER_HOURS_CLOSE:
        status = "after-hours"
        reason = "After-hours session"
    else:
        status = "closed"
        reason = "After market close"

    return {
        "status": status,
        "reason": reason,
        "current_time_et": now_et.strftime("%H:%M ET"),
        "day": now_et.strftime("%A"),
        "is_trading": status in ("open", "pre-market", "after-hours"),
    }
