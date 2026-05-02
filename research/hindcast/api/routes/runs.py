"""Audit-log endpoints for live trading sessions."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from hindcast.api.models import (
    LiveEquityPoint,
    LiveEquityResponse,
    LiveFill,
    LiveOrder,
    RunSummary,
)
from hindcast.config import settings
from hindcast.data.storage import Storage

router = APIRouter(prefix="/runs", tags=["runs"])


def _storage() -> Storage:
    return Storage(settings.db_path)


def _summarize(row, storage: Storage) -> RunSummary:
    run_id = row["run_id"]
    n_orders = len(storage.query_live_orders(run_id))
    n_fills = len(storage.query_live_fills(run_id))
    n_equity = len(storage.query_live_equity(run_id))
    ended_at = row.get("ended_at") if isinstance(row, dict) else row["ended_at"]
    return RunSummary(
        run_id=run_id,
        started_at=row["started_at"],
        ended_at=None if pd_isna(ended_at) else ended_at,
        strategy=row["strategy"],
        symbol=row["symbol"],
        timeframe=row["timeframe"],
        dry_run=bool(row["dry_run"]),
        params=row.get("params") if isinstance(row, dict) else row["params"],
        n_orders=n_orders,
        n_fills=n_fills,
        n_equity_points=n_equity,
        active=pd_isna(ended_at),
    )


def pd_isna(v) -> bool:
    """pandas NaT / None / NaN → True."""
    import pandas as pd
    return v is None or (isinstance(v, float) and v != v) or pd.isna(v)


@router.get("", response_model=list[RunSummary])
def list_runs(limit: int = 50) -> list[RunSummary]:
    storage = _storage()
    df = storage.list_live_runs()
    if df.empty:
        return []
    df = df.head(limit)
    out: list[RunSummary] = []
    for _, row in df.iterrows():
        out.append(_summarize(row, storage))
    return out


@router.get("/{run_id}", response_model=RunSummary)
def get_run(run_id: str) -> RunSummary:
    storage = _storage()
    df = storage.list_live_runs()
    matched = df[df["run_id"] == run_id] if not df.empty else df
    if matched.empty:
        raise HTTPException(404, f"run {run_id} not found")
    return _summarize(matched.iloc[0], storage)


@router.get("/{run_id}/orders", response_model=list[LiveOrder])
def get_orders(run_id: str) -> list[LiveOrder]:
    df = _storage().query_live_orders(run_id)
    if df.empty:
        return []
    return [
        LiveOrder(
            order_id=int(row.order_id),
            run_id=row.run_id,
            intent_ts=row.intent_ts,
            submit_ts=row.submit_ts,
            side=row.side,
            quantity=float(row.quantity),
            status=row.status,
            exchange_id=None if pd_isna(row.exchange_id) else str(row.exchange_id),
            error_message=None if pd_isna(row.error_message) else str(row.error_message),
        )
        for row in df.itertuples()
    ]


@router.get("/{run_id}/fills", response_model=list[LiveFill])
def get_fills(run_id: str) -> list[LiveFill]:
    df = _storage().query_live_fills(run_id)
    if df.empty:
        return []
    return [
        LiveFill(
            run_id=row.run_id,
            order_id=int(row.order_id),
            fill_ts=row.fill_ts,
            side=row.side,
            quantity=float(row.quantity),
            price=float(row.price),
            fee=float(row.fee),
            fee_currency=None if pd_isna(row.fee_currency) else str(row.fee_currency),
        )
        for row in df.itertuples()
    ]


@router.get("/{run_id}/equity", response_model=LiveEquityResponse)
def get_equity(run_id: str) -> LiveEquityResponse:
    df = _storage().query_live_equity(run_id)
    points = [
        LiveEquityPoint(
            timestamp=row.timestamp,
            cash=float(row.cash),
            position=float(row.position),
            price=float(row.price),
            equity=float(row.equity),
        )
        for row in df.itertuples()
    ]
    return LiveEquityResponse(run_id=run_id, count=len(points), points=points)
