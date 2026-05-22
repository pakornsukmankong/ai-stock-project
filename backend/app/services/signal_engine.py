from dataclasses import dataclass
from app.services.indicator_engine import IndicatorResult

# Minimum score to trigger buy signal (out of 100)
BUY_SIGNAL_THRESHOLD = 60


@dataclass
class SignalResult:
    """Result of the scoring-based signal engine."""

    is_buy_signal: bool
    total_score: int
    trend_score: int
    rsi_score: int
    macd_score: int
    volume_score: int
    support_score: int
    reasons: list[str]
    rsi_status: str
    macd_status: str
    trend_status: str
    support_status: str
    volume_status: str


class SignalEngine:
    """Scoring-based signal engine that determines if a buy signal exists.

    Scoring system (max 100 pts):
    - Trend (EMA200):       30 pts
    - RSI:                  20 pts
    - MACD:                 20 pts
    - Volume:               15 pts
    - Support Zone:         15 pts

    Buy signal triggers when total score >= 60.
    """

    EMA_NEAR_PERCENT = 0.02  # Within 2% of EMA200
    SUPPORT_PROXIMITY_PERCENT = 0.03  # Within 3% of support
    RESISTANCE_PROXIMITY_PERCENT = 0.03  # Within 3% of resistance
    VOLUME_ACCUMULATION_MULTIPLIER = 1.5
    VOLUME_NEUTRAL_MULTIPLIER = 1.0

    def evaluate(self, indicators: IndicatorResult) -> SignalResult:
        """Evaluate indicators using scoring system.

        Returns SignalResult with score breakdown and buy signal decision.
        """
        reasons: list[str] = []

        # Trend Score (30 pts) - EMA200
        trend_score, trend_status = self._score_trend(indicators, reasons)

        # RSI Score (20 pts)
        rsi_score, rsi_status = self._score_rsi(indicators, trend_status, reasons)

        # MACD Score (20 pts)
        macd_score, macd_status = self._score_macd(indicators, reasons)

        # Volume Score (15 pts)
        volume_score, volume_status = self._score_volume(indicators, reasons)

        # Support Zone Score (15 pts)
        support_score, support_status = self._score_support(indicators, reasons)

        # Total
        total_score = trend_score + rsi_score + macd_score + volume_score + support_score
        is_buy_signal = total_score >= BUY_SIGNAL_THRESHOLD

        return SignalResult(
            is_buy_signal=is_buy_signal,
            total_score=total_score,
            trend_score=trend_score,
            rsi_score=rsi_score,
            macd_score=macd_score,
            volume_score=volume_score,
            support_score=support_score,
            reasons=reasons,
            rsi_status=rsi_status,
            macd_status=macd_status,
            trend_status=trend_status,
            support_status=support_status,
            volume_status=volume_status,
        )

    def _score_trend(self, indicators: IndicatorResult, reasons: list[str]) -> tuple[int, str]:
        """Score trend based on price vs EMA200.

        - Above EMA200 = +30
        - Near EMA200 (within 2%) = +15
        - Below EMA200 = 0
        """
        price = indicators.current_price
        ema = indicators.ema_200
        distance_pct = (price - ema) / ema

        if distance_pct > self.EMA_NEAR_PERCENT:
            reasons.append(f"Price above EMA200 (+{distance_pct*100:.1f}%)")
            return 30, "above"
        elif abs(distance_pct) <= self.EMA_NEAR_PERCENT:
            reasons.append("Price near EMA200")
            return 15, "near"
        else:
            return 0, "below"

    def _score_rsi(
        self, indicators: IndicatorResult, trend_status: str, reasons: list[str]
    ) -> tuple[int, str]:
        """Score RSI based on value and trend context.

        - RSI 35-50 during uptrend = +20
        - RSI < 30 (oversold) = +15
        - RSI > 70 = 0
        """
        rsi = indicators.rsi

        if 35 <= rsi <= 50 and trend_status in ("above", "near"):
            reasons.append(f"RSI {rsi:.1f} — pullback in uptrend")
            return 20, "pullback_uptrend"
        elif rsi < 30:
            reasons.append(f"RSI {rsi:.1f} — oversold")
            return 15, "oversold"
        elif rsi > 70:
            return 0, "overbought"
        else:
            return 5, "neutral"

    def _score_macd(self, indicators: IndicatorResult, reasons: list[str]) -> tuple[int, str]:
        """Score MACD based on crossover status.

        - Bullish crossover (histogram > 0, MACD > signal) = +20
        - Weak momentum (histogram turning positive) = +10
        - Bearish = 0
        """
        histogram = indicators.macd_histogram
        macd = indicators.macd_value
        signal = indicators.macd_signal

        if histogram > 0 and macd > signal:
            reasons.append("MACD bullish crossover")
            return 20, "bullish"
        elif histogram > -0.1 and macd > signal * 0.95:
            reasons.append("MACD weak momentum (turning bullish)")
            return 10, "weak_bullish"
        else:
            return 0, "bearish"

    def _score_volume(self, indicators: IndicatorResult, reasons: list[str]) -> tuple[int, str]:
        """Score volume based on accumulation pattern.

        - Accumulation (volume > 1.5x avg) = +15
        - Neutral (volume ~ avg) = +8
        - Weak (volume < avg) = 0
        """
        if indicators.avg_volume == 0:
            return 0, "unknown"

        ratio = indicators.current_volume / indicators.avg_volume

        if ratio >= self.VOLUME_ACCUMULATION_MULTIPLIER:
            reasons.append(f"Accumulation volume ({ratio:.1f}x avg)")
            return 15, "accumulation"
        elif ratio >= self.VOLUME_NEUTRAL_MULTIPLIER:
            return 8, "neutral"
        else:
            return 0, "weak"

    def _score_support(self, indicators: IndicatorResult, reasons: list[str]) -> tuple[int, str]:
        """Score based on proximity to support/resistance.

        - Near strong support = +15
        - Mid-range = +5
        - Near resistance = 0
        """
        price = indicators.current_price
        support = indicators.support_level
        resistance = indicators.resistance_level

        if support == 0 or resistance == 0:
            return 0, "unknown"

        # Check if near resistance (bad)
        resistance_distance = (resistance - price) / resistance
        if resistance_distance <= self.RESISTANCE_PROXIMITY_PERCENT:
            return 0, "resistance"

        # Check if near support (good)
        support_distance = (price - support) / support
        if support_distance <= self.SUPPORT_PROXIMITY_PERCENT:
            reasons.append("Price near strong support zone")
            return 15, "near_support"

        # Mid-range
        return 5, "mid_range"
