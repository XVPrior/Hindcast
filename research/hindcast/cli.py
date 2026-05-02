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
from hindcast.backtest.strategies.bollinger_meanrev import BollingerMeanReversion
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
def live(
    strategy: str = typer.Option(
        "ma_crossover", "--strategy", "-s",
        help="Strategy name: buy_and_hold, ma_crossover, or bollinger_meanrev",
    ),
    symbol: str = typer.Option("BTC/USDT", "--symbol"),
    timeframe: str = typer.Option("1m", "--timeframe", help="1m / 5m / 1h / 1d"),
    fast_period: int = typer.Option(5, "--fast-period"),
    slow_period: int = typer.Option(20, "--slow-period"),
    window: int = typer.Option(20, "--window"),
    n_std: float = typer.Option(2.0, "--n-std"),
    allocation_pct: float = typer.Option(
        0.99, "--allocation-pct",
        help="Fraction of virtual cash to allocate per buy.",
    ),
    initial_cash: float = typer.Option(
        10_000.0, "--initial-cash",
        help="Virtual starting cash. Strategy starts flat (position=0) "
             "regardless of testnet balance.",
    ),
    fee_pct: float = typer.Option(
        0.001, "--fee-pct",
        help="Fee rate for dry-run fill simulation (default 0.10%, Binance taker).",
    ),
    slippage_pct: float = typer.Option(
        0.0005, "--slippage-pct",
        help="Slippage for dry-run fill simulation (default 0.05%).",
    ),
    live_mode: bool = typer.Option(
        False, "--live/--dry-run",
        help="Default dry-run. --live actually places orders on the testnet.",
    ),
) -> None:
    """Run a strategy live against the Binance spot testnet.

    The strategy operates against a *virtual* portfolio that starts at
    initial_cash + position=0, NOT the testnet account's actual balance.
    This matches backtest semantics so a strategy validated on history
    behaves the same way live.
    """
    from hindcast.backtest.strategies.bollinger_meanrev import BollingerMeanReversion
    from hindcast.backtest.strategies.buy_and_hold import BuyAndHold
    from hindcast.backtest.strategies.ma_crossover import MACrossover
    from hindcast.exec.binance_client import make_binance_testnet
    from hindcast.exec.live_engine import LiveEngine

    if strategy == "buy_and_hold":
        strat = BuyAndHold(allocation_pct=allocation_pct)
        label = f"buy_and_hold (alloc={allocation_pct:.0%})"
        params = {"allocation_pct": allocation_pct}
    elif strategy == "ma_crossover":
        strat = MACrossover(
            fast_window=fast_period, slow_window=slow_period,
            allocation_pct=allocation_pct,
        )
        label = f"ma_crossover ({fast_period}/{slow_period})"
        params = {"fast": fast_period, "slow": slow_period, "allocation_pct": allocation_pct}
    elif strategy == "bollinger_meanrev":
        strat = BollingerMeanReversion(
            window=window, n_std=n_std, allocation_pct=allocation_pct,
        )
        label = f"bollinger_meanrev (w={window}, n={n_std})"
        params = {"window": window, "n_std": n_std, "allocation_pct": allocation_pct}
    else:
        raise typer.BadParameter(f"Unknown strategy '{strategy}'.")

    storage = Storage(settings.db_path)
    client = make_binance_testnet()
    engine = LiveEngine(
        strategy=strat,
        client=client,
        symbol=symbol,
        timeframe=timeframe,
        storage=storage,
        strategy_label=label,
        params={**params, "initial_cash": initial_cash, "fee_pct": fee_pct, "slippage_pct": slippage_pct},
        dry_run=not live_mode,
        initial_cash=initial_cash,
        fee_pct=fee_pct,
        slippage_pct=slippage_pct,
    )
    engine.run()


@app.command(name="testnet-check")
def testnet_check(
    place_order: bool = typer.Option(
        False, "--place-order",
        help="Place a tiny BUY+SELL round-trip on the testnet to verify the write path.",
    ),
) -> None:
    """Verify Binance spot testnet credentials and connectivity."""
    import subprocess
    import sys

    args = [sys.executable, "scripts/testnet_check.py"]
    if place_order:
        args.append("--place-order")
    raise typer.Exit(subprocess.call(args))


@app.command()
def api(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
    reload: bool = typer.Option(False, "--reload/--no-reload"),
) -> None:
    """Start the FastAPI dashboard backend."""
    import uvicorn

    uvicorn.run(
        "hindcast.api.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


@app.command()
def backtest(
    strategy: str = typer.Option(
        "buy_and_hold", "--strategy", "-s",
        help="Strategy name: buy_and_hold, ma_crossover, or bollinger_meanrev",
    ),
    symbol: str = typer.Option("BTC/USDT", "--symbol"),
    timeframe: str = typer.Option("1d", "--timeframe"),
    start: str | None = typer.Option(None, "--start", help="ISO date, e.g. 2024-01-01"),
    end: str | None = typer.Option(None, "--end", help="ISO date, e.g. 2026-01-01"),
    initial_cash: float = typer.Option(10_000.0, "--initial-cash"),
    fee_pct: float = typer.Option(0.001, "--fee-pct"),
    slippage_pct: float = typer.Option(0.0005, "--slippage-pct"),
    no_fees: bool = typer.Option(False, "--no-fees", help="Force fee_pct to 0"),
    no_slippage: bool = typer.Option(False, "--no-slippage", help="Force slippage_pct to 0"),
    allocation_pct: float = typer.Option(0.99, "--allocation-pct"),
    fast_period: int = typer.Option(10, "--fast-period", help="ma_crossover only"),
    slow_period: int = typer.Option(30, "--slow-period", help="ma_crossover only"),
    window: int = typer.Option(20, "--window", help="bollinger_meanrev only"),
    n_std: float = typer.Option(2.0, "--n-std", help="bollinger_meanrev only"),
    save_plot: bool = typer.Option(True, "--save-plot/--no-save-plot"),
    spot_overlay: bool = typer.Option(
        False, "--spot-overlay/--no-spot-overlay",
        help="Overlay spot price on the equity panel.",
    ),
) -> None:
    """Run a backtest against locally stored OHLCV data."""
    if no_fees:
        fee_pct = 0.0
    if no_slippage:
        slippage_pct = 0.0

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
    elif strategy == "bollinger_meanrev":
        strat = BollingerMeanReversion(
            window=window,
            n_std=n_std,
            allocation_pct=allocation_pct,
        )
        label = f"bollinger_meanrev (w={window}, n={n_std})"
    else:
        raise typer.BadParameter(
            f"Unknown strategy '{strategy}'. "
            f"Choose buy_and_hold, ma_crossover, or bollinger_meanrev."
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
        spot_series = (
            pd.Series(df["close"].values, index=df["timestamp"].values)
            if spot_overlay else None
        )
        save_equity_plot(
            result, plot_path,
            strategy_label=label, symbol=symbol, timeframe=timeframe,
            spot_prices=spot_series,
        )
        console.print(f"\n[dim]Equity plot:[/dim] {plot_path}")


if __name__ == "__main__":
    app()
