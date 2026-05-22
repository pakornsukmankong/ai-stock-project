from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class StockSignalSummary(BaseModel):
    symbol: str
    price: float
    rsi: float
    macd: str
    trend: str
    support: str
    volume: str
    score: int = 0


class AIAnalysisResult(BaseModel):
    symbol: str
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
