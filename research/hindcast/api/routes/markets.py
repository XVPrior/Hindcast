"""Read-only access to the local data store: configured markets + OHLCV."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from hindcast.api.models import Bar, BarsResponse, MarketResponse
from hindcast.config import settings
from hindcast.data.markets import load_markets
from hindcast.data.storage import Storage

router = APIRouter(prefix="/markets", tags=["markets"])

# markets.toml ships inside the package — same path the CLI uses.
_MARKETS_TOML = Path(__file__).resolve().parents[2] / "markets.toml"


def _storage() -> Storage:
    return Storage(settings.db_path, read_only=True)


@router.get("", response_model=list[MarketResponse])
def list_markets() -> list[MarketResponse]:
    """List configured markets with bar counts per timeframe."""
    storage = _storage()
    out: list[MarketResponse] = []
    for m in load_markets(_MARKETS_TOML):
        bars_per_tf = {
            tf: storage.row_count(exchange=m.exchange, symbol=m.symbol, timeframe=tf)
            for tf in m.timeframes
        }
        out.append(MarketResponse(
            exchange=m.exchange,
            symbol=m.symbol,
            timeframes=m.timeframes,
            fallback_since=m.fallback_since,
            bars_per_timeframe=bars_per_tf,
        ))
    return out


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
