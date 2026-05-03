"""One-shot script: pull funding-rate history for the perps we care about.

Binance USD-M perpetual funding cadence is 8h, so two years is ~2200 events
per symbol — a couple of paginated requests.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console

load_dotenv()

from hindcast.data.fetcher import Fetcher  # noqa: E402
from hindcast.data.storage import Storage  # noqa: E402

console = Console()
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "data" / "hindcast.duckdb"

PERPS = [
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    "SOL/USDT:USDT",
    "BNB/USDT:USDT",
    "XRP/USDT:USDT",
    "DOGE/USDT:USDT",
    "ADA/USDT:USDT",
]
FALLBACK_SINCE = datetime(2023, 1, 1, tzinfo=timezone.utc)

BINANCE_FUTURES_OPTIONS = {
    # "linear" = USD-M perps; defaultType "future" is the v3 ccxt alias.
    "options": {"defaultType": "future", "fetchMarkets": ["linear"]},
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
        extra_config=BINANCE_FUTURES_OPTIONS,
    )

    total = 0
    for symbol in PERPS:
        latest = storage.latest_funding_timestamp("binance", symbol)
        if latest is None:
            since = FALLBACK_SINCE
            console.print(f"[cyan]No local funding for {symbol}, starting from {since.isoformat()}[/cyan]")
        else:
            # +1ms past the latest stored event — same trick fetch_funding_range
            # uses internally for chunk pagination.
            import pandas as pd
            since = (latest + pd.Timedelta(milliseconds=1)).to_pydatetime()
            console.print(f"[cyan]Resuming {symbol} from {since.isoformat()}[/cyan]")

        df = fetcher.fetch_funding_range(symbol, since=since)
        if df.empty:
            console.print(f"[green]{symbol} already up to date[/green]")
            continue
        n = storage.upsert_funding_rate(df)
        total += n
        console.print(f"[green]Wrote {n} funding events for {symbol}[/green]")

    console.print(f"\n[bold]Total written: {total}[/bold]")
    for symbol in PERPS:
        df = storage.query_funding_rate("binance", symbol)
        latest = storage.latest_funding_timestamp("binance", symbol)
        console.print(f"  {symbol}: {len(df)} events, latest = {latest}")


if __name__ == "__main__":
    main()
