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
    """Buy-on-Dip scoring engine.

    Strategy: Buy when price pulls back to support levels within an existing
    uptrend, NOT when price is already extended/high.

    Scoring system (max 100 pts):
    - Trend Context (uptrend confirmed):  25 pts
    - Dip/Pullback Detection:             25 pts
    - Reversal Confirmation:              20 pts
    - Volume + Volatility:                15 pts
    - Support/Patterns:                   15 pts

    Buy signal triggers when total score >= 60.
    """

    VOLUME_ACCUMULATION_MULTIPLIER = 1.3

    def evaluate(self, indicators: IndicatorResult) -> SignalResult:
        """Evaluate indicators using Buy-on-Dip scoring (backward compatible)."""
        return self._run_scoring(indicators)

    def evaluate_with_mtf(self, indicators: IndicatorResult, mtf_result) -> SignalResult:
        """Evaluate indicators with Multi-Timeframe confluence adjustment."""
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
        """Internal Buy-on-Dip scoring logic."""
        reasons = []

        # Trend Context (25 pts) - Is the stock in an uptrend worth buying dips in?
        trend_score, trend_status = self._score_trend_context(indicators, reasons)

        # Dip/Pullback Detection (25 pts) - Has price pulled back to a buy zone?
        rsi_score, rsi_status = self._score_dip_detection(indicators, reasons)

        # Reversal Confirmation (20 pts) - Are reversal signals appearing?
        macd_score, macd_status = self._score_reversal_confirmation(indicators, reasons)

        # Volume + Volatility (15 pts) - Accumulation at support?
        volume_score, volume_status = self._score_volume_volatility(indicators, reasons)

        # Support/Patterns (15 pts) - Near key support with bullish patterns?
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

    def _score_trend_context(self, ind: IndicatorResult, reasons: list) -> tuple:
        """Score trend context: Is the stock worth buying dips in? (max 25 pts).

        We want to buy dips in UPTRENDS, not catch falling knives.
        Key: Price should be above EMA200 (long-term uptrend intact),
        but we DON'T reward being above ALL EMAs (that means overextended).

        - Above EMA200 + EMA50 rising (uptrend intact) = 25
        - Above EMA200 only (basic uptrend) = 15
        - Below EMA200 but SuperTrend bullish (early reversal) = 10
        - Below EMA200 + bearish = 0 (no dip buying in downtrend)
        """
        price = ind.current_price
        is_above_ema200 = price > ind.ema_200
        is_above_ema50 = price > ind.ema_50
        is_ema50_above_ema200 = ind.ema_50 > ind.ema_200  # EMA50 rising above EMA200
        is_supertrend_bullish = ind.supertrend_direction == "bullish"

        # Overextended penalty: if price is way above EMA21 (>5%), less attractive dip
        if ind.ema_21 > 0:
            distance_from_ema21 = (price - ind.ema_21) / ind.ema_21
        else:
            distance_from_ema21 = 0

        if is_above_ema200 and is_ema50_above_ema200:
            # Strong uptrend structure intact — good candidate for dip buying
            if distance_from_ema21 > 0.05:
                # Price extended >5% above EMA21 — not a dip yet
                score = 10
                reasons.append("Uptrend intact but price overextended (+5% above EMA21)")
                status = "overextended"
            else:
                score = 25
                reasons.append("Strong uptrend (EMA50>EMA200) — dip buy candidate")
                status = "uptrend_dip_zone"
        elif is_above_ema200:
            score = 15
            reasons.append("Above EMA200 — basic uptrend intact")
            status = "basic_uptrend"
        elif is_supertrend_bullish and ind.ema_9 > ind.ema_21:
            # Short-term recovery, potential trend reversal
            score = 10
            reasons.append("SuperTrend bullish + short EMA recovering")
            status = "early_reversal"
        else:
            score = 0
            status = "downtrend"

        return score, status

    def _score_dip_detection(self, ind: IndicatorResult, reasons: list) -> tuple:
        """Score dip/pullback detection (max 25 pts).

        This is the CORE of buy-on-dip. We want price to have pulled back
        into a "buy zone" rather than being at highs.

        Buy zone indicators:
        - RSI oversold (< 35) or pulled back from high = strong dip
        - Price near/below EMA21 in uptrend = pullback to mean
        - Stochastic oversold turning up = timing entry
        - Price near lower Bollinger Band = stretched to downside

        - RSI < 30 + Stoch oversold + near EMA support = 25 (perfect dip)
        - RSI 30-40 + price near EMA21 + Stoch turning = 20
        - RSI 40-50 + pullback signals = 15
        - RSI > 60 (not a dip) = 0-5
        """
        price = ind.current_price
        is_uptrend = price > ind.ema_200 or ind.ema_50 > ind.ema_200

        # Calculate distance from EMA21 (negative = below EMA21 = pulled back)
        if ind.ema_21 > 0:
            ema21_distance = (price - ind.ema_21) / ind.ema_21
        else:
            ema21_distance = 0

        is_near_or_below_ema21 = ema21_distance <= 0.01  # within 1% or below
        is_stoch_oversold_turning = ind.stoch_k < 30 and ind.stoch_k > ind.stoch_d
        is_stoch_oversold = ind.stoch_k < 25
        is_near_lower_bb = ind.bb_position in ("near_lower", "below_lower")
        has_divergence = ind.rsi_bullish_divergence or ind.macd_bullish_divergence

        # Deep dip: RSI oversold + Stoch oversold + near support
        if ind.rsi < 30 and is_stoch_oversold and is_near_lower_bb:
            score = 25
            reasons.append(f"Deep dip: RSI {ind.rsi:.1f} oversold + Stoch {ind.stoch_k:.0f} + at lower BB")
            status = "deep_dip"
        elif has_divergence and is_uptrend and (is_near_or_below_ema21 or is_near_lower_bb) and ind.rsi < 50:
            # Strong uptrends rarely hit RSI<30; divergence lets a shallower
            # pullback still qualify as a high-quality dip.
            score = 23
            reasons.append(f"Divergence dip: bullish divergence at pullback (RSI {ind.rsi:.1f})")
            status = "divergence_dip"
        elif ind.rsi < 35 and is_near_or_below_ema21 and is_uptrend:
            score = 22
            reasons.append(f"Strong pullback: RSI {ind.rsi:.1f} + price at/below EMA21 in uptrend")
            status = "strong_pullback"
        elif ind.rsi < 40 and is_stoch_oversold_turning and is_uptrend:
            score = 20
            reasons.append(f"Pullback + reversal: RSI {ind.rsi:.1f} + Stoch turning up from oversold")
            status = "pullback_reversal"
        elif ind.rsi < 45 and is_near_or_below_ema21 and is_uptrend:
            score = 15
            reasons.append(f"Moderate pullback: RSI {ind.rsi:.1f} + price near EMA21")
            status = "moderate_pullback"
        elif ind.rsi < 50 and is_near_lower_bb:
            score = 12
            reasons.append(f"RSI {ind.rsi:.1f} + near lower Bollinger Band")
            status = "bb_dip"
        elif 50 <= ind.rsi <= 60:
            # Neutral — not really a dip
            score = 5
            status = "neutral"
        elif ind.rsi > 60:
            # NOT a dip — price is strong/high, penalize
            score = 0
            status = "no_dip"
        else:
            score = 8
            status = "mild_pullback"

        return score, status

    def _score_reversal_confirmation(self, ind: IndicatorResult, reasons: list) -> tuple:
        """Score reversal confirmation signals (max 20 pts).

        After detecting a dip we need confirmation that price is actually TURNING
        back up. These rely on transition flags computed on closed bars (real
        crosses, not just current states), plus bullish divergence — the single
        strongest classic reversal signal.
        """
        # Real transitions detected on closed bars (see IndicatorEngine).
        is_macd_bullish_cross = ind.macd_bullish_cross
        is_macd_turning = ind.macd_turning_up
        is_stoch_bullish_cross = ind.stoch_bullish_cross and ind.stoch_k < 50
        has_divergence = ind.rsi_bullish_divergence or ind.macd_bullish_divergence

        if has_divergence and (is_macd_bullish_cross or is_stoch_bullish_cross):
            score = 20
            div_kind = "RSI" if ind.rsi_bullish_divergence else "MACD"
            reasons.append(f"Strong reversal: bullish {div_kind} divergence + momentum cross")
            status = "divergence_cross"
        elif is_macd_bullish_cross and is_stoch_bullish_cross:
            score = 18
            reasons.append("Reversal confirmed: MACD bullish cross + Stoch cross below 50")
            status = "strong_reversal"
        elif has_divergence:
            div_kind = "RSI" if ind.rsi_bullish_divergence else "MACD"
            score = 15
            reasons.append(f"Bullish {div_kind} divergence — price falling but momentum rising")
            status = "divergence"
        elif is_macd_bullish_cross:
            score = 13
            reasons.append("MACD bullish crossover — histogram flipped positive")
            status = "macd_reversal"
        elif is_macd_turning and is_stoch_bullish_cross:
            score = 11
            reasons.append("Early reversal: MACD histogram rising + Stoch cross below 50")
            status = "early_reversal"
        elif is_stoch_bullish_cross and ind.stoch_k < 30:
            score = 9
            reasons.append(f"Stochastic bullish cross at {ind.stoch_k:.0f} (oversold zone)")
            status = "stoch_reversal"
        elif is_macd_turning:
            score = 6
            reasons.append("MACD histogram turning up (rising while still negative)")
            status = "momentum_improving"
        else:
            score = 0
            status = "no_reversal"

        return score, status

    def _score_volume_volatility(self, ind: IndicatorResult, reasons: list) -> tuple:
        """Score volume at dip + Bollinger Band position (max 15 pts).

        For buy-on-dip, we want:
        - Declining volume on the dip (sellers exhausted) OR
        - Volume spike at support (capitulation/accumulation)
        - Price at lower Bollinger Band (mean reversion setup)

        - Volume spike at lower BB (capitulation buy) = 15
        - Low volume dip + near lower BB = 12
        - Near lower BB only = 8
        - Normal conditions = 3
        """
        if ind.avg_volume == 0:
            return 0, "unknown"

        ratio = ind.current_volume / ind.avg_volume
        is_high_volume = ratio >= self.VOLUME_ACCUMULATION_MULTIPLIER
        is_low_volume = ratio < 0.8  # Below average = sellers exhausted
        is_near_lower_bb = ind.bb_position in ("near_lower", "below_lower")

        if is_high_volume and is_near_lower_bb:
            # Volume spike at support — capitulation/accumulation
            reasons.append(f"Volume spike ({ratio:.1f}x) at lower BB — possible capitulation buy")
            return 15, "capitulation_buy"
        elif is_low_volume and is_near_lower_bb:
            # Dip on low volume = sellers exhausted, good sign
            reasons.append(f"Low volume dip ({ratio:.1f}x) at lower BB — sellers exhausted")
            return 12, "exhaustion_dip"
        elif is_near_lower_bb:
            reasons.append("Price at lower Bollinger Band — mean reversion zone")
            return 8, "bb_bounce"
        elif is_high_volume and ind.rsi < 40:
            # Volume accumulation during pullback
            reasons.append(f"Accumulation volume ({ratio:.1f}x) during pullback")
            return 7, "accumulation"
        elif ratio >= 0.8:
            return 3, "neutral"
        else:
            return 0, "weak"

    def _score_support_patterns(self, ind: IndicatorResult, reasons: list) -> tuple:
        """Score support proximity + reversal candlestick patterns (max 15 pts).

        For buy-on-dip, we specifically look for:
        - Price near pivot support (S1/S2) = potential bounce zone
        - Bullish reversal patterns (Hammer, Bullish Engulfing) at support
        - NOT near resistance (that's where you sell, not buy)

        - Near S1/S2 + Hammer/Engulfing = 15 (textbook dip buy)
        - Near S1/S2 support = 10
        - Bullish reversal pattern only = 8
        - Near EMA50 support = 6
        - Near resistance = 0 (penalize)
        """
        price = ind.current_price
        pivot = ind.pivot_levels

        # Check proximity to support/resistance
        is_near_s1 = False
        is_near_s2 = False
        is_near_resistance = False
        is_near_ema50 = False

        if pivot.s1 > 0:
            s1_distance = abs(price - pivot.s1) / price
            is_near_s1 = s1_distance <= 0.02

        if pivot.s2 > 0:
            s2_distance = abs(price - pivot.s2) / price
            is_near_s2 = s2_distance <= 0.03

        if pivot.r1 > 0:
            r1_distance = abs(price - pivot.r1) / price
            is_near_resistance = r1_distance <= 0.01

        if ind.ema_50 > 0:
            ema50_distance = abs(price - ind.ema_50) / price
            is_near_ema50 = ema50_distance <= 0.02

        # Check bullish REVERSAL patterns (important for dip buying)
        patterns = ind.candle_patterns.get_detected()
        has_reversal_pattern = any(
            p in patterns for p in ["Hammer", "Bullish Engulfing"]
        )
        has_doji = "Doji" in patterns  # Indecision at support = potential turn

        # Penalize if near resistance
        if is_near_resistance:
            return 0, "at_resistance"

        # Best: at support with reversal pattern
        if (is_near_s1 or is_near_s2) and has_reversal_pattern:
            support_level = pivot.s1 if is_near_s1 else pivot.s2
            reasons.append(f"Dip to support (${support_level:.2f}) + {patterns[0]} reversal pattern")
            return 15, "perfect_dip_buy"
        elif (is_near_s1 or is_near_s2) and has_doji:
            support_level = pivot.s1 if is_near_s1 else pivot.s2
            reasons.append(f"At support (${support_level:.2f}) + Doji (indecision → potential reversal)")
            return 12, "support_doji"
        elif is_near_s1 or is_near_s2:
            support_level = pivot.s1 if is_near_s1 else pivot.s2
            reasons.append(f"Price at pivot support ${support_level:.2f}")
            return 10, "at_support"
        elif is_near_ema50 and has_reversal_pattern:
            reasons.append(f"Pullback to EMA50 + {patterns[0]} pattern")
            return 10, "ema50_reversal"
        elif has_reversal_pattern:
            reasons.append(f"Reversal pattern: {', '.join(patterns)}")
            return 8, "reversal_pattern"
        elif is_near_ema50:
            reasons.append(f"Price pulled back to EMA50 (${ind.ema_50:.2f})")
            return 6, "ema50_support"
        elif has_doji:
            return 4, "doji"
        else:
            return 2, "mid_range"
