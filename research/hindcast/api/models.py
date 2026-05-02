"""Pydantic response schemas shared across API routes."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    version: str


class MarketResponse(BaseModel):
    exchange: str
    symbol: str
    timeframes: list[str]
    fallback_since: datetime
    bars_per_timeframe: dict[str, int] = Field(
        default_factory=dict,
        description="How many bars are stored locally for each timeframe.",
    )


class Bar(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class BarsResponse(BaseModel):
    exchange: str
    symbol: str
    timeframe: str
    count: int
    bars: list[Bar]
