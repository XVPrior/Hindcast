"""Hindcast command-line interface.

Usage:
    uv run hindcast sync                    # sync all markets in markets.toml
    uv run hindcast sync --symbol BTC/USDT
    uv run hindcast status                  # show what's in the local store
    uv run hindcast markets                 # list configured markets
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import typer
from rich.console import Console
from rich.table import Table

from hindcast.backtest.engine import BacktestEngine
from hindcast.backtest.execution import SimpleExecutionModel
from hindcast.backtest.portfolio import Portfolio
from hindcast.backtest.report import render_console, save_equity_plot
from hindcast.backtest.strategies.buy_and_hold import BuyAndHold
from hindcast.backtest.strategies.ma_crossover import MACrossover
from hindcast.backtest.types import Bar
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


@app.command()
def backtest(
    strategy: str = typer.Option(
        "buy_and_hold", "--strategy", "-s",
        help="Strategy name: buy_and_hold or ma_crossover",
    ),
    symbol: str = typer.Option("BTC/USDT", "--symbol"),
    timeframe: str = typer.Option("1d", "--timeframe"),
    start: str | None = typer.Option(None, "--start", help="ISO date, e.g. 2024-01-01"),
    end: str | None = typer.Option(None, "--end", help="ISO date, e.g. 2026-01-01"),
    initial_cash: float = typer.Option(10_000.0, "--initial-cash"),
    fee_pct: float = typer.Option(0.001, "--fee-pct"),
    slippage_pct: float = typer.Option(0.0005, "--slippage-pct"),
    allocation_pct: float = typer.Option(0.99, "--allocation-pct"),
    fast_period: int = typer.Option(10, "--fast-period", help="ma_crossover only"),
    slow_period: int = typer.Option(30, "--slow-period", help="ma_crossover only"),
    save_plot: bool = typer.Option(True, "--save-plot/--no-save-plot"),
) -> None:
    """Run a backtest against locally stored OHLCV data."""
    # ----- build strategy -----
    if strategy == "buy_and_hold":
        strat = BuyAndHold(allocation_pct=allocation_pct)
        label = f"buy_and_hold (alloc={allocation_pct:.0%})"
    elif strategy == "ma_crossover":
        strat = MACrossover(
            fast_window=fast_period,
            slow_window=slow_period,
            allocation_pct=allocation_pct,
        )
        label = f"ma_crossover ({fast_period}/{slow_period})"
    else:
        raise typer.BadParameter(
            f"Unknown strategy '{strategy}'. Choose buy_and_hold or ma_crossover."
        )

    # ----- load bars -----
    storage = Storage(settings.db_path)
    start_ts = pd.Timestamp(start, tz="UTC") if start else None
    end_ts = pd.Timestamp(end, tz="UTC") if end else None
    df = storage.query_ohlcv(
        "binance", symbol, timeframe, start=start_ts, end=end_ts,
    )
    if df.empty:
        console.print(
            f"[red]No data for {symbol} {timeframe} in the requested range. "
            f"Run `hindcast sync` first?[/red]"
        )
        raise typer.Exit(code=1)
    bars = [Bar.from_series(row) for _, row in df.iterrows()]

    # ----- run -----
    engine = BacktestEngine(
        strategy=strat,
        execution_model=SimpleExecutionModel(
            fee_pct=fee_pct, slippage_pct=slippage_pct,
        ),
        portfolio=Portfolio(initial_cash=initial_cash),
    )
    result = engine.run(bars)

    # ----- report -----
    render_console(
        result,
        strategy_label=label,
        symbol=symbol,
        timeframe=timeframe,
        initial_cash=initial_cash,
    )

    if save_plot:
        runs_dir = settings.db_path.parent / "backtest_runs"
        ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H%M%S")
        symbol_safe = symbol.replace("/", "")
        plot_path = runs_dir / f"{ts}_{strategy}_{symbol_safe}_{timeframe}.png"
        save_equity_plot(
            result, plot_path,
            strategy_label=label, symbol=symbol, timeframe=timeframe,
        )
        console.print(f"\n[dim]Equity plot:[/dim] {plot_path}")


if __name__ == "__main__":
    app()
