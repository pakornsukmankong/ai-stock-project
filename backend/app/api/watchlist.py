from fastapi import APIRouter, HTTPException, Depends

from app.core.database import get_supabase_client, db
from app.core.auth import get_current_user_id
from app.core.error_monitor import monitor
from app.core.validation import clean_symbol
from app.schemas.stock import WatchlistStockRequest
from app.services.stock_validator import validate_stock_symbol

router = APIRouter(prefix="/watchlist", tags=["watchlist"])

# A single user's watchlist drives scheduled Yahoo fetches and OpenAI calls, so
# it is bounded.
MAX_STOCKS_PER_WATCHLIST = 50


@router.get("/stocks")
async def get_watchlist_stocks(user_id: str = Depends(get_current_user_id)):
    """Get all stocks in user's watchlist."""
    try:
        supabase = get_supabase_client()

        watchlist_response = await db(
            supabase.table("watchlists").select("id").eq("user_id", user_id)
        )

        if not watchlist_response.data:
            return {"stocks": []}

        watchlist_id = watchlist_response.data[0]["id"]

        stocks_response = await db(
            supabase.table("watchlist_stocks")
            .select("*")
            .eq("watchlist_id", watchlist_id)
            .order("created_at", desc=True)
        )

        return {"stocks": stocks_response.data}

    except Exception as e:
        monitor.log_error("watchlist.list", str(e))
        raise HTTPException(status_code=500, detail="Failed to load watchlist")


@router.post("/stocks")
async def add_stock(request: WatchlistStockRequest, user_id: str = Depends(get_current_user_id)):
    """Add a stock to user's watchlist."""
    symbol = clean_symbol(request.symbol)

    try:
        # Validate symbol exists in market
        is_valid = await validate_stock_symbol(symbol)
        if not is_valid:
            raise HTTPException(
                status_code=400,
                detail=f"'{symbol}' is not a valid stock symbol",
            )

        supabase = get_supabase_client()

        # Get or create watchlist
        watchlist_id = await _get_or_create_watchlist(supabase, user_id)

        # Enforce the per-watchlist cap
        existing = await db(
            supabase.table("watchlist_stocks")
            .select("id", count="exact")
            .eq("watchlist_id", watchlist_id)
        )

        if (existing.count or 0) >= MAX_STOCKS_PER_WATCHLIST:
            raise HTTPException(
                status_code=400,
                detail=f"Watchlist is full (max {MAX_STOCKS_PER_WATCHLIST} stocks)",
            )

        duplicate = await db(
            supabase.table("watchlist_stocks")
            .select("id")
            .eq("watchlist_id", watchlist_id)
            .eq("symbol", symbol)
            .limit(1)
        )

        if duplicate.data:
            raise HTTPException(
                status_code=409,
                detail=f"{symbol} is already in your watchlist",
            )

        # Add stock
        response = await db(
            supabase.table("watchlist_stocks").insert(
                {
                    "watchlist_id": watchlist_id,
                    "symbol": symbol,
                    "is_enabled": request.is_enabled,
                }
            )
        )

        return {"stock": response.data[0]}

    except HTTPException:
        raise
    except Exception as e:
        monitor.log_error("watchlist.add", str(e))
        raise HTTPException(status_code=500, detail="Failed to add stock")


@router.delete("/stocks/{symbol}")
async def remove_stock(symbol: str, user_id: str = Depends(get_current_user_id)):
    """Remove a stock from user's watchlist."""
    ticker = clean_symbol(symbol)

    try:
        supabase = get_supabase_client()

        watchlist_response = await db(
            supabase.table("watchlists").select("id").eq("user_id", user_id)
        )

        if not watchlist_response.data:
            raise HTTPException(status_code=404, detail="Watchlist not found")

        watchlist_id = watchlist_response.data[0]["id"]

        await db(
            supabase.table("watchlist_stocks")
            .delete()
            .eq("watchlist_id", watchlist_id)
            .eq("symbol", ticker)
        )

        return {"message": f"{ticker} removed from watchlist"}

    except HTTPException:
        raise
    except Exception as e:
        monitor.log_error("watchlist.remove", str(e))
        raise HTTPException(status_code=500, detail="Failed to remove stock")


@router.patch("/stocks/{symbol}/toggle")
async def toggle_stock(symbol: str, is_enabled: bool, user_id: str = Depends(get_current_user_id)):
    """Enable or disable tracking for a stock."""
    ticker = clean_symbol(symbol)

    try:
        supabase = get_supabase_client()

        watchlist_response = await db(
            supabase.table("watchlists").select("id").eq("user_id", user_id)
        )

        if not watchlist_response.data:
            raise HTTPException(status_code=404, detail="Watchlist not found")

        watchlist_id = watchlist_response.data[0]["id"]

        response = await db(
            supabase.table("watchlist_stocks")
            .update({"is_enabled": is_enabled})
            .eq("watchlist_id", watchlist_id)
            .eq("symbol", ticker)
        )

        return {"stock": response.data[0] if response.data else None}

    except HTTPException:
        raise
    except Exception as e:
        monitor.log_error("watchlist.toggle", str(e))
        raise HTTPException(status_code=500, detail="Failed to update stock")


async def _get_or_create_watchlist(supabase, user_id: str) -> str:
    """Get existing watchlist or create a new one."""
    response = await db(
        supabase.table("watchlists").select("id").eq("user_id", user_id)
    )

    if response.data:
        return response.data[0]["id"]

    # Ensure user exists in users table first (for foreign key)
    from app.api.user import _ensure_user_exists
    await _ensure_user_exists(supabase, user_id)

    # Create new watchlist
    new_watchlist = await db(
        supabase.table("watchlists").insert({"user_id": user_id})
    )

    return new_watchlist.data[0]["id"]
