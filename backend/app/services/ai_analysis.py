from openai import AsyncOpenAI
from datetime import datetime, timedelta, timezone
from typing import Optional
from app.core.config import get_settings
from app.core.database import get_supabase_client
from app.schemas.stock import StockSignalSummary, AIAnalysisResult


class AIAnalysisService:
    """AI layer that generates buy analysis only when signal engine triggers.

    Uses analysis cache to prevent repeated AI calls for the same stock.
    """

    SYSTEM_PROMPT = """You are a concise stock analysis assistant. 
Given technical indicator data, provide a brief buy analysis suitable for a mobile notification.
Keep your response under 100 words. Be direct and actionable.
Format: Summary sentence, then bullet points for key reasons."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = AsyncOpenAI(api_key=self.settings.openai_api_key)

    @property
    def supabase(self):
        return get_supabase_client()

    async def analyze(self, signal_summary: StockSignalSummary) -> Optional[AIAnalysisResult]:
        """Generate AI analysis for a buy signal.

        First checks cache. If cached result exists and is not expired, returns it.
        Otherwise, calls OpenAI and caches the result.
        """
        # Check cache first
        cached = await self._get_cached_analysis(signal_summary.symbol)
        if cached:
            return cached

        # Generate new analysis
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
                    summary=entry["ai_summary"],
                    confidence=entry["confidence"],
                    reasons=entry["reasons"],
                    analyzed_at=datetime.fromisoformat(entry["cached_at"]),
                )

            return None

        except Exception as e:
            print(f"Error checking cache for {symbol}: {e}")
            return None

    async def _call_openai(self, signal_summary: StockSignalSummary) -> Optional[AIAnalysisResult]:
        """Call OpenAI API with compact signal summary."""
        try:
            user_message = (
                f"Stock: {signal_summary.symbol}\n"
                f"Price: {signal_summary.price}\n"
                f"RSI: {signal_summary.rsi}\n"
                f"MACD: {signal_summary.macd}\n"
                f"Trend: {signal_summary.trend}\n"
                f"Support: {signal_summary.support}\n"
                f"Volume: {signal_summary.volume}\n\n"
                "Provide a brief buy analysis."
            )

            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                max_tokens=150,
                temperature=0.3,
            )

            ai_text = response.choices[0].message.content or ""

            # Parse confidence from context
            confidence = self._determine_confidence(signal_summary)

            return AIAnalysisResult(
                symbol=signal_summary.symbol,
                summary=ai_text,
                confidence=confidence,
                reasons=self._extract_reasons(ai_text),
                analyzed_at=datetime.now(timezone.utc),
            )

        except Exception as e:
            print(f"Error calling OpenAI for {signal_summary.symbol}: {e}")
            return None

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

    def _determine_confidence(self, summary: StockSignalSummary) -> str:
        """Determine confidence level based on total signal score."""
        score = summary.score
        if score >= 80:
            return "High"
        if score >= 60:
            return "Medium"
        return "Low"

    def _extract_reasons(self, ai_text: str) -> list[str]:
        """Extract bullet point reasons from AI response."""
        reasons: list[str] = []
        for line in ai_text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("-") or stripped.startswith("•"):
                reasons.append(stripped.lstrip("-•").strip())
        return reasons if reasons else [ai_text[:100]]
