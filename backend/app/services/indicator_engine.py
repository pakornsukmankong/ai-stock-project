import pandas as pd
import ta
from typing import Optional
from dataclasses import dataclass


@dataclass
class IndicatorResult:
    """Holds calculated technical indicator values."""

    rsi: float
    macd_value: float
    macd_signal: float
    macd_histogram: float
    ema_200: float
    current_price: float
    avg_volume: float
    current_volume: float
    support_level: float
    resistance_level: float


class IndicatorEngine:
    """Calculates technical indicators from OHLCV data."""

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
            # RSI (14 periods)
            rsi_indicator = ta.momentum.RSIIndicator(close=df["close"], window=14)
            rsi = rsi_indicator.rsi().iloc[-1]

            # MACD (12, 26, 9)
            macd_indicator = ta.trend.MACD(
                close=df["close"], window_slow=26, window_fast=12, window_sign=9
            )
            macd_value = macd_indicator.macd().iloc[-1]
            macd_signal = macd_indicator.macd_signal().iloc[-1]
            macd_histogram = macd_indicator.macd_diff().iloc[-1]

            # EMA 200
            ema_indicator = ta.trend.EMAIndicator(close=df["close"], window=200)
            ema_200 = ema_indicator.ema_indicator().iloc[-1]

            # Current price
            current_price = df["close"].iloc[-1]

            # Volume analysis
            avg_volume = df["volume"].rolling(window=20).mean().iloc[-1]
            current_volume = df["volume"].iloc[-1]

            # Support and Resistance
            support_level = self._calculate_support(df)
            resistance_level = self._calculate_resistance(df)

            return IndicatorResult(
                rsi=rsi,
                macd_value=macd_value,
                macd_signal=macd_signal,
                macd_histogram=macd_histogram,
                ema_200=ema_200,
                current_price=current_price,
                avg_volume=avg_volume,
                current_volume=current_volume,
                support_level=support_level,
                resistance_level=resistance_level,
            )

        except Exception as e:
            print(f"Error calculating indicators: {e}")
            return None

    def _calculate_support(self, df: pd.DataFrame) -> float:
        """Calculate support level using recent lows."""
        recent_lows = df["low"].tail(20)
        return recent_lows.min()

    def _calculate_resistance(self, df: pd.DataFrame) -> float:
        """Calculate resistance level using recent highs."""
        recent_highs = df["high"].tail(20)
        return recent_highs.max()
