"""Hindcast command-line interface.

Usage:
    uv run hindcast sync                    # sync all markets in markets.toml
    uv run hindcast sync --symbol BTC/USDT
    uv run hindcast status                  # show what's in the local store
    uv run hindcast markets                 # list configured markets
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from hindcast.config import settings
from hindcast.data.fetcher import Fetcher
from hindcast.data.markets import MarketSpec, load_markets
from hindcast.data.storage import Storage
from hindcast.data.sync import sync_market

app = typer.Typer(
    add_completion=False,
    help="Hindcast — crypto quant research toolkit.",
)
console = Console()

DEFAULT_MARKETS_PATH = Path(__file__).parent / "markets.toml"

# Per-exchange ccxt config. Binance: spot-only avoids the multi-market-type
# load_markets fan-out that trips the 418 ban on shared proxy egress IPs.
EXCHANGE_DEFAULTS: dict[str, dict] = {
    "binance": {"options": {"defaultType": "spot", "fetchMarkets": ["spot"]}},
}


def _load_markets(path: Path) -> list[MarketSpec]:
    if not path.exists():
        console.print(f"[red]Markets config not found: {path}[/red]")
        raise typer.Exit(code=1)
    return load_markets(path)


def _filter(
    markets: list[MarketSpec],
    symbol: str | None,
    exchange: str | None,
) -> list[MarketSpec]:
    out = markets
    if symbol:
        out = [m for m in out if m.symbol == symbol]
    if exchange:
        out = [m for m in out if m.exchange == exchange]
    return out


@app.command()
def sync(
    symbol: str | None = typer.Option(None, help="Sync only this symbol."),
    exchange: str | None = typer.Option(None, help="Sync only this exchange."),
    markets_file: Path = typer.Option(
        DEFAULT_MARKETS_PATH, "--markets", help="Path to markets.toml"
    ),
) -> None:
    """Pull missing OHLCV data into the local store."""
    markets = _filter(_load_markets(markets_file), symbol, exchange)
    if not markets:
        console.print("[yellow]No markets matched. Nothing to do.[/yellow]")
        raise typer.Exit()

    if settings.proxy:
        console.print(f"[dim]Using proxy: {settings.proxy}[/dim]")
    console.print(f"[dim]DB: {settings.db_path}[/dim]")

    storage = Storage(settings.db_path)
    fetchers: dict[str, Fetcher] = {}

    total_written = 0
    for market in markets:
        if market.exchange not in fetchers:
            fetchers[market.exchange] = Fetcher(
                exchange_name=market.exchange,
                proxy=settings.proxy,
                extra_config=EXCHANGE_DEFAULTS.get(market.exchange),
            )
        fetcher = fetchers[market.exchange]

        for tf in market.timeframes:
            console.rule(f"[bold]{market.exchange} {market.symbol} {tf}")
            total_written += sync_market(
                storage=storage,
                fetcher=fetcher,
                symbol=market.symbol,
                timeframe=tf,
                fallback_since=market.fallback_since,
            )

    console.rule("[bold green]Sync complete")
    console.print(f"Total rows written: {total_written}")


@app.command()
def status(
    markets_file: Path = typer.Option(
        DEFAULT_MARKETS_PATH, "--markets", help="Path to markets.toml"
    ),
) -> None:
    """Show what's in the local store."""
    markets = _load_markets(markets_file)
    storage = Storage(settings.db_path)

    table = Table(title=f"Hindcast store: {settings.db_path}")
    table.add_column("Exchange")
    table.add_column("Symbol")
    table.add_column("Timeframe")
    table.add_column("Bars", justify="right")
    table.add_column("Latest (UTC)")

    for m in markets:
        for tf in m.timeframes:
            n = storage.row_count(exchange=m.exchange, symbol=m.symbol, timeframe=tf)
            latest = storage.latest_timestamp(m.exchange, m.symbol, tf)
            latest_str = (
                latest.tz_convert("UTC").strftime("%Y-%m-%d %H:%M")
                if latest is not None
                else "—"
            )
            table.add_row(m.exchange, m.symbol, tf, f"{n:,}", latest_str)

    console.print(table)


@app.command()
def markets(
    markets_file: Path = typer.Option(
        DEFAULT_MARKETS_PATH, "--markets", help="Path to markets.toml"
    ),
) -> None:
    """List configured markets."""
    ms = _load_markets(markets_file)

    table = Table(title="Configured markets")
    table.add_column("Exchange")
    table.add_column("Symbol")
    table.add_column("Timeframes")
    table.add_column("Fallback since")
    for m in ms:
        table.add_row(
            m.exchange,
            m.symbol,
            ", ".join(m.timeframes),
            m.fallback_since.date().isoformat(),
        )
    console.print(table)


if __name__ == "__main__":
    app()
