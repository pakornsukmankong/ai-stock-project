"""News + fundamentals context to enrich the AI's stock analysis.

Fetched only when a signal reaches the AI (i.e. after the rule gate passes and
the analysis cache misses), so external calls stay bounded. Cached per symbol for
a few hours. Everything fails OPEN — on any error the AI simply analyzes on the
technical indicators alone.

Sources:
- Fundamentals + upcoming earnings: Finnhub (needs FINNHUB_API_KEY; free tier).
- News: Finnhub company-news when a key is set (symbol-specific), otherwise the
  key-free Yahoo search endpoint as a fallback so news always works.
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.config import get_settings
from app.core.http_client import get_http_client

logger = logging.getLogger(__name__)

_FINNHUB = "https://finnhub.io/api/v1"
_YAHOO_SEARCH = "https://query1.finance.yahoo.com/v1/finance/search"

_CACHE_TTL_SECONDS = 3 * 3600   # 3h — news is the fastest-moving part
_MAX_NEWS = 5
_NEWS_LOOKBACK_DAYS = 7


@dataclass
class CompanyContext:
    """Compact, prompt-ready company context. Any field may be empty."""
    news: list = field(default_factory=list)          # [{"title","source","date"}]
    fundamentals: dict = field(default_factory=dict)  # compact metric -> value
    next_earnings: Optional[str] = None               # ISO date "YYYY-MM-DD"
    days_to_earnings: Optional[int] = None

    @property
    def is_empty(self) -> bool:
        return not self.news and not self.fundamentals and not self.next_earnings


class CompanyContextService:
    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, CompanyContext]] = {}
        self._lock = asyncio.Lock()

    async def get_context(self, symbol: str) -> CompanyContext:
        """Return cached context, or fetch it. Never raises."""
        now = time.monotonic()
        async with self._lock:
            hit = self._cache.get(symbol)
            if hit and now - hit[0] < _CACHE_TTL_SECONDS:
                return hit[1]

        ctx = await self._fetch(symbol)

        async with self._lock:
            self._cache[symbol] = (now, ctx)
        return ctx

    async def _fetch(self, symbol: str) -> CompanyContext:
        settings = get_settings()
        key = settings.finnhub_api_key

        ctx = CompanyContext()
        try:
            if key:
                ctx.news = await self._finnhub_news(symbol, key)
                ctx.fundamentals = await self._finnhub_fundamentals(symbol, key)
                ctx.next_earnings, ctx.days_to_earnings = await self._finnhub_earnings(symbol, key)
            if not ctx.news:
                # No key, or Finnhub returned nothing — fall back to free Yahoo news.
                ctx.news = await self._yahoo_news(symbol)
        except Exception as e:
            logger.warning(f"[context] {symbol}: failed to fetch company context: {e}")
        return ctx

    # ------------------------------------------------------------------ #
    # Finnhub
    # ------------------------------------------------------------------ #
    async def _finnhub_news(self, symbol: str, key: str) -> list:
        client = get_http_client()
        today = datetime.now(timezone.utc).date()
        params = {
            "symbol": symbol.upper(),
            "from": (today - timedelta(days=_NEWS_LOOKBACK_DAYS)).isoformat(),
            "to": today.isoformat(),
            "token": key,
        }
        r = await client.get(f"{_FINNHUB}/company-news", params=params, timeout=10.0)
        r.raise_for_status()
        items = r.json() if isinstance(r.json(), list) else []
        # Newest first.
        items.sort(key=lambda n: n.get("datetime", 0), reverse=True)
        out = []
        for n in items[:_MAX_NEWS]:
            ts = n.get("datetime")
            date = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d") if ts else ""
            headline = (n.get("headline") or "").strip()
            if headline:
                out.append({"title": headline[:160], "source": n.get("source", ""), "date": date})
        return out

    async def _finnhub_fundamentals(self, symbol: str, key: str) -> dict:
        client = get_http_client()
        r = await client.get(
            f"{_FINNHUB}/stock/metric",
            params={"symbol": symbol.upper(), "metric": "all", "token": key},
            timeout=10.0,
        )
        r.raise_for_status()
        m = (r.json() or {}).get("metric", {}) or {}

        def num(key_name, digits=1, suffix=""):
            v = m.get(key_name)
            if v is None:
                return None
            try:
                return f"{float(v):.{digits}f}{suffix}"
            except (TypeError, ValueError):
                return None

        # Only keep fields that are present — an ETF or thin ticker yields few.
        out = {}
        for label, key_name, digits, suffix in (
            ("P/E (TTM)", "peTTM", 1, ""),
            ("EPS growth 5y", "epsGrowth5Y", 1, "%"),
            ("Revenue growth (TTM YoY)", "revenueGrowthTTMYoy", 1, "%"),
            ("Net margin (TTM)", "netProfitMarginTTM", 1, "%"),
            ("ROE (TTM)", "roeTTM", 1, "%"),
            ("Debt/Equity", "totalDebt/totalEquityQuarterly", 2, ""),
        ):
            val = num(key_name, digits, suffix)
            if val is not None:
                out[label] = val
        return out

    async def _finnhub_earnings(self, symbol: str, key: str):
        client = get_http_client()
        today = datetime.now(timezone.utc).date()
        params = {
            "symbol": symbol.upper(),
            "from": today.isoformat(),
            "to": (today + timedelta(days=90)).isoformat(),
            "token": key,
        }
        r = await client.get(f"{_FINNHUB}/calendar/earnings", params=params, timeout=10.0)
        r.raise_for_status()
        cal = (r.json() or {}).get("earningsCalendar", []) or []
        dates = sorted(e["date"] for e in cal if e.get("date"))
        if not dates:
            return None, None
        nxt = dates[0]
        try:
            d = datetime.strptime(nxt, "%Y-%m-%d").date()
            # Rough trading-day estimate: calendar days * 5/7.
            days = max(0, int((d - today).days * 5 / 7))
        except ValueError:
            days = None
        return nxt, days

    # ------------------------------------------------------------------ #
    # Yahoo (key-free news fallback)
    # ------------------------------------------------------------------ #
    async def _yahoo_news(self, symbol: str) -> list:
        client = get_http_client()
        r = await client.get(
            _YAHOO_SEARCH,
            params={"q": symbol.upper(), "newsCount": _MAX_NEWS, "quotesCount": 0},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10.0,
        )
        r.raise_for_status()
        items = (r.json() or {}).get("news", []) or []
        out = []
        for n in items[:_MAX_NEWS]:
            title = (n.get("title") or "").strip()
            ts = n.get("providerPublishTime")
            date = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d") if ts else ""
            if title:
                out.append({"title": title[:160], "source": n.get("publisher", ""), "date": date})
        return out
