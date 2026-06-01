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

    SYSTEM_PROMPT = """You are an expert stock trading analyst. You receive comprehensive technical indicator data and must decide: BUY, SELL, or HOLD.

Your response MUST be valid JSON with this exact format:
{
  "action": "BUY" or "SELL" or "HOLD",
  "confidence": "High" or "Medium" or "Low",
  "summary": "One sentence explanation of your decision",
  "reasons": ["reason 1", "reason 2", "reason 3"]
}

Decision guidelines:
- BUY: Strong bullish alignment across multiple indicators, good risk/reward
- SELL: Bearish signals, overbought conditions, breakdown from support
- HOLD: Mixed signals, no clear edge, wait for confirmation

Consider ALL indicators holistically:
- Trend: EMA alignment, SuperTrend direction, MACD crossover
- Momentum: RSI state, Stochastic crossover
- Volatility: Bollinger Band position, ATR for risk assessment
- Structure: Pivot levels (support/resistance), candlestick patterns
- Volume: Accumulation or distribution

Be decisive. Respond ONLY with the JSON object, no other text."""

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
                max_tokens=300,
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
        """Build comprehensive indicator message for AI."""
        return (
            f"=== {s.symbol} Analysis ===\n"
            f"Price: ${s.price:.2f}\n"
            f"Signal Score: {s.score}/100\n\n"
            f"--- TREND ---\n"
            f"EMA 9: ${s.ema_9:.2f}\n"
            f"EMA 21: ${s.ema_21:.2f}\n"
            f"EMA 50: ${s.ema_50:.2f}\n"
            f"EMA 200: ${s.ema_200:.2f}\n"
            f"EMA Alignment: {'Bullish' if s.price > s.ema_9 > s.ema_21 > s.ema_50 else 'Mixed'}\n"
            f"MACD: {s.macd_value:.4f} | Signal: {s.macd_signal:.4f} | Hist: {s.macd_histogram:.4f}\n"
            f"SuperTrend: {s.supertrend_direction} (value: ${s.supertrend_value:.2f})\n\n"
            f"--- MOMENTUM ---\n"
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
            f"Candlestick: {', '.join(s.candle_patterns) if s.candle_patterns else 'None'}\n\n"
            f"--- SIGNAL ENGINE ---\n"
            f"Reasons: {', '.join(s.signal_reasons) if s.signal_reasons else 'None'}\n\n"
            f"Based on ALL the above data, what is your decision: BUY, SELL, or HOLD?"
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
