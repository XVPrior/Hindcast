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
    MarketOverview,
    OverviewResponse,
)
from hindcast.api.routes.runs import _summarize
from hindcast.config import settings
from hindcast.data.markets import load_markets
from hindcast.data.storage import Storage

router = APIRouter(tags=["overview"])

_MARKETS_TOML = Path(__file__).resolve().parents[2] / "markets.toml"


def _storage() -> Storage:
    return Storage(settings.db_path, read_only=True)


@router.get("/overview", response_model=OverviewResponse)
def overview() -> OverviewResponse:
    storage = _storage()
    markets_list = load_markets(_MARKETS_TOML)

    market_overviews: list[MarketOverview] = []
    for m in markets_list:
        df_1d = storage.query_ohlcv(m.exchange, m.symbol, "1d")
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
                    change_24h = (
                        float(last["close"]) / float(prev["close"]) - 1
                    ) * 100

        bars_per_tf = {
            tf: storage.row_count(exchange=m.exchange, symbol=m.symbol, timeframe=tf)
            for tf in m.timeframes
        }

        # Funding rate from the perpetual contract — same base symbol with
        # the unified-CCXT perp suffix. May be missing if M3-E4 sync wasn't run.
        perp_symbol = f"{m.symbol}:USDT"
        df_f = storage.query_funding_rate(m.exchange, perp_symbol)
        funding_rate = None
        funding_annual = None
        funding_ts = None
        funding_history: list[float] = []
        if not df_f.empty:
            last_f = df_f.iloc[-1]
            funding_rate = float(last_f["rate"])
            funding_annual = funding_rate * 1095 * 100  # 3/day × 365 × pct
            funding_ts = last_f["timestamp"]
            # Last 21 events = ~7 days of 8h funding intervals.
            funding_history = df_f.tail(21)["rate"].astype(float).tolist()

        market_overviews.append(MarketOverview(
            exchange=m.exchange,
            symbol=m.symbol,
            latest_close=latest_close,
            latest_close_ts=latest_ts,
            change_24h_pct=change_24h,
            total_bars=bars_per_tf,
            funding_rate=funding_rate,
            funding_annualized_pct=funding_annual,
            funding_ts=funding_ts,
            funding_history=funding_history,
        ))

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
