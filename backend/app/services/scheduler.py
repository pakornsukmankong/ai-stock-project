import asyncio
from datetime import datetime, timezone, timedelta
from functools import lru_cache
from app.core.config import get_settings
from app.core.database import get_supabase_client, db
from app.core.error_monitor import monitor
from app.services.market_data import MarketDataService
from app.services.markets import market_for_symbol, any_market_open, open_market_codes
from app.services.indicator_engine import IndicatorEngine
from app.services.signal_engine import SignalEngine
from app.services.mtf_engine import MTFEngine
from app.services.ai_analysis import AIAnalysisService
from app.services.line_notification import LineNotificationService, MONTHLY_LIMIT, SENT
from app.schemas.stock import StockSignalSummary


class AnalysisScheduler:
    """Orchestrates the stock analysis pipeline.

    Flow:
    1. Get all active watchlist stocks
    2. Fetch market data for each
    3. Calculate indicators
    4. Run signal engine (rule-based)
    5. If buy signal → AI analysis → LINE notification → Save alert
    """

    def __init__(self) -> None:
        self.market_data = MarketDataService()
        self.indicator_engine = IndicatorEngine()
        self.signal_engine = SignalEngine()
        self.mtf_engine = MTFEngine()
        self.ai_service = AIAnalysisService()
        self.line_service = LineNotificationService()
        # Per-symbol signal state from the previous cycle, used for edge-trigger
        # detection (symbol -> was the buy signal active last cycle). In-memory:
        # resets on restart, where the cooldown bounds any re-alert burst.
        self._signal_active: dict[str, bool] = {}
        # Guards against two cycles running at once (the interval job overlapping
        # a slow run, or a manual /analysis/trigger landing mid-cycle).
        self._cycle_lock = asyncio.Lock()

    @property
    def supabase(self):
        return get_supabase_client()

    @property
    def is_running(self) -> bool:
        """True while a cycle is in flight."""
        return self._cycle_lock.locked()

    async def run_analysis_cycle(self) -> None:
        """Run one complete analysis cycle for all active stocks."""
        # Skip only when EVERY supported market is closed. Symbols are filtered to
        # the currently-open exchange(s) inside the cycle, so a Thai stock is
        # analyzed during SET hours and a US stock during US hours.
        if not any_market_open():
            print(f"[{datetime.now(timezone.utc)}] All markets closed. Skipping analysis.")
            return

        if self._cycle_lock.locked():
            print(f"[{datetime.now(timezone.utc)}] Analysis cycle already running. Skipping.")
            return

        async with self._cycle_lock:
            await self._run_cycle()

    async def _run_cycle(self) -> None:
        print(f"[{datetime.now(timezone.utc)}] Starting analysis cycle...")

        try:
            # One query up-front for the whole watcher graph, instead of one query
            # per symbol plus one per (user, symbol) pair later in the cycle.
            watchers = await self._get_watchers()
            all_symbols = list(watchers.keys())
            if not all_symbols:
                print("No active symbols to analyze.")
                monitor.log_scheduler_success()
                return

            # Forget edge-trigger state for symbols no longer watched (so a
            # re-added symbol gets a fresh edge). Keyed on ALL watched symbols,
            # not just the ones analyzed this cycle, so a closed-market symbol
            # keeps its state until its exchange opens again.
            active_set = set(all_symbols)
            self._signal_active = {
                s: v for s, v in self._signal_active.items() if s in active_set
            }

            # Analyze only symbols whose exchange is open right now. US and SET
            # sessions don't overlap, so most cycles this is a single market.
            open_codes = open_market_codes()
            symbols = [s for s in all_symbols if market_for_symbol(s).code in open_codes]
            if not symbols:
                print("No watched symbols are in an open market this cycle.")
                monitor.log_scheduler_success()
                return

            recently_alerted = await self._get_recently_alerted()

            # Collect buy signals per user across the whole cycle so each user
            # receives ONE digest message instead of one push per signal.
            pending: dict[str, dict] = {}

            # Analyze symbols concurrently. Each symbol costs two Yahoo round-trips
            # plus heavy pandas work, so a serial loop made cycle time scale
            # linearly with watchlist size. The semaphore keeps us from tripping
            # Yahoo's rate limiting.
            concurrency = max(1, get_settings().analysis_concurrency)
            semaphore = asyncio.Semaphore(concurrency)

            async def analyze(symbol: str) -> None:
                async with semaphore:
                    await self._analyze_symbol(
                        symbol, pending, watchers, recently_alerted
                    )

            await asyncio.gather(*(analyze(symbol) for symbol in symbols))

            await self._dispatch_notifications(pending)

            print(f"[{datetime.now(timezone.utc)}] Analysis cycle complete.")
            monitor.log_scheduler_success()

        except Exception as e:
            monitor.log_scheduler_failure(str(e))
            print(f"[{datetime.now(timezone.utc)}] Analysis cycle FAILED: {e}")

    async def _get_watchers(self) -> dict[str, list[dict]]:
        """Map every actively-tracked symbol to the users watching it.

        Replaces the old per-symbol `_collect_users` query (N queries per cycle)
        with a single fetch of the watchlist graph.
        """
        try:
            response = await db(
                self.supabase.table("watchlist_stocks")
                .select("symbol, watchlists(user_id, users(line_user_id, min_confidence))")
                .eq("is_enabled", True)
            )

            watchers: dict[str, list[dict]] = {}
            for row in response.data:
                symbol = row.get("symbol")
                if not symbol:
                    continue

                entry = watchers.setdefault(symbol, [])

                watchlist = row.get("watchlists") or {}
                user = watchlist.get("users") or {}
                user_id = watchlist.get("user_id")
                line_user_id = user.get("line_user_id")

                # Symbols with no LINE-connected watcher still need analyzing (so
                # alerts land on the dashboard), hence the key is created above.
                if user_id and line_user_id:
                    entry.append(
                        {
                            "user_id": user_id,
                            "line_user_id": line_user_id,
                            "min_confidence": user.get("min_confidence") or "All",
                        }
                    )

            return watchers
        except Exception as e:
            print(f"Error fetching active symbols: {e}")
            return {}

    async def _get_recently_alerted(self) -> set[tuple[str, str]]:
        """(user_id, symbol) pairs alerted within the cooldown window.

        Fetched once per cycle instead of one query per (user, symbol) candidate.
        """
        try:
            cooldown_hours = get_settings().alert_cooldown_hours
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=cooldown_hours)).isoformat()

            response = await db(
                self.supabase.table("alerts")
                .select("user_id, stock_symbol")
                .eq("signal_type", "BUY")
                .gte("sent_at", cutoff)
            )

            return {(row["user_id"], row["stock_symbol"]) for row in response.data}
        except Exception as e:
            print(f"Error fetching recent alerts: {e}")
            # Fail closed: an empty set would let every signal through and
            # re-alert users who are still inside their cooldown window.
            raise

    async def _analyze_symbol(
        self,
        symbol: str,
        pending: dict,
        watchers: dict[str, list[dict]],
        recently_alerted: set[tuple[str, str]],
    ) -> None:
        """Run full analysis pipeline for a single stock symbol with multi-timeframe."""
        try:
            # Step 1: Fetch daily market data (primary timeframe)
            df = await self.market_data.fetch_ohlcv(symbol)
            if df is None or df.empty:
                return

            # Step 2: Calculate daily indicators
            indicators = self.indicator_engine.calculate(df)
            if indicators is None:
                return

            # Step 3: Run Multi-Timeframe analysis (4H + 1H), reusing the daily
            # indicators we already computed above (no redundant daily fetch).
            mtf_result = None
            try:
                mtf_result = await self.mtf_engine.analyze(
                    symbol, daily_df=df, daily_indicators=indicators
                )
            except Exception as e:
                print(f"  MTF analysis failed for {symbol} (using single TF): {e}")
                mtf_result = None

            # Step 4: Run signal engine with MTF adjustment
            signal = self.signal_engine.evaluate_with_mtf(indicators, mtf_result)

            # Step 5: Edge-trigger gate. Only continue when the signal NEWLY turns
            # active (was inactive last cycle). A setup that stays >= threshold for
            # hours/days should alert once, not every cycle. Updating state here
            # (not on earlier early-returns) leaves it unchanged when data is
            # missing, so a fetch hiccup doesn't fabricate a fresh edge.
            settings = get_settings()
            was_active = self._signal_active.get(symbol, False)
            now_active = signal.is_buy_signal
            self._signal_active[symbol] = now_active

            if not now_active:
                return  # no buy signal — stop (no AI call)
            if settings.alert_edge_trigger and was_active:
                # Still active from a previous cycle — not a new event.
                print(f"  {symbol}: signal still active (no new edge) — skipping")
                return

            # Determine which score to display
            display_score = signal.mtf_adjusted_score if mtf_result else signal.total_score
            print(f"  BUY SIGNAL for {symbol} (score: {display_score}/100, "
                  f"base: {signal.total_score}, MTF bonus: +{signal.mtf_bonus}, "
                  f"penalty: -{signal.mtf_penalty}): {signal.reasons}")

            # Step 6: Build compact summary for AI (with MTF data)
            signal_summary = StockSignalSummary(
                symbol=symbol,
                price=indicators.current_price,
                score=display_score,
                # Trend
                ema_9=indicators.ema_9,
                ema_21=indicators.ema_21,
                ema_50=indicators.ema_50,
                ema_200=indicators.ema_200,
                macd_value=indicators.macd_value,
                macd_signal=indicators.macd_signal,
                macd_histogram=indicators.macd_histogram,
                supertrend_direction=indicators.supertrend_direction,
                supertrend_value=indicators.supertrend_value,
                # Momentum
                rsi=indicators.rsi,
                rsi_state=indicators.rsi_state,
                stoch_k=indicators.stoch_k,
                stoch_d=indicators.stoch_d,
                # Volatility
                atr=indicators.atr,
                bb_upper=indicators.bb_upper,
                bb_middle=indicators.bb_middle,
                bb_lower=indicators.bb_lower,
                bb_position=indicators.bb_position,
                # Volume
                volume_ratio=indicators.current_volume / indicators.avg_volume if indicators.avg_volume > 0 else 1.0,
                # Market Structure
                pivot=indicators.pivot_levels.pivot,
                r1=indicators.pivot_levels.r1,
                r2=indicators.pivot_levels.r2,
                s1=indicators.pivot_levels.s1,
                s2=indicators.pivot_levels.s2,
                # Patterns
                candle_patterns=indicators.candle_patterns.get_detected(),
                signal_reasons=signal.reasons,
                # Multi-Timeframe
                mtf_trend_alignment=signal.mtf_confluence,
                mtf_4h_trend=mtf_result.four_hour.trend_direction if mtf_result and mtf_result.four_hour.is_valid else "n/a",
                mtf_1h_trend=mtf_result.one_hour.trend_direction if mtf_result and mtf_result.one_hour.is_valid else "n/a",
                mtf_4h_rsi=mtf_result.four_hour.indicators.rsi if mtf_result and mtf_result.four_hour.indicators else 0.0,
                mtf_1h_rsi=mtf_result.one_hour.indicators.rsi if mtf_result and mtf_result.one_hour.indicators else 0.0,
                mtf_bonus=signal.mtf_bonus,
                mtf_penalty=signal.mtf_penalty,
                # Historical Candle Data
                weekly_candles=self._build_weekly_candles(df),
                daily_candles=self._build_recent_daily_candles(df),
            )

            # Step 7: AI analysis (with cache)
            analysis = await self.ai_service.analyze(signal_summary)
            if analysis is None:
                return

            # Only notify if AI says BUY (not HOLD or SELL)
            if analysis.action != "BUY":
                print(f"  AI decision for {symbol}: {analysis.action} — skipping notification")
                return

            # Step 8: Queue this signal for every user watching the stock
            # (sent as a digest at the end of the cycle).
            self._collect_users(
                symbol,
                analysis,
                indicators.current_price,
                pending,
                watchers.get(symbol, []),
                recently_alerted,
            )

        except Exception as e:
            print(f"Error analyzing {symbol}: {e}")

    def _build_weekly_candles(self, df) -> list[dict]:
        """Resample daily data to weekly candles (52 weeks = 1 year overview).

        Provides AI with long-term price structure:
        - Major support/resistance zones
        - Overall trend direction
        - Historical highs/lows
        """
        try:
            weekly = df.resample("W").agg({
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }).dropna()

            # Take last 52 weeks
            weekly = weekly.tail(52)

            candles = []
            for idx, row in weekly.iterrows():
                candles.append({
                    "date": idx.strftime("%Y-%m-%d"),
                    "o": round(row["open"], 2),
                    "h": round(row["high"], 2),
                    "l": round(row["low"], 2),
                    "c": round(row["close"], 2),
                    "v": int(row["volume"]),
                })
            return candles
        except Exception as e:
            print(f"Error building weekly candles: {e}")
            return []

    def _build_recent_daily_candles(self, df) -> list[dict]:
        """Get last 30 daily candles for recent price action context.

        Provides AI with short-term context:
        - Recent momentum and volume patterns
        - Consolidation/breakout detection
        - Gap up/down identification
        - Recent support/resistance tests
        """
        try:
            recent = df.tail(30)

            candles = []
            for idx, row in recent.iterrows():
                candles.append({
                    "date": idx.strftime("%Y-%m-%d"),
                    "o": round(row["open"], 2),
                    "h": round(row["high"], 2),
                    "l": round(row["low"], 2),
                    "c": round(row["close"], 2),
                    "v": int(row["volume"]),
                })
            return candles
        except Exception as e:
            print(f"Error building daily candles: {e}")
            return []

    def _collect_users(
        self,
        symbol: str,
        analysis: "AIAnalysisResult",
        price: float,
        pending: dict,
        watchers: list[dict],
        recently_alerted: set[tuple[str, str]],
    ) -> None:
        """Queue this signal for every eligible user into the per-user digest buckets.

        Purely in-memory: the watcher list and the cooldown set are both fetched
        once per cycle by the caller.
        """
        for watcher in watchers:
            user_id = watcher["user_id"]

            # Skip if the user was already alerted for this stock within the
            # cooldown window (ALERT_COOLDOWN_HOURS).
            if (user_id, symbol) in recently_alerted:
                continue

            if not self._meets_confidence_preference(
                analysis.confidence, watcher["min_confidence"]
            ):
                continue

            bucket = pending.setdefault(
                user_id, {"line_user_id": watcher["line_user_id"], "items": []}
            )
            bucket["items"].append(
                {"symbol": symbol, "analysis": analysis, "price": price}
            )

    async def _dispatch_notifications(self, pending: dict) -> None:
        """Send one digest per user, with LINE monthly-quota awareness.

        - If the LINE monthly quota is exhausted, skip sending but still persist
          alerts to the DB so users can see them on the dashboard (fallback).
        - Transient LINE failures are NOT persisted, so they are retried on the
          next cycle.
        """
        if not pending:
            return

        # Check the LINE monthly quota once before sending the batch.
        monthly_limit_hit = False
        quota = await self.line_service.get_quota_status()
        if (
            quota["type"] == "limited"
            and quota.get("remaining") is not None
            and quota["remaining"] <= 0
        ):
            monthly_limit_hit = True
            print(
                f"[LINE] Monthly quota exhausted ({quota['used']}/{quota['limit']}). "
                f"Saving alerts to DB only (dashboard fallback)."
            )

        for user_id, bucket in pending.items():
            items = bucket["items"]
            should_save = False

            if monthly_limit_hit:
                # Known-exhausted: DB-only fallback, don't even attempt LINE.
                should_save = True
            else:
                message = self.line_service.format_digest(items)
                status = await self.line_service.send_text(bucket["line_user_id"], message)

                if status == SENT:
                    should_save = True
                elif status == MONTHLY_LIMIT:
                    # Quota ran out mid-batch — fall back to DB for this and the rest.
                    monthly_limit_hit = True
                    should_save = True
                else:
                    # Transient (rate limit / other failure): leave unsaved so the
                    # next cycle retries delivery.
                    print(f"[LINE] Delivery failed for {user_id} ({status}); will retry next cycle.")

            if should_save:
                for item in items:
                    await self._save_alert(
                        user_id, item["symbol"], item["analysis"], item["price"]
                    )

    def _meets_confidence_preference(self, confidence: str, min_confidence: str) -> bool:
        """Check if alert confidence meets user's minimum preference.

        Hierarchy: High > Medium > Low
        - 'All' = receive everything
        - 'Medium' = receive Medium and High
        - 'High' = receive only High
        """
        if min_confidence == "All":
            return True

        confidence_levels = {"High": 3, "Medium": 2, "Low": 1}
        alert_level = confidence_levels.get(confidence, 0)
        min_level = confidence_levels.get(min_confidence, 0)

        return alert_level >= min_level

    async def _save_alert(
        self,
        user_id: str,
        symbol: str,
        analysis: "AIAnalysisResult",
        price: float = None,
    ) -> None:
        """Save alert to history."""
        try:
            await db(
                self.supabase.table("alerts").insert(
                    {
                        "user_id": user_id,
                        "stock_symbol": symbol,
                        "signal_type": "BUY",
                        "ai_summary": analysis.summary,
                        "confidence": analysis.confidence,
                        "reasons": analysis.reasons,
                        "alert_price": price,
                        "sent_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
            )
        except Exception as e:
            print(f"Error saving alert for {user_id}/{symbol}: {e}")


@lru_cache()
def get_analysis_scheduler() -> AnalysisScheduler:
    """The single scheduler instance shared by the cron job and /analysis/trigger.

    Must be a singleton: the edge-trigger state and the run lock live on the
    instance, so a per-request `AnalysisScheduler()` would both re-alert
    already-active signals and run a second cycle concurrently with the job.
    """
    return AnalysisScheduler()
