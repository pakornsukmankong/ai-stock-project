from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query

from app.core.database import get_supabase_client, db
from app.core.auth import get_current_user_id
from app.core.error_monitor import monitor

router = APIRouter(prefix="/alerts", tags=["alerts"])

# Cap on how many alerts the win-rate/return aggregate scans. The old code pulled
# every alert the user had ever received into memory on each page view.
STATS_SAMPLE_LIMIT = 500


@router.get("/")
async def get_alerts(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
):
    """Get paginated alert history for a user.

    Args:
        page: Page number (1-based, default 1)
        per_page: Items per page (default 20, max 100)
    """
    try:
        supabase = get_supabase_client()
        offset = (page - 1) * per_page

        # Get total count
        count_response = await db(
            supabase.table("alerts")
            .select("id", count="exact")
            .eq("user_id", user_id)
        )
        total = count_response.count or 0

        # Get paginated data
        response = await db(
            supabase.table("alerts")
            .select("*")
            .eq("user_id", user_id)
            .order("sent_at", desc=True)
            .range(offset, offset + per_page - 1)
        )

        total_pages = (total + per_page - 1) // per_page if total > 0 else 1

        return {
            "alerts": response.data,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
            },
        }

    except Exception as e:
        monitor.log_error("alerts.list", str(e))
        raise HTTPException(status_code=500, detail="Failed to load alerts")


@router.get("/stats")
async def get_alert_stats(user_id: str = Depends(get_current_user_id)):
    """Get alert statistics for today."""
    try:
        supabase = get_supabase_client()

        today_start = (
            datetime.now(timezone.utc)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .isoformat()
        )

        # count="exact" makes Postgres do the counting; the rows themselves were
        # only ever used for len().
        response = await db(
            supabase.table("alerts")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .gte("sent_at", today_start)
            .limit(1)
        )

        return {"signals_today": response.count or 0}

    except Exception as e:
        monitor.log_error("alerts.stats", str(e))
        raise HTTPException(status_code=500, detail="Failed to load alert stats")


@router.get("/performance")
async def get_performance_stats(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    signal_type: Optional[str] = Query(None),
    user_id: str = Depends(get_current_user_id),
):
    """Get paginated performance statistics for user's alerts.

    `signal_type` (BUY/SELL) filters only the listed rows + their pagination; the
    summary cards and the by-type breakdown always reflect the full picture.
    """
    try:
        supabase = get_supabase_client()
        offset = (page - 1) * per_page
        side_filter = signal_type.upper() if signal_type and signal_type.upper() in ("BUY", "SELL") else None

        # Overall count (both sides) — drives the "total alerts" card.
        count_response = await db(
            supabase.table("alerts")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .not_.is_("alert_price", "null")
        )
        total = count_response.count or 0

        # Filtered count — drives pagination for the (optionally filtered) table.
        if side_filter:
            filtered_count_response = await db(
                supabase.table("alerts")
                .select("id", count="exact")
                .eq("user_id", user_id)
                .eq("signal_type", side_filter)
                .not_.is_("alert_price", "null")
            )
            filtered_total = filtered_count_response.count or 0
        else:
            filtered_total = total

        # Get paginated data (optionally filtered by side).
        data_query = (
            supabase.table("alerts")
            .select(
                "stock_symbol, signal_type, alert_price, target_high, price_after_1d, "
                "price_after_3d, price_after_7d, return_1d, return_3d, return_7d, "
                "is_successful, sent_at, confidence"
            )
            .eq("user_id", user_id)
            .not_.is_("alert_price", "null")
        )
        if side_filter:
            data_query = data_query.eq("signal_type", side_filter)
        response = await db(
            data_query.order("sent_at", desc=True).range(offset, offset + per_page - 1)
        )

        alerts_data = response.data

        # Overall stats, computed over the most recent STATS_SAMPLE_LIMIT alerts
        # rather than the user's entire (unbounded) history. Returns are stored as
        # signal performance (SELL inverted), so BUY and SELL aggregate together.
        all_response = await db(
            supabase.table("alerts")
            .select("stock_symbol, signal_type, alert_price, target_high, "
                    "is_successful, return_7d, sent_at")
            .eq("user_id", user_id)
            .not_.is_("alert_price", "null")
            .order("sent_at", desc=True)
            .limit(STATS_SAMPLE_LIMIT)
        )
        all_data = all_response.data

        tracked = [a for a in all_data if a.get("is_successful") is not None]
        successful = [a for a in tracked if a["is_successful"]]
        win_rate = (len(successful) / len(tracked) * 100) if tracked else 0

        avg_return_7d = 0
        returns_7d = [a["return_7d"] for a in all_data if a.get("return_7d") is not None]
        if returns_7d:
            avg_return_7d = sum(returns_7d) / len(returns_7d)

        # ---- Round trips -------------------------------------------------
        # A BUY opens a position; the next SELL on that symbol closes it. This is
        # the unit the strategy is actually judged on: the 1d/3d/7d windows are
        # far shorter than a real holding period (~93 trading days in backtest),
        # so on their own they say little about whether a signal worked.
        positions = _pair_round_trips(all_data)

        # index by (symbol, sent_at) so listed rows can look up their position
        by_entry = {(p["symbol"], p["entry_at"]): p for p in positions}
        by_exit = {(p["symbol"], p["exit_at"]): p for p in positions if p["exit_at"]}

        for row in alerts_data:
            key = (row["stock_symbol"], row["sent_at"])
            pos = by_entry.get(key) if row.get("signal_type") == "BUY" else by_exit.get(key)
            if not pos:
                row["position_status"] = None
                continue
            row["position_status"] = pos["status"]
            row["entry_price"] = pos["entry_price"]
            row["exit_price"] = pos["exit_price"]
            row["round_trip_return"] = pos["round_trip_return"]
            row["days_held"] = pos["days_held"]
            if row.get("target_high") is None:
                row["target_high"] = pos["target_high"]

        closed = [p for p in positions if p["status"] == "closed"]
        open_positions = [p for p in positions if p["status"] == "open"]
        rt_returns = [p["round_trip_return"] for p in closed if p["round_trip_return"] is not None]
        round_trip = {
            "closed": len(closed),
            "open": len(open_positions),
            "win_rate": round(
                sum(1 for r in rt_returns if r > 0) / len(rt_returns) * 100, 1
            ) if rt_returns else 0,
            "avg_return": round(sum(rt_returns) / len(rt_returns), 2) if rt_returns else 0,
        }

        # Per-side breakdown so the UI can show BUY vs SELL win rates separately.
        by_type = {}
        for side in ("BUY", "SELL"):
            side_tracked = [a for a in tracked if a.get("signal_type", "BUY") == side]
            side_success = [a for a in side_tracked if a["is_successful"]]
            by_type[side] = {
                "tracked": len(side_tracked),
                "successful": len(side_success),
                "win_rate": round(len(side_success) / len(side_tracked) * 100, 1) if side_tracked else 0,
            }

        total_pages = (filtered_total + per_page - 1) // per_page if filtered_total > 0 else 1

        return {
            "total_alerts": total,
            "tracked": len(tracked),
            "successful": len(successful),
            "win_rate": round(win_rate, 1),
            "avg_return_7d": round(avg_return_7d, 2),
            "by_type": by_type,
            "round_trip": round_trip,
            "alerts": alerts_data,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": filtered_total,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
            },
        }

    except Exception as e:
        monitor.log_error("alerts.performance", str(e))
        raise HTTPException(status_code=500, detail="Failed to load performance stats")



def _pair_round_trips(alerts: list) -> list:
    """Pair each BUY with the SELL that closed it, per symbol.

    `alerts` arrives newest-first; walking it oldest-first mirrors how positions
    actually opened and closed. A BUY while one is already open is ignored (the
    scheduler only takes one position at a time per symbol), and a SELL with no
    open BUY is skipped — it cannot close anything.
    """
    positions: list = []
    open_by_symbol: dict = {}

    for row in sorted(alerts, key=lambda r: r.get("sent_at") or ""):
        symbol = row.get("stock_symbol")
        side = row.get("signal_type", "BUY")
        price = row.get("alert_price")
        if not symbol or price is None:
            continue

        if side == "BUY":
            if symbol not in open_by_symbol:
                open_by_symbol[symbol] = {
                    "symbol": symbol,
                    "entry_price": float(price),
                    "entry_at": row.get("sent_at"),
                    "target_high": float(row["target_high"]) if row.get("target_high") else None,
                    "exit_price": None,
                    "exit_at": None,
                    "status": "open",
                    "round_trip_return": None,
                    "days_held": None,
                }
        elif side == "SELL":
            pos = open_by_symbol.pop(symbol, None)
            if not pos:
                continue
            pos["exit_price"] = float(price)
            pos["exit_at"] = row.get("sent_at")
            pos["status"] = "closed"
            pos["round_trip_return"] = round(
                (pos["exit_price"] / pos["entry_price"] - 1) * 100, 2
            )
            pos["days_held"] = _days_between(pos["entry_at"], pos["exit_at"])
            positions.append(pos)

    positions.extend(open_by_symbol.values())
    return positions


def _days_between(start: str, end: str):
    try:
        a = datetime.fromisoformat(start.replace("Z", "+00:00"))
        b = datetime.fromisoformat(end.replace("Z", "+00:00"))
        return max(0, (b - a).days)
    except Exception:
        return None


@router.get("/recent")
async def get_recent_alerts(user_id: str = Depends(get_current_user_id)):
    """Get the 5 most recent alerts for a user."""
    try:
        supabase = get_supabase_client()

        response = await db(
            supabase.table("alerts")
            .select("*")
            .eq("user_id", user_id)
            .order("sent_at", desc=True)
            .limit(5)
        )

        return {"alerts": response.data}

    except Exception as e:
        monitor.log_error("alerts.recent", str(e))
        raise HTTPException(status_code=500, detail="Failed to load recent alerts")


@router.delete("/performance/clear")
async def clear_performance_data(user_id: str = Depends(get_current_user_id)):
    """Clear all performance-tracked alerts (BUY and SELL with price data) for the user."""
    try:
        supabase = get_supabase_client()

        # Delete all alerts that have alert_price (the performance-tracked ones)
        await db(
            supabase.table("alerts")
            .delete()
            .eq("user_id", user_id)
            .not_.is_("alert_price", "null")
        )

        return {"message": "Performance tracking data cleared successfully"}

    except Exception as e:
        monitor.log_error("alerts.clear_performance", str(e))
        raise HTTPException(status_code=500, detail="Failed to clear performance data")
