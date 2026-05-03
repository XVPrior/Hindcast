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


# ----- live trading audit log -----


class RunSummary(BaseModel):
    run_id: str
    started_at: datetime
    ended_at: datetime | None
    strategy: str
    symbol: str
    timeframe: str
    dry_run: bool
    params: str | None
    n_orders: int
    n_fills: int
    n_equity_points: int
    active: bool  # convenience: ended_at IS NULL
    stop_requested: bool = False
    crashed_at: datetime | None = None


class LiveOrder(BaseModel):
    order_id: int
    run_id: str
    intent_ts: datetime
    submit_ts: datetime
    side: str
    quantity: float
    status: str
    exchange_id: str | None
    error_message: str | None


class LiveFill(BaseModel):
    run_id: str
    order_id: int
    fill_ts: datetime
    side: str
    quantity: float
    price: float
    fee: float
    fee_currency: str | None


class LiveEquityPoint(BaseModel):
    timestamp: datetime
    cash: float
    position: float
    price: float
    equity: float


class LiveEquityResponse(BaseModel):
    run_id: str
    count: int
    points: list[LiveEquityPoint]


# ----- overview (composite for home page) -----


class MarketOverview(BaseModel):
    exchange: str
    symbol: str
    latest_close: float | None
    latest_close_ts: datetime | None
    change_24h_pct: float | None
    total_bars: dict[str, int]
    funding_rate: float | None
    funding_annualized_pct: float | None
    funding_ts: datetime | None
    funding_history: list[float] = Field(
        default_factory=list,
        description="Last ~21 funding rates (oldest first), ~7 days for 8h cadence.",
    )


class OverviewResponse(BaseModel):
    health: HealthResponse
    markets: list[MarketOverview]
    live_total: int
    live_active: int
    live_recent: list[RunSummary]
    live_recent_equity: dict[str, list[float]] = Field(
        default_factory=dict,
        description="run_id → last ~60 equity values (oldest first).",
    )
