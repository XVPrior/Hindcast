"""Incremental sync: pull only what's missing from the local store."""

from __future__ import annotations

from datetime import datetime, timezone

from rich.console import Console

from .fetcher import TIMEFRAME_MS, Fetcher
from .storage import Storage

console = Console()


def sync_market(
    storage: Storage,
    fetcher: Fetcher,
    symbol: str,
    timeframe: str,
    fallback_since: datetime,
) -> int:
    """Bring `symbol`/`timeframe` up to date in `storage`.

    Strategy:
    - If local has data, fetch from the next bar after the latest stored one.
    - If local is empty, fetch from `fallback_since`.

    Returns: number of rows newly written.
    """
    latest = storage.latest_timestamp(fetcher.exchange_name, symbol, timeframe)

    if latest is None:
        since = fallback_since
        console.print(
            f"[cyan]No local data for {symbol} {timeframe}, "
            f"starting from {fallback_since.isoformat()}[/cyan]"
        )
    else:
        # Start from the bar AFTER the latest stored one to avoid re-fetching it.
        since_ms = int(latest.timestamp() * 1000) + TIMEFRAME_MS[timeframe]
        since = datetime.fromtimestamp(since_ms / 1000, tz=timezone.utc)
        console.print(
            f"[cyan]Resuming {symbol} {timeframe} from {since.isoformat()}[/cyan]"
        )

    df = fetcher.fetch_range(symbol, timeframe, since=since)

    if df.empty:
        console.print(f"[green]{symbol} {timeframe} already up to date[/green]")
        return 0

    n = storage.upsert_ohlcv(df)
    console.print(f"[green]Wrote {n} bars for {symbol} {timeframe}[/green]")
    return n
