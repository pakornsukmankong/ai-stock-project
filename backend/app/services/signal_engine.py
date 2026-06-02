from dataclasses import dataclass, field
from typing import Optional
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
    reasons: list
    rsi_status: str
    macd_status: str
    trend_status: str
    support_status: str
    volume_status: str

    # Multi-Timeframe fields
    mtf_bonus: int = 0
    mtf_penalty: int = 0
    mtf_adjusted_score: int = 0
    mtf_confluence: str = "not_available"  # trend alignment from MTF
    mtf_reasons: list = field(default_factory=list)


class SignalEngine:
    """Scoring-based signal engine using comprehensive indicators.

    Scoring system (max 100 pts):
    - Trend (EMA + SuperTrend):  30 pts
    - Momentum (RSI + Stoch):    20 pts
    - MACD:                      20 pts
    - Volume + Volatility:       15 pts
    - Support/Patterns:          15 pts

    Buy signal triggers when total score >= 60.
    """

    VOLUME_ACCUMULATION_MULTIPLIER = 1.5

    def evaluate(self, indicators: IndicatorResult) -> SignalResult:
        """Evaluate indicators using scoring system (single timeframe, backward compatible)."""
        return self._run_scoring(indicators)

    def evaluate_with_mtf(self, indicators: IndicatorResult, mtf_result) -> SignalResult:
        """Evaluate indicators with Multi-Timeframe confluence adjustment.

        The MTF result provides bonus/penalty scores based on higher timeframe alignment.
        - Bonus: added when multiple timeframes confirm the signal (max +25)
        - Penalty: subtracted when higher timeframes conflict (max -25)

        Final adjusted score determines the buy signal, not the raw score.
        """
        signal = self._run_scoring(indicators)

        # Apply MTF adjustment
        if mtf_result is not None:
            signal.mtf_bonus = mtf_result.mtf_bonus_score
            signal.mtf_penalty = mtf_result.mtf_penalty_score
            signal.mtf_confluence = mtf_result.trend_alignment
            signal.mtf_reasons = mtf_result.confluence_reasons

            # Adjusted score: base + bonus - penalty (clamped 0-125)
            adjusted = signal.total_score + signal.mtf_bonus - signal.mtf_penalty
            signal.mtf_adjusted_score = max(0, min(adjusted, 125))

            # Use adjusted score for buy signal decision
            signal.is_buy_signal = signal.mtf_adjusted_score >= BUY_SIGNAL_THRESHOLD

            # Update reasons with MTF info
            signal.reasons.extend(signal.mtf_reasons)
        else:
            signal.mtf_adjusted_score = signal.total_score

        return signal

    def _run_scoring(self, indicators: IndicatorResult) -> SignalResult:
        """Internal scoring logic."""
        reasons = []

        # Trend Score (30 pts) - EMA alignment + SuperTrend
        trend_score, trend_status = self._score_trend(indicators, reasons)

        # Momentum Score (20 pts) - RSI + Stochastic
        rsi_score, rsi_status = self._score_momentum(indicators, reasons)

        # MACD Score (20 pts)
        macd_score, macd_status = self._score_macd(indicators, reasons)

        # Volume + Volatility Score (15 pts)
        volume_score, volume_status = self._score_volume_volatility(indicators, reasons)

        # Support/Patterns Score (15 pts)
        support_score, support_status = self._score_support_patterns(indicators, reasons)

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

    def _score_trend(self, ind: IndicatorResult, reasons: list) -> tuple:
        """Score trend: EMA alignment + SuperTrend (max 30 pts).

        - Full bullish alignment (price > EMA9 > EMA21 > EMA50 > EMA200) + SuperTrend bullish = 30
        - Partial alignment + SuperTrend bullish = 20
        - Price above EMA200 only = 10
        - Below EMA200 = 0
        """
        score = 0
        price = ind.current_price

        # Check EMA alignment
        is_full_alignment = (
            price > ind.ema_9 > ind.ema_21 > ind.ema_50 > ind.ema_200
        )
        is_above_ema200 = price > ind.ema_200
        is_supertrend_bullish = ind.supertrend_direction == "bullish"

        if is_full_alignment and is_supertrend_bullish:
            score = 30
            reasons.append("Full EMA alignment (9>21>50>200) + SuperTrend bullish")
            status = "strong_uptrend"
        elif is_above_ema200 and is_supertrend_bullish:
            score = 20
            reasons.append("Above EMA200 + SuperTrend bullish")
            status = "uptrend"
        elif is_above_ema200:
            score = 10
            status = "above_ema200"
        else:
            score = 0
            status = "downtrend"

        return score, status

    def _score_momentum(self, ind: IndicatorResult, reasons: list) -> tuple:
        """Score momentum: RSI + Stochastic (max 20 pts).

        - RSI 35-50 in uptrend + Stoch %K > %D = 20
        - RSI < 30 (oversold) + Stoch < 20 = 15 (reversal potential)
        - RSI > 70 = 0
        """
        score = 0
        price = ind.current_price
        is_uptrend = price > ind.ema_200

        # RSI + Stochastic combined
        if 35 <= ind.rsi <= 50 and is_uptrend and ind.stoch_k > ind.stoch_d:
            score = 20
            reasons.append(f"RSI {ind.rsi:.1f} pullback + Stoch bullish cross")
            status = "pullback_uptrend"
        elif ind.rsi < 30 and ind.stoch_k < 20:
            score = 15
            reasons.append(f"RSI {ind.rsi:.1f} oversold + Stoch oversold (reversal)")
            status = "oversold"
        elif ind.rsi < 40 and ind.stoch_k > ind.stoch_d:
            score = 10
            reasons.append(f"RSI {ind.rsi:.1f} + Stoch turning up")
            status = "recovering"
        elif ind.rsi > 70:
            score = 0
            status = "overbought"
        else:
            score = 5
            status = "neutral"

        return score, status

    def _score_macd(self, ind: IndicatorResult, reasons: list) -> tuple:
        """Score MACD (max 20 pts).

        - Bullish crossover (histogram > 0, MACD > signal) = 20
        - Histogram turning positive = 10
        - Bearish = 0
        """
        histogram = ind.macd_histogram
        macd = ind.macd_value
        signal = ind.macd_signal

        if histogram > 0 and macd > signal:
            reasons.append("MACD bullish crossover")
            return 20, "bullish"
        elif histogram > -0.1 and macd > signal * 0.95:
            reasons.append("MACD momentum turning bullish")
            return 10, "weak_bullish"
        else:
            return 0, "bearish"

    def _score_volume_volatility(self, ind: IndicatorResult, reasons: list) -> tuple:
        """Score volume + Bollinger Band position (max 15 pts).

        - Accumulation volume + price near lower BB = 15
        - Accumulation volume = 10
        - Normal volume + near lower BB = 8
        - Weak = 0
        """
        if ind.avg_volume == 0:
            return 0, "unknown"

        ratio = ind.current_volume / ind.avg_volume
        is_accumulation = ratio >= self.VOLUME_ACCUMULATION_MULTIPLIER
        is_near_lower_bb = ind.bb_position in ("near_lower", "below_lower")

        if is_accumulation and is_near_lower_bb:
            reasons.append(f"Accumulation volume ({ratio:.1f}x) + near lower Bollinger Band")
            return 15, "strong_accumulation"
        elif is_accumulation:
            reasons.append(f"Accumulation volume ({ratio:.1f}x avg)")
            return 10, "accumulation"
        elif is_near_lower_bb:
            reasons.append("Price near lower Bollinger Band (potential bounce)")
            return 8, "bb_bounce"
        elif ratio >= 1.0:
            return 4, "neutral"
        else:
            return 0, "weak"

    def _score_support_patterns(self, ind: IndicatorResult, reasons: list) -> tuple:
        """Score support proximity + candlestick patterns (max 15 pts).

        - Near pivot support + bullish pattern = 15
        - Near pivot support = 10
        - Bullish candlestick pattern only = 8
        - Near resistance = 0
        """
        price = ind.current_price
        pivot = ind.pivot_levels

        # Check proximity to support/resistance
        is_near_support = False
        is_near_resistance = False

        if pivot.s1 > 0:
            support_distance = abs(price - pivot.s1) / price
            is_near_support = support_distance <= 0.02

        if pivot.r1 > 0:
            resistance_distance = abs(price - pivot.r1) / price
            is_near_resistance = resistance_distance <= 0.02

        # Check bullish patterns
        patterns = ind.candle_patterns.get_detected()
        has_bullish_pattern = any(
            p in patterns for p in ["Hammer", "Bullish Engulfing", "Doji"]
        )

        if is_near_resistance:
            return 0, "resistance"

        if is_near_support and has_bullish_pattern:
            reasons.append(f"Near support (S1: ${pivot.s1:.2f}) + {patterns[0]} pattern")
            return 15, "strong_support"
        elif is_near_support:
            reasons.append(f"Price near pivot support S1 (${pivot.s1:.2f})")
            return 10, "near_support"
        elif has_bullish_pattern:
            reasons.append(f"Candlestick pattern: {', '.join(patterns)}")
            return 8, "pattern"
        else:
            return 3, "mid_range"
