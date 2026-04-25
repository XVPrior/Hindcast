"""One-shot script: pull BTC/USDT history for a few timeframes.

Run me twice — first run downloads, second run should be a no-op.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console

load_dotenv()  # must precede ccxt-touching imports

from hindcast.data.fetcher import Fetcher  # noqa: E402
from hindcast.data.storage import Storage  # noqa: E402
from hindcast.data.sync import sync_market  # noqa: E402

console = Console()

# Resolve to project root so cwd doesn't matter (avoids dropping the DB
# under research/data/ when invoked from research/).
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "data" / "hindcast.duckdb"

SYMBOL = "BTC/USDT"
TIMEFRAMES = ["1d", "1h"]
FALLBACK_SINCE = datetime(2023, 1, 1, tzinfo=timezone.utc)

# Spot-only on purpose — see scripts/smoke_ccxt.py for why fetching all
# market types trips Binance's rate-limit ban on shared proxy egress IPs.
BINANCE_OPTIONS = {
    "options": {"defaultType": "spot", "fetchMarkets": ["spot"]},
}


def main() -> None:
    proxy = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
    if proxy:
        console.print(f"[dim]Using proxy: {proxy}[/dim]")
    console.print(f"[dim]DB: {DB_PATH}[/dim]")

    storage = Storage(DB_PATH)
    fetcher = Fetcher(
        exchange_name="binance",
        proxy=proxy,
        extra_config=BINANCE_OPTIONS,
    )

    total_written = 0
    for tf in TIMEFRAMES:
        console.rule(f"[bold]Syncing {SYMBOL} {tf}")
        total_written += sync_market(
            storage=storage,
            fetcher=fetcher,
            symbol=SYMBOL,
            timeframe=tf,
            fallback_since=FALLBACK_SINCE,
        )

    console.rule("[bold green]Summary")
    console.print(f"Newly written rows: {total_written}")
    for tf in TIMEFRAMES:
        n = storage.row_count(exchange="binance", symbol=SYMBOL, timeframe=tf)
        latest = storage.latest_timestamp("binance", SYMBOL, tf)
        console.print(f"  {tf}: {n} bars, latest = {latest}")


if __name__ == "__main__":
    main()
