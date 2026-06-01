import pandas as pd
import numpy as np
import ta
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class CandlestickPattern:
    """Detected candlestick patterns."""
    hammer: bool = False
    shooting_star: bool = False
    engulfing_bullish: bool = False
    engulfing_bearish: bool = False
    doji: bool = False

    def get_detected(self) -> list[str]:
        """Return list of detected pattern names."""
        patterns = []
        if self.hammer:
            patterns.append("Hammer")
        if self.shooting_star:
            patterns.append("Shooting Star")
        if self.engulfing_bullish:
            patterns.append("Bullish Engulfing")
        if self.engulfing_bearish:
            patterns.append("Bearish Engulfing")
        if self.doji:
            patterns.append("Doji")
        return patterns


@dataclass
class PivotLevels:
    """Pivot points and support/resistance levels."""
    pivot: float = 0.0
    r1: float = 0.0
    r2: float = 0.0
    s1: float = 0.0
    s2: float = 0.0


@dataclass
class IndicatorResult:
    """Holds all calculated technical indicator values."""

    # Price
    current_price: float = 0.0

    # Trend - Moving Averages
    ema_9: float = 0.0
    ema_21: float = 0.0
    ema_50: float = 0.0
    ema_200: float = 0.0

    # Trend - MACD
    macd_value: float = 0.0
    macd_signal: float = 0.0
    macd_histogram: float = 0.0

    # Trend - SuperTrend
    supertrend_direction: str = "neutral"  # "bullish" or "bearish"
    supertrend_value: float = 0.0

    # Momentum - RSI
    rsi: float = 50.0
    rsi_state: str = "neutral"  # "overbought", "oversold", "neutral"

    # Momentum - Stochastic
    stoch_k: float = 50.0
    stoch_d: float = 50.0

    # Volatility - ATR
    atr: float = 0.0

    # Volatility - Bollinger Bands
    bb_upper: float = 0.0
    bb_middle: float = 0.0
    bb_lower: float = 0.0
    bb_position: str = "middle"  # "above_upper", "near_upper", "middle", "near_lower", "below_lower"

    # Volume
    avg_volume: float = 0.0
    current_volume: float = 0.0

    # Price Action - Candlestick Patterns
    candle_patterns: CandlestickPattern = field(default_factory=CandlestickPattern)

    # Market Structure - Pivot Points
    pivot_levels: PivotLevels = field(default_factory=PivotLevels)

    # Legacy fields for signal engine compatibility
    support_level: float = 0.0
    resistance_level: float = 0.0


class IndicatorEngine:
    """Calculates comprehensive technical indicators from OHLCV data."""

    def calculate(self, df: pd.DataFrame) -> Optional[IndicatorResult]:
        """Calculate all technical indicators from OHLCV DataFrame.

        Args:
            df: DataFrame with columns: open, high, low, close, volume

        Returns:
            IndicatorResult with all calculated values, or None if insufficient data
        """
        if df is None or len(df) < 200:
            return None

        try:
            result = IndicatorResult()
            result.current_price = float(df["close"].iloc[-1])

            # A. Trend Indicators
            self._calculate_moving_averages(df, result)
            self._calculate_macd(df, result)
            self._calculate_supertrend(df, result)

            # B. Momentum & Volatility
            self._calculate_rsi(df, result)
            self._calculate_stochastic(df, result)
            self._calculate_atr(df, result)
            self._calculate_bollinger_bands(df, result)

            # Volume
            result.avg_volume = float(df["volume"].rolling(window=20).mean().iloc[-1])
            result.current_volume = float(df["volume"].iloc[-1])

            # C. Price Action & Market Structure
            self._detect_candlestick_patterns(df, result)
            self._calculate_pivot_points(df, result)

            # Legacy support/resistance for signal engine
            result.support_level = result.pivot_levels.s1
            result.resistance_level = result.pivot_levels.r1

            return result

        except Exception as e:
            print(f"Error calculating indicators: {e}")
            return None

    def _calculate_moving_averages(self, df: pd.DataFrame, result: IndicatorResult) -> None:
        """Calculate EMA 9, 21, 50, 200."""
        result.ema_9 = float(ta.trend.EMAIndicator(close=df["close"], window=9).ema_indicator().iloc[-1])
        result.ema_21 = float(ta.trend.EMAIndicator(close=df["close"], window=21).ema_indicator().iloc[-1])
        result.ema_50 = float(ta.trend.EMAIndicator(close=df["close"], window=50).ema_indicator().iloc[-1])
        result.ema_200 = float(ta.trend.EMAIndicator(close=df["close"], window=200).ema_indicator().iloc[-1])

    def _calculate_macd(self, df: pd.DataFrame, result: IndicatorResult) -> None:
        """Calculate MACD (12, 26, 9)."""
        macd_indicator = ta.trend.MACD(
            close=df["close"], window_slow=26, window_fast=12, window_sign=9
        )
        result.macd_value = float(macd_indicator.macd().iloc[-1])
        result.macd_signal = float(macd_indicator.macd_signal().iloc[-1])
        result.macd_histogram = float(macd_indicator.macd_diff().iloc[-1])

    def _calculate_supertrend(self, df: pd.DataFrame, result: IndicatorResult) -> None:
        """Calculate SuperTrend indicator."""
        # SuperTrend using ATR multiplier of 3 and period of 10
        atr_period = 10
        multiplier = 3.0

        high = df["high"]
        low = df["low"]
        close = df["close"]

        # Calculate ATR for SuperTrend
        tr = pd.DataFrame()
        tr["h-l"] = high - low
        tr["h-pc"] = abs(high - close.shift(1))
        tr["l-pc"] = abs(low - close.shift(1))
        tr["tr"] = tr[["h-l", "h-pc", "l-pc"]].max(axis=1)
        atr_st = tr["tr"].rolling(window=atr_period).mean()

        # Basic bands
        hl2 = (high + low) / 2
        upper_band = hl2 + (multiplier * atr_st)
        lower_band = hl2 - (multiplier * atr_st)

        # SuperTrend calculation
        supertrend = pd.Series(index=df.index, dtype=float)
        direction = pd.Series(index=df.index, dtype=int)

        for i in range(atr_period, len(df)):
            if close.iloc[i] > upper_band.iloc[i - 1]:
                direction.iloc[i] = 1  # Bullish
            elif close.iloc[i] < lower_band.iloc[i - 1]:
                direction.iloc[i] = -1  # Bearish
            else:
                direction.iloc[i] = direction.iloc[i - 1] if i > atr_period else 1

            if direction.iloc[i] == 1:
                supertrend.iloc[i] = lower_band.iloc[i]
            else:
                supertrend.iloc[i] = upper_band.iloc[i]

        last_direction = direction.iloc[-1]
        result.supertrend_direction = "bullish" if last_direction == 1 else "bearish"
        result.supertrend_value = float(supertrend.iloc[-1]) if not pd.isna(supertrend.iloc[-1]) else 0.0

    def _calculate_rsi(self, df: pd.DataFrame, result: IndicatorResult) -> None:
        """Calculate RSI (14)."""
        rsi_indicator = ta.momentum.RSIIndicator(close=df["close"], window=14)
        result.rsi = float(rsi_indicator.rsi().iloc[-1])

        if result.rsi > 70:
            result.rsi_state = "overbought"
        elif result.rsi < 30:
            result.rsi_state = "oversold"
        else:
            result.rsi_state = "neutral"

    def _calculate_stochastic(self, df: pd.DataFrame, result: IndicatorResult) -> None:
        """Calculate Stochastic Oscillator (14, 3, 3)."""
        stoch = ta.momentum.StochasticOscillator(
            high=df["high"], low=df["low"], close=df["close"],
            window=14, smooth_window=3
        )
        result.stoch_k = float(stoch.stoch().iloc[-1])
        result.stoch_d = float(stoch.stoch_signal().iloc[-1])

    def _calculate_atr(self, df: pd.DataFrame, result: IndicatorResult) -> None:
        """Calculate ATR (14)."""
        atr_indicator = ta.volatility.AverageTrueRange(
            high=df["high"], low=df["low"], close=df["close"], window=14
        )
        result.atr = float(atr_indicator.average_true_range().iloc[-1])

    def _calculate_bollinger_bands(self, df: pd.DataFrame, result: IndicatorResult) -> None:
        """Calculate Bollinger Bands (20, 2)."""
        bb = ta.volatility.BollingerBands(close=df["close"], window=20, window_dev=2)
        result.bb_upper = float(bb.bollinger_hband().iloc[-1])
        result.bb_middle = float(bb.bollinger_mavg().iloc[-1])
        result.bb_lower = float(bb.bollinger_lband().iloc[-1])

        # Determine position relative to bands
        price = result.current_price
        if price > result.bb_upper:
            result.bb_position = "above_upper"
        elif price > result.bb_upper * 0.99:
            result.bb_position = "near_upper"
        elif price < result.bb_lower:
            result.bb_position = "below_lower"
        elif price < result.bb_lower * 1.01:
            result.bb_position = "near_lower"
        else:
            result.bb_position = "middle"

    def _detect_candlestick_patterns(self, df: pd.DataFrame, result: IndicatorResult) -> None:
        """Detect major candlestick patterns (manual implementation)."""
        if len(df) < 3:
            return

        o = df["open"].iloc[-1]
        h = df["high"].iloc[-1]
        l = df["low"].iloc[-1]
        c = df["close"].iloc[-1]
        body = abs(c - o)
        full_range = h - l

        prev_o = df["open"].iloc[-2]
        prev_c = df["close"].iloc[-2]
        prev_body = abs(prev_c - prev_o)

        if full_range == 0:
            return

        # Doji: very small body relative to range
        if body / full_range < 0.1:
            result.candle_patterns.doji = True

        # Hammer: small body at top, long lower shadow
        lower_shadow = min(o, c) - l
        upper_shadow = h - max(o, c)
        if lower_shadow > body * 2 and upper_shadow < body * 0.5 and c > o:
            result.candle_patterns.hammer = True

        # Shooting Star: small body at bottom, long upper shadow
        if upper_shadow > body * 2 and lower_shadow < body * 0.5 and c < o:
            result.candle_patterns.shooting_star = True

        # Bullish Engulfing: current green candle engulfs previous red
        if prev_c < prev_o and c > o and o <= prev_c and c >= prev_o and body > prev_body:
            result.candle_patterns.engulfing_bullish = True

        # Bearish Engulfing: current red candle engulfs previous green
        if prev_c > prev_o and c < o and o >= prev_c and c <= prev_o and body > prev_body:
            result.candle_patterns.engulfing_bearish = True

    def _calculate_pivot_points(self, df: pd.DataFrame, result: IndicatorResult) -> None:
        """Calculate Pivot Points, S1, S2, R1, R2 from previous day."""
        # Use previous day's data
        prev_high = float(df["high"].iloc[-2])
        prev_low = float(df["low"].iloc[-2])
        prev_close = float(df["close"].iloc[-2])

        pivot = (prev_high + prev_low + prev_close) / 3
        r1 = (2 * pivot) - prev_low
        r2 = pivot + (prev_high - prev_low)
        s1 = (2 * pivot) - prev_high
        s2 = pivot - (prev_high - prev_low)

        result.pivot_levels = PivotLevels(
            pivot=round(pivot, 2),
            r1=round(r1, 2),
            r2=round(r2, 2),
            s1=round(s1, 2),
            s2=round(s2, 2),
        )
