from fastapi import APIRouter, HTTPException, Depends, Request
from app.core.database import get_supabase_client
from app.core.auth import get_current_user_id
from app.schemas.stock import WatchlistStockRequest, WatchlistStockResponse
from app.services.stock_validator import validate_stock_symbol

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


@router.get("/stocks")
async def get_watchlist_stocks(user_id: str = Depends(get_current_user_id)):
    """Get all stocks in user's watchlist."""
    try:
        supabase = get_supabase_client()

        watchlist_response = (
            supabase.table("watchlists")
            .select("id")
            .eq("user_id", user_id)
            .execute()
        )

        if not watchlist_response.data:
            return {"stocks": []}

        watchlist_id = watchlist_response.data[0]["id"]

        stocks_response = (
            supabase.table("watchlist_stocks")
            .select("*")
            .eq("watchlist_id", watchlist_id)
            .order("created_at", desc=True)
            .execute()
        )

        return {"stocks": stocks_response.data}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stocks")
async def add_stock(request: WatchlistStockRequest, user_id: str = Depends(get_current_user_id)):
    """Add a stock to user's watchlist."""
    try:
        symbol = request.symbol.upper().strip()

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

        # Check if stock already exists
        existing = (
            supabase.table("watchlist_stocks")
            .select("id")
            .eq("watchlist_id", watchlist_id)
            .eq("symbol", symbol)
            .execute()
        )

        if existing.data:
            raise HTTPException(
                status_code=409,
                detail=f"{symbol} is already in your watchlist",
            )

        # Add stock
        response = (
            supabase.table("watchlist_stocks")
            .insert(
                {
                    "watchlist_id": watchlist_id,
                    "symbol": symbol,
                    "is_enabled": request.is_enabled,
                }
            )
            .execute()
        )

        return {"stock": response.data[0]}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/stocks/{symbol}")
async def remove_stock(symbol: str, user_id: str = Depends(get_current_user_id)):
    """Remove a stock from user's watchlist."""
    try:
        supabase = get_supabase_client()

        watchlist_response = (
            supabase.table("watchlists")
            .select("id")
            .eq("user_id", user_id)
            .execute()
        )

        if not watchlist_response.data:
            raise HTTPException(status_code=404, detail="Watchlist not found")

        watchlist_id = watchlist_response.data[0]["id"]

        supabase.table("watchlist_stocks").delete().eq(
            "watchlist_id", watchlist_id
        ).eq("symbol", symbol.upper()).execute()

        return {"message": f"{symbol} removed from watchlist"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/stocks/{symbol}/toggle")
async def toggle_stock(symbol: str, is_enabled: bool, user_id: str = Depends(get_current_user_id)):
    """Enable or disable tracking for a stock."""
    try:
        supabase = get_supabase_client()

        watchlist_response = (
            supabase.table("watchlists")
            .select("id")
            .eq("user_id", user_id)
            .execute()
        )

        if not watchlist_response.data:
            raise HTTPException(status_code=404, detail="Watchlist not found")

        watchlist_id = watchlist_response.data[0]["id"]

        response = (
            supabase.table("watchlist_stocks")
            .update({"is_enabled": is_enabled})
            .eq("watchlist_id", watchlist_id)
            .eq("symbol", symbol.upper())
            .execute()
        )

        return {"stock": response.data[0] if response.data else None}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _get_or_create_watchlist(supabase, user_id: str) -> str:
    """Get existing watchlist or create a new one."""
    response = (
        supabase.table("watchlists")
        .select("id")
        .eq("user_id", user_id)
        .execute()
    )

    if response.data:
        return response.data[0]["id"]

    # Ensure user exists in users table first (for foreign key)
    from app.api.user import _ensure_user_exists
    await _ensure_user_exists(supabase, user_id)

    # Create new watchlist
    new_watchlist = (
        supabase.table("watchlists")
        .insert({"user_id": user_id})
        .execute()
    )

    return new_watchlist.data[0]["id"]
