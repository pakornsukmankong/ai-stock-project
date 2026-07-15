from fastapi import APIRouter, HTTPException, Depends, Query

from app.core.auth import get_current_user_id
from app.core.error_monitor import monitor
from app.core.http_client import get_http_client

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/stocks")
async def search_stocks(
    q: str = Query(..., min_length=1, max_length=40),
    user_id: str = Depends(get_current_user_id),
):
    """Search for stock symbols using Yahoo Finance autocomplete.

    Args:
        q: Search query (e.g., 'AAPL', 'Apple', 'TSLA')

    Returns:
        List of matching stock symbols with name and exchange.
    """
    query = q.strip()
    if not query:
        return {"results": []}

    try:
        url = "https://query1.finance.yahoo.com/v1/finance/search"
        params = {
            "q": query,
            "quotesCount": 8,
            "newsCount": 0,
            "listsCount": 0,
            "enableFuzzyQuery": False,
            "quotesQueryId": "tss_match_phrase_query",
        }

        client = get_http_client()
        response = await client.get(url, params=params, timeout=5.0)
        response.raise_for_status()

        data = response.json()
        quotes = data.get("quotes", [])

        results = []
        for quote in quotes:
            # Only include equities (stocks)
            quote_type = quote.get("quoteType", "")
            if quote_type not in ("EQUITY", "ETF"):
                continue

            results.append({
                "symbol": quote.get("symbol", ""),
                "name": quote.get("shortname") or quote.get("longname", ""),
                "exchange": quote.get("exchange", ""),
                "type": quote_type,
            })

        return {"results": results}

    except Exception as e:
        monitor.log_error("search.stocks", str(e))
        raise HTTPException(status_code=500, detail="Stock search failed")
