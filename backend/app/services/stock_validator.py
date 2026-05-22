import httpx


async def validate_stock_symbol(symbol: str) -> bool:
    """Check if a stock symbol exists by querying Yahoo Finance.

    Args:
        symbol: Stock ticker symbol (e.g., 'AAPL')

    Returns:
        True if the symbol is valid and has market data
    """
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        params = {"interval": "1d", "range": "1d"}

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                params=params,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=5.0,
            )

        if response.status_code != 200:
            return False

        data = response.json()
        result = data.get("chart", {}).get("result")

        return result is not None and len(result) > 0

    except Exception:
        return False
