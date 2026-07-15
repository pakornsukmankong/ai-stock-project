from app.core.http_client import get_http_client
from app.core.validation import is_valid_symbol


async def validate_stock_symbol(symbol: str) -> bool:
    """Check if a stock symbol exists by querying Yahoo Finance.

    Args:
        symbol: Stock ticker symbol (e.g., 'AAPL')

    Returns:
        True if the symbol is valid and has market data
    """
    if not is_valid_symbol(symbol):
        return False

    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol.upper()}"
        params = {"interval": "1d", "range": "1d"}

        client = get_http_client()
        response = await client.get(url, params=params, timeout=5.0)

        if response.status_code != 200:
            return False

        data = response.json()
        result = data.get("chart", {}).get("result")

        return result is not None and len(result) > 0

    except Exception:
        return False
