from openai import AsyncOpenAI
from datetime import datetime, timedelta, timezone
from typing import Optional
import json
from app.core.config import get_settings
from app.core.database import get_supabase_client
from app.schemas.stock import StockSignalSummary, AIAnalysisResult


class AIAnalysisService:
    """AI layer that analyzes stocks and decides BUY, SELL, or HOLD.

    Receives full indicator data and uses AI to make a final decision.
    Uses analysis cache to prevent repeated AI calls for the same stock.
    """

    SYSTEM_PROMPT = """You are an expert stock trading analyst specializing in "Buy on Dip" strategy. You receive comprehensive technical indicator data, multi-timeframe analysis, AND historical price data to identify HIGH-PROBABILITY reversal points where price has pulled back in an uptrend.

Your response MUST be valid JSON with this exact format:
{
  "action": "BUY" or "SELL" or "HOLD",
  "confidence": "High" or "Medium" or "Low",
  "summary": "One sentence explanation of your decision",
  "reasons": ["reason 1", "reason 2", "reason 3"]
}

BUY ON DIP STRATEGY — Core Principles:
1. Only BUY when price has PULLED BACK to support in an existing uptrend
2. NEVER buy at highs or when price is overextended above moving averages
3. Look for REVERSAL signals at support (oversold RSI, bullish patterns, volume)
4. Higher timeframes must confirm the uptrend is intact

BUY criteria (ALL must be met for High confidence):
- Price is in an uptrend (above EMA200 or EMA50>EMA200)
- Price has PULLED BACK (RSI < 45, near EMA21/50, or at lower Bollinger Band)
- Reversal signals present (MACD turning, Stoch cross, bullish candle pattern)
- NOT at resistance, NOT overextended

HOLD criteria:
- Price is still falling (no reversal confirmation yet)
- Mixed signals between timeframes
- RSI > 55 (not enough of a dip yet)
- Near resistance level

SELL/AVOID criteria:
- Price overextended (>5% above EMA21)
- RSI > 70 (overbought, likely to pull back)
- At 52-week highs with no pullback
- Volume declining in uptrend (distribution)
- All timeframes showing bearish divergence

Historical Price Analysis for Dip Buying:
- Use WEEKLY candles to identify: is this a dip within an uptrend, or a breakdown?
- Use DAILY candles to identify: has selling pressure exhausted? Is volume drying up on the dip?
- Compare current price to recent highs — a 5-15% pullback from high in uptrend = ideal dip
- A 20%+ drop with broken EMA200 = NOT a dip, it's a trend change

Be CONSERVATIVE. Only say BUY when the dip is clear and reversal is confirmed.
Respond ONLY with the JSON object, no other text."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = AsyncOpenAI(api_key=self.settings.openai_api_key)

    @property
    def supabase(self):
        return get_supabase_client()

    async def analyze(self, signal_summary: StockSignalSummary) -> Optional[AIAnalysisResult]:
        """Generate AI analysis with full indicator data.

        First checks cache. If cached result exists and is not expired, returns it.
        Otherwise, calls OpenAI and caches the result.
        """
        cached = await self._get_cached_analysis(signal_summary.symbol)
        if cached:
            return cached

        result = await self._call_openai(signal_summary)
        if result:
            await self._cache_analysis(result)

        return result

    async def _get_cached_analysis(self, symbol: str) -> Optional[AIAnalysisResult]:
        """Check if a valid cached analysis exists."""
        try:
            now = datetime.now(timezone.utc).isoformat()
            response = (
                self.supabase.table("analysis_cache")
                .select("*")
                .eq("symbol", symbol)
                .gte("expires_at", now)
                .order("cached_at", desc=True)
                .limit(1)
                .execute()
            )

            if response.data:
                entry = response.data[0]
                return AIAnalysisResult(
                    symbol=entry["symbol"],
                    action=entry.get("action", "BUY"),
                    summary=entry["ai_summary"],
                    confidence=entry["confidence"],
                    reasons=entry["reasons"],
                    analyzed_at=datetime.fromisoformat(entry["cached_at"]),
                )

            return None

        except Exception as e:
            print(f"Error checking cache for {symbol}: {e}")
            return None

    async def _call_openai(self, summary: StockSignalSummary) -> Optional[AIAnalysisResult]:
        """Call OpenAI API with full indicator data."""
        try:
            user_message = self._build_indicator_message(summary)

            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                max_tokens=500,
                temperature=0.2,
            )

            ai_text = response.choices[0].message.content or ""

            # Parse JSON response
            parsed = self._parse_ai_response(ai_text, summary)
            return parsed

        except Exception as e:
            print(f"Error calling OpenAI for {summary.symbol}: {e}")
            return None

    def _build_indicator_message(self, s: StockSignalSummary) -> str:
        """Build comprehensive indicator message for AI including MTF and historical data."""
        mtf_section = ""
        if s.mtf_trend_alignment != "not_available":
            mtf_section = (
                f"\n--- MULTI-TIMEFRAME ANALYSIS ---\n"
                f"Overall MTF Alignment: {s.mtf_trend_alignment.upper()}\n"
                f"Daily Trend: (primary analysis above)\n"
                f"4H Trend: {s.mtf_4h_trend} | RSI: {s.mtf_4h_rsi:.1f}\n"
                f"1H Trend: {s.mtf_1h_trend} | RSI: {s.mtf_1h_rsi:.1f}\n"
                f"MTF Score Adjustment: +{s.mtf_bonus} bonus, -{s.mtf_penalty} penalty\n"
            )

        # Build weekly candles section
        weekly_section = ""
        if s.weekly_candles:
            weekly_section = "\n--- WEEKLY CANDLES (1 Year, oldest→newest) ---\n"
            weekly_section += "Date       | Open    | High    | Low     | Close   | Volume\n"
            for c in s.weekly_candles:
                weekly_section += (
                    f"{c['date']} | ${c['o']:>7.2f} | ${c['h']:>7.2f} | "
                    f"${c['l']:>7.2f} | ${c['c']:>7.2f} | {c['v']:>10,}\n"
                )
            # Add computed context
            if len(s.weekly_candles) >= 2:
                first_close = s.weekly_candles[0]["c"]
                last_close = s.weekly_candles[-1]["c"]
                year_return = ((last_close - first_close) / first_close) * 100
                year_high = max(c["h"] for c in s.weekly_candles)
                year_low = min(c["l"] for c in s.weekly_candles)
                weekly_section += (
                    f"\n52-Week Summary: Return={year_return:+.1f}%, "
                    f"High=${year_high:.2f}, Low=${year_low:.2f}, "
                    f"Current vs High={((last_close/year_high)-1)*100:.1f}%\n"
                )

        # Build daily candles section
        daily_section = ""
        if s.daily_candles:
            daily_section = "\n--- RECENT DAILY CANDLES (30 days, oldest→newest) ---\n"
            daily_section += "Date       | Open    | High    | Low     | Close   | Volume\n"
            for c in s.daily_candles:
                daily_section += (
                    f"{c['date']} | ${c['o']:>7.2f} | ${c['h']:>7.2f} | "
                    f"${c['l']:>7.2f} | ${c['c']:>7.2f} | {c['v']:>10,}\n"
                )
            # Add recent context
            if len(s.daily_candles) >= 5:
                last_5_closes = [c["c"] for c in s.daily_candles[-5:]]
                last_5_volumes = [c["v"] for c in s.daily_candles[-5:]]
                avg_recent_vol = sum(last_5_volumes) / 5
                recent_momentum = ((last_5_closes[-1] - last_5_closes[0]) / last_5_closes[0]) * 100
                daily_section += (
                    f"\n5-Day Momentum: {recent_momentum:+.2f}%, "
                    f"Avg Volume (5d): {int(avg_recent_vol):,}\n"
                )

        return (
            f"=== {s.symbol} Analysis ===\n"
            f"Price: ${s.price:.2f}\n"
            f"Signal Score: {s.score}/100 (MTF-adjusted)\n\n"
            f"--- TREND (Daily) ---\n"
            f"EMA 9: ${s.ema_9:.2f}\n"
            f"EMA 21: ${s.ema_21:.2f}\n"
            f"EMA 50: ${s.ema_50:.2f}\n"
            f"EMA 200: ${s.ema_200:.2f}\n"
            f"EMA Alignment: {'Bullish' if s.price > s.ema_9 > s.ema_21 > s.ema_50 else 'Mixed'}\n"
            f"MACD: {s.macd_value:.4f} | Signal: {s.macd_signal:.4f} | Hist: {s.macd_histogram:.4f}\n"
            f"SuperTrend: {s.supertrend_direction} (value: ${s.supertrend_value:.2f})\n\n"
            f"--- MOMENTUM (Daily) ---\n"
            f"RSI(14): {s.rsi:.1f} ({s.rsi_state})\n"
            f"Stochastic: %K={s.stoch_k:.1f}, %D={s.stoch_d:.1f}\n\n"
            f"--- VOLATILITY ---\n"
            f"ATR(14): ${s.atr:.2f}\n"
            f"Bollinger Bands: Upper=${s.bb_upper:.2f}, Mid=${s.bb_middle:.2f}, Lower=${s.bb_lower:.2f}\n"
            f"BB Position: {s.bb_position}\n\n"
            f"--- VOLUME ---\n"
            f"Volume Ratio: {s.volume_ratio:.1f}x average\n\n"
            f"--- MARKET STRUCTURE ---\n"
            f"Pivot: ${s.pivot:.2f}\n"
            f"R1: ${s.r1:.2f} | R2: ${s.r2:.2f}\n"
            f"S1: ${s.s1:.2f} | S2: ${s.s2:.2f}\n\n"
            f"--- PATTERNS ---\n"
            f"Candlestick: {', '.join(s.candle_patterns) if s.candle_patterns else 'None'}\n"
            f"{mtf_section}"
            f"{weekly_section}"
            f"{daily_section}\n"
            f"--- SIGNAL ENGINE ---\n"
            f"Reasons: {', '.join(s.signal_reasons) if s.signal_reasons else 'None'}\n\n"
            f"Based on ALL data (indicators, multi-timeframe, AND historical price action), what is your decision: BUY, SELL, or HOLD?"
        )

    def _parse_ai_response(self, ai_text: str, summary: StockSignalSummary) -> Optional[AIAnalysisResult]:
        """Parse AI JSON response into AIAnalysisResult."""
        try:
            # Try to extract JSON from response
            text = ai_text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            parsed = json.loads(text)

            action = parsed.get("action", "HOLD").upper()
            if action not in ("BUY", "SELL", "HOLD"):
                action = "HOLD"

            confidence = parsed.get("confidence", "Medium")
            if confidence not in ("High", "Medium", "Low"):
                confidence = "Medium"

            return AIAnalysisResult(
                symbol=summary.symbol,
                action=action,
                summary=parsed.get("summary", ai_text[:200]),
                confidence=confidence,
                reasons=parsed.get("reasons", []),
                analyzed_at=datetime.now(timezone.utc),
            )

        except (json.JSONDecodeError, KeyError):
            # Fallback: use raw text
            return AIAnalysisResult(
                symbol=summary.symbol,
                action="HOLD",
                summary=ai_text[:200],
                confidence="Low",
                reasons=[ai_text[:100]],
                analyzed_at=datetime.now(timezone.utc),
            )

    async def _cache_analysis(self, result: AIAnalysisResult) -> None:
        """Cache AI analysis result with TTL."""
        try:
            ttl_minutes = self.settings.cache_ttl_minutes
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)

            self.supabase.table("analysis_cache").upsert(
                {
                    "symbol": result.symbol,
                    "ai_summary": result.summary,
                    "confidence": result.confidence,
                    "reasons": result.reasons,
                    "cached_at": result.analyzed_at.isoformat(),
                    "expires_at": expires_at.isoformat(),
                },
                on_conflict="symbol",
            ).execute()

        except Exception as e:
            print(f"Error caching analysis for {result.symbol}: {e}")
