"""Composite endpoint for the home/overview page.

Bundles health + per-market snapshot + live session summary into one
response so the dashboard's home view is a single fetch.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from hindcast import __version__
from hindcast.api.models import (
    HealthResponse,
    OverviewResponse,
)
from hindcast.api.routes.markets import enrich_market
from hindcast.api.routes.runs import _summarize
from hindcast.config import settings
from hindcast.data.markets import load_markets
from hindcast.data.storage import Storage

router = APIRouter(tags=["overview"])

_MARKETS_TOML = Path(__file__).resolve().parents[2] / "markets.toml"


def _storage() -> Storage:
    # Same rationale as routes/markets.py — in-process worker requires
    # matching connection mode, retry handles cross-process contention.
    return Storage(settings.db_path)


@router.get("/overview", response_model=OverviewResponse)
def overview() -> OverviewResponse:
    storage = _storage()
    market_overviews = [
        enrich_market(spec, storage) for spec in load_markets(_MARKETS_TOML)
    ]

    runs_df = storage.list_live_runs()
    total = len(runs_df)
    active = int(runs_df["ended_at"].isna().sum()) if total else 0
    recent_summaries = []
    recent_equity: dict[str, list[float]] = {}
    if total:
        for _, row in runs_df.head(5).iterrows():
            summary = _summarize(row, storage)
            recent_summaries.append(summary)
            eq_df = storage.query_live_equity(summary.run_id)
            if not eq_df.empty:
                recent_equity[summary.run_id] = (
                    eq_df.tail(60)["equity"].astype(float).tolist()
                )

    return OverviewResponse(
        health=HealthResponse(status="ok", version=__version__),
        markets=market_overviews,
        live_total=total,
        live_active=active,
        live_recent=recent_summaries,
        live_recent_equity=recent_equity,
    )
