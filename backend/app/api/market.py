from fastapi import APIRouter, HTTPException, Depends
from app.core.auth import get_current_user_id
from app.services.market_data import MarketDataService

router = APIRouter(prefix="/market", tags=["market"])

market_data = MarketDataService()


@router.get("/chart/{symbol}")
async def get_chart_data(
    symbol: str,
    interval: str = "1d",
    period: str = "3mo",
    user_id: str = Depends(get_current_user_id),
):
    """Get OHLCV chart data for a stock symbol."""
    try:
        df = await market_data.fetch_ohlcv(
            symbol=symbol.upper(),
            interval=interval,
            period=period,
        )

        if df is None or df.empty:
            raise HTTPException(status_code=404, detail=f"No data found for {symbol}")

        # Convert to lightweight-charts format
        candles = []
        for timestamp, row in df.iterrows():
            candles.append({
                "time": int(timestamp.timestamp()),
                "open": round(row["open"], 2),
                "high": round(row["high"], 2),
                "low": round(row["low"], 2),
                "close": round(row["close"], 2),
            })

        volumes = []
        for timestamp, row in df.iterrows():
            volumes.append({
                "time": int(timestamp.timestamp()),
                "value": int(row["volume"]),
                "color": "rgba(34,197,94,0.3)" if row["close"] >= row["open"] else "rgba(239,68,68,0.3)",
            })

        return {
            "symbol": symbol.upper(),
            "candles": candles,
            "volumes": volumes,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
