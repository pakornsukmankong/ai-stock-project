"""Multi-Timeframe (MTF) Analysis Engine.

Analyzes stocks across multiple timeframes to confirm signals:
- Daily (1D): Higher timeframe → confirms overall trend direction
- 4-Hour (4H): Mid timeframe → validates momentum alignment
- 1-Hour (1H): Lower timeframe → identifies precise entry timing

Strategy:
- Higher timeframe trend must align with lower timeframe signal
- Confluence across timeframes increases signal confidence
- Divergence between timeframes reduces confidence or blocks signal
"""

from dataclasses import dataclass, field
from typing import Optional

from app.services.indicator_engine import IndicatorEngine, IndicatorResult
from app.services.market_data import MarketDataService


# Yahoo Finance interval/period constraints:
# - 1h: max ~730 days, practical free limit ~60 days
# - 4h: not directly supported, use 1h and resample
# - 1d: up to 10+ years
TIMEFRAME_CONFIG = {
    "1d": {"interval": "1d", "period": "1y", "min_bars": 200},
    "4h": {"interval": "1h", "period": "60d", "min_bars": 200},  # resample 1h → 4h
    "1h": {"interval": "1h", "period": "30d", "min_bars": 200},
}


@dataclass
class TimeframeAnalysis:
    """Analysis result for a single timeframe."""

    timeframe: str
    indicators: Optional[IndicatorResult] = None
    trend_direction: str = "neutral"  # "bullish", "bearish", "neutral"
    momentum_state: str = "neutral"  # "bullish", "bearish", "neutral"
    macd_state: str = "neutral"  # "bullish", "bearish", "neutral"
    is_valid: bool = False


@dataclass
class MTFResult:
    """Combined multi-timeframe analysis result."""

    daily: TimeframeAnalysis = field(default_factory=lambda: TimeframeAnalysis(timeframe="1d"))
    four_hour: TimeframeAnalysis = field(default_factory=lambda: TimeframeAnalysis(timeframe="4h"))
    one_hour: TimeframeAnalysis = field(default_factory=lambda: TimeframeAnalysis(timeframe="1h"))

    # MTF confluence scoring
    trend_alignment: str = "neutral"  # "strong_bullish", "bullish", "neutral", "bearish", "conflicting"
    momentum_alignment: str = "neutral"
    mtf_bonus_score: int = 0  # Extra points (0 to 15) added to signal engine
    mtf_penalty_score: int = 0  # Penalty points (0 to 20) subtracted from signal
    confluence_reasons: list = field(default_factory=list)

    @property
    def is_aligned_bullish(self) -> bool:
        """Check if all timeframes align bullish."""
        return self.trend_alignment in ("strong_bullish", "bullish")

    @property
    def has_divergence(self) -> bool:
        """Check if there's conflicting signals between timeframes."""
        return self.trend_alignment == "conflicting"


class MTFEngine:
    """Multi-Timeframe Analysis Engine.

    Fetches data for multiple timeframes, calculates indicators for each,
    and produces a confluence score that adjusts the main signal engine scoring.
    """

    def __init__(self) -> None:
        self.market_data = MarketDataService()
        self.indicator_engine = IndicatorEngine()

    async def analyze(
        self,
        symbol: str,
        daily_df=None,
        daily_indicators: Optional[IndicatorResult] = None,
    ) -> MTFResult:
        """Run multi-timeframe analysis for a symbol.

        Args:
            symbol: Stock ticker symbol
            daily_df: Pre-fetched daily OHLCV (currently unused, reserved)
            daily_indicators: Pre-computed daily indicators from the caller.
                When provided, the daily timeframe is reused instead of being
                re-fetched and re-calculated.

        Returns:
            MTFResult with timeframe analyses and confluence scoring
        """
        result = MTFResult()

        # Daily timeframe — reuse the caller's already-computed indicators when
        # available to avoid a redundant fetch + 200-bar recalculation.
        if daily_indicators is not None:
            result.daily = self._build_from_indicators("1d", daily_indicators)
        else:
            result.daily = await self._analyze_timeframe(symbol, "1d")

        # Fetch hourly data ONCE (60d) and derive both 4H and 1H from it,
        # rather than fetching overlapping 1H ranges twice.
        hourly_df = await self.market_data.fetch_ohlcv(
            symbol=symbol, interval="1h", period="60d"
        )
        if hourly_df is not None and not hourly_df.empty:
            result.four_hour = self._analyze_df("4h", self._resample_to_4h(hourly_df))
            result.one_hour = self._analyze_df("1h", self._slice_recent(hourly_df, days=30))

        # Calculate confluence
        self._calculate_confluence(result)

        return result

    async def _analyze_timeframe(self, symbol: str, timeframe: str) -> TimeframeAnalysis:
        """Fetch a single timeframe and analyze it."""
        config = TIMEFRAME_CONFIG[timeframe]
        try:
            df = await self.market_data.fetch_ohlcv(
                symbol=symbol,
                interval=config["interval"],
                period=config["period"],
            )
            # For 4H: resample 1H data to 4H candles
            if df is not None and not df.empty and timeframe == "4h":
                df = self._resample_to_4h(df)
            return self._analyze_df(timeframe, df)
        except Exception as e:
            print(f"MTF error for {symbol} [{timeframe}]: {e}")
            return TimeframeAnalysis(timeframe=timeframe)

    def _analyze_df(self, timeframe: str, df) -> TimeframeAnalysis:
        """Analyze an OHLCV DataFrame already at the target timeframe."""
        analysis = TimeframeAnalysis(timeframe=timeframe)
        config = TIMEFRAME_CONFIG[timeframe]

        try:
            if df is None or df.empty:
                return analysis

            # Check minimum data requirement (relax to 50 bars for intraday)
            if len(df) < config["min_bars"] and len(df) < 50:
                return analysis

            # Calculate indicators
            indicators = self.indicator_engine.calculate(df)
            if indicators is None:
                # Try with relaxed requirement for intraday
                if len(df) >= 50:
                    indicators = self._calculate_relaxed(df)
                if indicators is None:
                    return analysis

            analysis = self._build_from_indicators(timeframe, indicators)

        except Exception as e:
            print(f"MTF error [{timeframe}]: {e}")

        return analysis

    def _build_from_indicators(self, timeframe: str, indicators: IndicatorResult) -> TimeframeAnalysis:
        """Build a TimeframeAnalysis from already-computed indicators."""
        analysis = TimeframeAnalysis(timeframe=timeframe)
        analysis.indicators = indicators
        analysis.is_valid = True
        analysis.trend_direction = self._classify_trend(indicators)
        analysis.momentum_state = self._classify_momentum(indicators)
        analysis.macd_state = self._classify_macd(indicators)
        return analysis

    def _slice_recent(self, df, days: int):
        """Return rows within the last `days` of the DataFrame's time index."""
        import pandas as pd

        cutoff = df.index.max() - pd.Timedelta(days=days)
        return df[df.index >= cutoff]

    def _resample_to_4h(self, df):
        """Resample 1H DataFrame to 4H candles."""
        import pandas as pd

        resampled = df.resample("4h").agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }).dropna()

        return resampled

    def _calculate_relaxed(self, df) -> Optional[IndicatorResult]:
        """Calculate indicators with relaxed data requirements for intraday.

        Uses shorter EMA periods when 200-bar data isn't available.
        Falls back to what's calculable.
        """
        import ta

        if len(df) < 50:
            return None

        try:
            result = IndicatorResult()
            result.current_price = float(df["close"].iloc[-1])

            # EMAs - use what's available
            if len(df) >= 9:
                result.ema_9 = float(ta.trend.EMAIndicator(close=df["close"], window=9).ema_indicator().iloc[-1])
            if len(df) >= 21:
                result.ema_21 = float(ta.trend.EMAIndicator(close=df["close"], window=21).ema_indicator().iloc[-1])
            if len(df) >= 50:
                result.ema_50 = float(ta.trend.EMAIndicator(close=df["close"], window=50).ema_indicator().iloc[-1])
            if len(df) >= 200:
                result.ema_200 = float(ta.trend.EMAIndicator(close=df["close"], window=200).ema_indicator().iloc[-1])
            else:
                # Use longest available EMA as proxy
                longest = min(len(df) - 1, 100)
                if longest > 50:
                    result.ema_200 = float(
                        ta.trend.EMAIndicator(close=df["close"], window=longest).ema_indicator().iloc[-1]
                    )

            # MACD
            if len(df) >= 35:
                macd_indicator = ta.trend.MACD(close=df["close"], window_slow=26, window_fast=12, window_sign=9)
                result.macd_value = float(macd_indicator.macd().iloc[-1])
                result.macd_signal = float(macd_indicator.macd_signal().iloc[-1])
                result.macd_histogram = float(macd_indicator.macd_diff().iloc[-1])

            # RSI
            if len(df) >= 15:
                rsi_indicator = ta.momentum.RSIIndicator(close=df["close"], window=14)
                result.rsi = float(rsi_indicator.rsi().iloc[-1])
                if result.rsi > 70:
                    result.rsi_state = "overbought"
                elif result.rsi < 30:
                    result.rsi_state = "oversold"
                else:
                    result.rsi_state = "neutral"

            # Stochastic
            if len(df) >= 17:
                stoch = ta.momentum.StochasticOscillator(
                    high=df["high"], low=df["low"], close=df["close"],
                    window=14, smooth_window=3
                )
                result.stoch_k = float(stoch.stoch().iloc[-1])
                result.stoch_d = float(stoch.stoch_signal().iloc[-1])

            # SuperTrend
            if len(df) >= 15:
                self.indicator_engine._calculate_supertrend(df, result)

            # Volume
            if len(df) >= 20:
                result.avg_volume = float(df["volume"].rolling(window=20).mean().iloc[-1])
                result.current_volume = float(df["volume"].iloc[-1])

            return result

        except Exception as e:
            print(f"Error in relaxed indicator calculation: {e}")
            return None

    def _classify_trend(self, indicators: IndicatorResult) -> str:
        """Classify overall trend direction from indicators."""
        price = indicators.current_price

        is_above_ema50 = price > indicators.ema_50 if indicators.ema_50 > 0 else False
        is_above_ema200 = price > indicators.ema_200 if indicators.ema_200 > 0 else False
        is_supertrend_bullish = indicators.supertrend_direction == "bullish"

        bullish_signals = sum([is_above_ema50, is_above_ema200, is_supertrend_bullish])

        if bullish_signals >= 3:
            return "bullish"
        elif bullish_signals <= 0:
            return "bearish"
        else:
            return "neutral"

    def _classify_momentum(self, indicators: IndicatorResult) -> str:
        """Classify momentum state."""
        rsi_bullish = 40 <= indicators.rsi <= 65
        stoch_bullish = indicators.stoch_k > indicators.stoch_d

        if rsi_bullish and stoch_bullish:
            return "bullish"
        elif indicators.rsi > 70 or (indicators.stoch_k > 80 and indicators.stoch_k < indicators.stoch_d):
            return "bearish"
        else:
            return "neutral"

    def _classify_macd(self, indicators: IndicatorResult) -> str:
        """Classify MACD state."""
        if indicators.macd_histogram > 0 and indicators.macd_value > indicators.macd_signal:
            return "bullish"
        elif indicators.macd_histogram < 0 and indicators.macd_value < indicators.macd_signal:
            return "bearish"
        else:
            return "neutral"

    def _calculate_confluence(self, result: MTFResult) -> None:
        """Calculate multi-timeframe confluence score.

        Scoring logic:
        - All 3 timeframes bullish trend → +15 bonus
        - 2/3 timeframes bullish trend → +10 bonus
        - Daily bullish + lower bearish → +5 (trend with pullback entry)
        - Daily bearish + lower bullish → -15 penalty (counter-trend)
        - All bearish → -20 penalty
        """
        reasons = []
        bonus = 0
        penalty = 0

        # Count valid timeframes
        valid_tfs = [
            tf for tf in [result.daily, result.four_hour, result.one_hour]
            if tf.is_valid
        ]

        if not valid_tfs:
            result.trend_alignment = "neutral"
            result.mtf_bonus_score = 0
            result.mtf_penalty_score = 0
            return

        # --- Trend Alignment ---
        trend_directions = [tf.trend_direction for tf in valid_tfs]
        bullish_count = trend_directions.count("bullish")
        bearish_count = trend_directions.count("bearish")

        if bullish_count == len(valid_tfs):
            result.trend_alignment = "strong_bullish"
            bonus += 15
            reasons.append(f"MTF: All {len(valid_tfs)} timeframes confirm bullish trend")
        elif bullish_count >= 2:
            result.trend_alignment = "bullish"
            bonus += 10
            reasons.append(f"MTF: {bullish_count}/{len(valid_tfs)} timeframes bullish")
        elif bearish_count == len(valid_tfs):
            result.trend_alignment = "bearish"
            penalty += 20
            reasons.append(f"MTF: All timeframes bearish — counter-trend risk")
        elif result.daily.is_valid and result.daily.trend_direction == "bearish":
            # Daily bearish but lower timeframes bullish = dangerous
            if bullish_count > 0:
                result.trend_alignment = "conflicting"
                penalty += 15
                reasons.append("MTF: Daily trend bearish, lower TFs diverge — high risk")
        elif result.daily.is_valid and result.daily.trend_direction == "bullish":
            # Daily bullish but lower timeframes pulling back (good entry)
            if bearish_count > 0:
                result.trend_alignment = "bullish"
                bonus += 5
                reasons.append("MTF: Daily bullish + lower TF pullback — potential entry")
        else:
            result.trend_alignment = "neutral"

        # --- Momentum Alignment ---
        momentum_states = [tf.momentum_state for tf in valid_tfs if tf.is_valid]
        bullish_momentum = momentum_states.count("bullish")

        if bullish_momentum == len(momentum_states) and len(momentum_states) >= 2:
            result.momentum_alignment = "bullish"
            bonus += 5
            reasons.append("MTF: Momentum aligned bullish across timeframes")
        elif momentum_states.count("bearish") == len(momentum_states):
            result.momentum_alignment = "bearish"
            penalty += 5
            reasons.append("MTF: Momentum bearish across all timeframes")
        else:
            result.momentum_alignment = "neutral"

        # --- MACD Alignment (extra confirmation) ---
        macd_states = [tf.macd_state for tf in valid_tfs if tf.is_valid]
        if macd_states.count("bullish") == len(macd_states) and len(macd_states) >= 2:
            bonus += 5
            reasons.append("MTF: MACD bullish across all timeframes")

        # Cap bonus/penalty
        result.mtf_bonus_score = min(bonus, 25)
        result.mtf_penalty_score = min(penalty, 25)
        result.confluence_reasons = reasons
