from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class StockSignalSummary(BaseModel):
    """Compact summary sent to AI with all indicator data."""
    symbol: str
    price: float
    score: int = 0

    # Trend
    ema_9: float = 0.0
    ema_21: float = 0.0
    ema_50: float = 0.0
    ema_200: float = 0.0
    macd_value: float = 0.0
    macd_signal: float = 0.0
    macd_histogram: float = 0.0
    supertrend_direction: str = "neutral"
    supertrend_value: float = 0.0

    # Momentum
    rsi: float = 50.0
    rsi_state: str = "neutral"
    stoch_k: float = 50.0
    stoch_d: float = 50.0

    # Volatility
    atr: float = 0.0
    bb_upper: float = 0.0
    bb_middle: float = 0.0
    bb_lower: float = 0.0
    bb_position: str = "middle"

    # Volume
    volume_ratio: float = 1.0

    # Market Structure
    pivot: float = 0.0
    r1: float = 0.0
    r2: float = 0.0
    s1: float = 0.0
    s2: float = 0.0

    # Patterns
    candle_patterns: list[str] = []

    # Signal engine reasons
    signal_reasons: list[str] = []

    # Multi-Timeframe Analysis
    mtf_trend_alignment: str = "not_available"  # strong_bullish, bullish, neutral, bearish, conflicting
    mtf_4h_trend: str = "n/a"  # bullish, bearish, neutral
    mtf_1h_trend: str = "n/a"  # bullish, bearish, neutral
    mtf_4h_rsi: float = 0.0
    mtf_1h_rsi: float = 0.0
    mtf_bonus: int = 0
    mtf_penalty: int = 0


class AIAnalysisResult(BaseModel):
    symbol: str
    action: str  # "BUY", "SELL", "HOLD"
    summary: str
    confidence: str
    reasons: list[str]
    analyzed_at: datetime


class AlertResponse(BaseModel):
    id: str
    user_id: str
    stock_symbol: str
    signal_type: str
    ai_summary: str
    sent_at: datetime


class WatchlistStockRequest(BaseModel):
    symbol: str
    is_enabled: bool = True


class WatchlistStockResponse(BaseModel):
    id: str
    symbol: str
    is_enabled: bool
    created_at: datetime


class AnalysisCacheEntry(BaseModel):
    symbol: str
    ai_summary: str
    confidence: str
    reasons: list[str]
    cached_at: datetime
    expires_at: datetime
    is_expired: bool = False
