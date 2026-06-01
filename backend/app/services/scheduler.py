from datetime import datetime, timezone, timedelta
from app.core.config import get_settings
from app.core.database import get_supabase_client
from app.core.error_monitor import monitor
from app.services.market_data import MarketDataService
from app.services.market_hours import is_market_open, get_market_status
from app.services.indicator_engine import IndicatorEngine
from app.services.signal_engine import SignalEngine
from app.services.ai_analysis import AIAnalysisService
from app.services.line_notification import LineNotificationService
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
        self.ai_service = AIAnalysisService()
        self.line_service = LineNotificationService()

    @property
    def supabase(self):
        return get_supabase_client()

    async def run_analysis_cycle(self) -> None:
        """Run one complete analysis cycle for all active stocks."""
        # Skip if market is closed (only run during regular hours 9:30 AM - 4:00 PM ET)
        if not is_market_open(include_extended=False):
            status = get_market_status()
            print(f"[{datetime.now(timezone.utc)}] Market closed ({status['reason']}). Skipping analysis.")
            return

        print(f"[{datetime.now(timezone.utc)}] Starting analysis cycle...")

        try:
            # Get unique active stock symbols from all watchlists
            symbols = await self._get_active_symbols()
            if not symbols:
                print("No active symbols to analyze.")
                monitor.log_scheduler_success()
                return

            for symbol in symbols:
                await self._analyze_symbol(symbol)

            print(f"[{datetime.now(timezone.utc)}] Analysis cycle complete.")
            monitor.log_scheduler_success()

        except Exception as e:
            monitor.log_scheduler_failure(str(e))
            print(f"[{datetime.now(timezone.utc)}] Analysis cycle FAILED: {e}")

    async def _get_active_symbols(self) -> list[str]:
        """Get all unique stock symbols that are actively being tracked."""
        try:
            response = (
                self.supabase.table("watchlist_stocks")
                .select("symbol")
                .eq("is_enabled", True)
                .execute()
            )
            symbols = list({row["symbol"] for row in response.data})
            return symbols
        except Exception as e:
            print(f"Error fetching active symbols: {e}")
            return []

    async def _analyze_symbol(self, symbol: str) -> None:
        """Run full analysis pipeline for a single stock symbol."""
        try:
            # Step 1: Fetch market data
            df = await self.market_data.fetch_ohlcv(symbol)
            if df is None or df.empty:
                return

            # Step 2: Calculate indicators
            indicators = self.indicator_engine.calculate(df)
            if indicators is None:
                return

            # Step 3: Run signal engine (rule-based)
            signal = self.signal_engine.evaluate(indicators)

            # Step 4: If NO buy signal, stop here (no AI call)
            if not signal.is_buy_signal:
                return

            print(f"  BUY SIGNAL for {symbol} (score: {signal.total_score}/100): {signal.reasons}")

            # Step 5: Build compact summary for AI
            signal_summary = StockSignalSummary(
                symbol=symbol,
                price=indicators.current_price,
                score=signal.total_score,
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
            )

            # Step 6: AI analysis (with cache)
            analysis = await self.ai_service.analyze(signal_summary)
            if analysis is None:
                return

            # Only notify if AI says BUY (not HOLD or SELL)
            if analysis.action != "BUY":
                print(f"  AI decision for {symbol}: {analysis.action} — skipping notification")
                return

            # Step 7: Notify all users watching this stock
            await self._notify_users(symbol, analysis, indicators.current_price)

        except Exception as e:
            print(f"Error analyzing {symbol}: {e}")

    async def _notify_users(
        self,
        symbol: str,
        analysis: "AIAnalysisResult",
        price: float,
    ) -> None:
        """Send notifications to all users watching this stock."""
        try:
            # Get users watching this symbol with LINE connected
            response = (
                self.supabase.table("watchlist_stocks")
                .select("watchlist_id, watchlists(user_id, users(line_user_id, min_confidence))")
                .eq("symbol", symbol)
                .eq("is_enabled", True)
                .execute()
            )

            for row in response.data:
                watchlist = row.get("watchlists", {})
                user = watchlist.get("users", {})
                line_user_id = user.get("line_user_id")

                if not line_user_id:
                    continue

                user_id = watchlist.get("user_id")

                # Check duplicate: skip if already alerted within 24 hours
                if await self._has_recent_alert(user_id, symbol):
                    continue

                # Check notification preference
                min_confidence = user.get("min_confidence", "All")
                if not self._meets_confidence_preference(analysis.confidence, min_confidence):
                    continue

                # Send LINE notification
                is_sent = await self.line_service.send_buy_alert(
                    line_user_id=line_user_id,
                    analysis=analysis,
                    price=price,
                )

                # Save alert history
                if is_sent:
                    await self._save_alert(user_id, symbol, analysis, price)

        except Exception as e:
            print(f"Error notifying users for {symbol}: {e}")

    async def _has_recent_alert(self, user_id: str, symbol: str) -> bool:
        """Check if user already received an alert for this stock within 1 hour."""
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

            response = (
                self.supabase.table("alerts")
                .select("id")
                .eq("user_id", user_id)
                .eq("stock_symbol", symbol)
                .gte("sent_at", cutoff)
                .limit(1)
                .execute()
            )

            return len(response.data) > 0

        except Exception:
            return False

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
            ).execute()
        except Exception as e:
            print(f"Error saving alert for {user_id}/{symbol}: {e}")
