"""Read-only access to the local data store: configured markets + OHLCV."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from hindcast.api.models import Bar, BarsResponse, MarketOverview
from hindcast.config import settings
from hindcast.data.markets import MarketSpec, load_markets
from hindcast.data.storage import Storage

router = APIRouter(prefix="/markets", tags=["markets"])

# markets.toml ships inside the package — same path the CLI uses.
_MARKETS_TOML = Path(__file__).resolve().parents[2] / "markets.toml"


def _storage() -> Storage:
    return Storage(settings.db_path, read_only=True)


def enrich_market(spec: MarketSpec, storage: Storage) -> MarketOverview:
    """Build a full MarketOverview for one market spec.

    Shared by /api/markets and /api/overview so both endpoints return the
    same per-market shape from the same source of truth.
    """
    df_1d = storage.query_ohlcv(spec.exchange, spec.symbol, "1d")
    latest_close = None
    latest_ts = None
    change_24h = None
    if not df_1d.empty:
        last = df_1d.iloc[-1]
        latest_close = float(last["close"])
        latest_ts = last["timestamp"]
        if len(df_1d) >= 2:
            prev = df_1d.iloc[-2]
            if float(prev["close"]) > 0:
                change_24h = (float(last["close"]) / float(prev["close"]) - 1) * 100

    bars_per_tf = {
        tf: storage.row_count(exchange=spec.exchange, symbol=spec.symbol, timeframe=tf)
        for tf in spec.timeframes
    }

    perp_symbol = f"{spec.symbol}:USDT"
    df_f = storage.query_funding_rate(spec.exchange, perp_symbol)
    funding_rate = None
    funding_annual = None
    funding_ts = None
    funding_history: list[float] = []
    if not df_f.empty:
        last_f = df_f.iloc[-1]
        funding_rate = float(last_f["rate"])
        funding_annual = funding_rate * 1095 * 100  # 3/day × 365 × pct
        funding_ts = last_f["timestamp"]
        funding_history = df_f.tail(21)["rate"].astype(float).tolist()

    return MarketOverview(
        exchange=spec.exchange,
        symbol=spec.symbol,
        latest_close=latest_close,
        latest_close_ts=latest_ts,
        change_24h_pct=change_24h,
        total_bars=bars_per_tf,
        funding_rate=funding_rate,
        funding_annualized_pct=funding_annual,
        funding_ts=funding_ts,
        funding_history=funding_history,
    )


@router.get("", response_model=list[MarketOverview])
def list_markets() -> list[MarketOverview]:
    """List configured markets with bar counts + latest price/change/funding."""
    storage = _storage()
    return [enrich_market(spec, storage) for spec in load_markets(_MARKETS_TOML)]


@router.get("/bars", response_model=BarsResponse)
def get_bars(
    exchange: str = Query("binance"),
    symbol: str = Query(..., description="e.g. BTC/USDT"),
    timeframe: str = Query("1d"),
    start: datetime | None = Query(None, description="ISO 8601, UTC"),
    end: datetime | None = Query(None, description="ISO 8601, UTC"),
    limit: int = Query(2000, ge=1, le=10_000),
) -> BarsResponse:
    """Return stored OHLCV bars for one (exchange, symbol, timeframe)."""
    storage = _storage()
    df = storage.query_ohlcv(
        exchange=exchange,
        symbol=symbol,
        timeframe=timeframe,
        start=pd.Timestamp(start, tz="UTC") if start else None,
        end=pd.Timestamp(end, tz="UTC") if end else None,
    )
    if df.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No data for {exchange} {symbol} {timeframe} in the requested range",
        )

    if len(df) > limit:
        df = df.tail(limit)

    bars = [
        Bar(
            timestamp=row.timestamp,
            open=row.open, high=row.high, low=row.low,
            close=row.close, volume=row.volume,
        )
        for row in df.itertuples()
    ]
    return BarsResponse(
        exchange=exchange,
        symbol=symbol,
        timeframe=timeframe,
        count=len(bars),
        bars=bars,
    )
