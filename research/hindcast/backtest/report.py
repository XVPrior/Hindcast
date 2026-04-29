"""Render a BacktestResult: console summary + equity/drawdown plot."""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # non-interactive backend, safe in CLI context
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402,F401  (used in type hint string)

from rich.console import Console  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.table import Table  # noqa: E402

from .engine import BacktestResult  # noqa: E402

console = Console()


def render_console(
    result: BacktestResult,
    *,
    strategy_label: str,
    symbol: str,
    timeframe: str,
    initial_cash: float,
) -> None:
    curve = result.equity_curve
    final = float(curve["equity"].iloc[-1])
    period_start = curve["timestamp"].iloc[0]
    period_end = curve["timestamp"].iloc[-1]
    n_bars = len(curve)

    panel_lines = [
        f"[bold]Strategy[/bold]    {strategy_label}",
        f"[bold]Symbol[/bold]      {symbol} {timeframe}",
        f"[bold]Period[/bold]      {period_start.date()} → {period_end.date()} "
        f"([dim]{n_bars} bars[/dim])",
        f"[bold]Initial[/bold]     ${initial_cash:,.2f}",
        f"[bold]Final[/bold]       ${final:,.2f}",
    ]
    console.print(Panel("\n".join(panel_lines), title="Backtest Result", expand=False))

    m = result.metrics
    if m is None:
        console.print("[yellow]No metrics computed (single-bar run?)[/yellow]")
        return

    table = Table(title="Metrics", show_header=False, expand=False)
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Total Return", f"{m.total_return:+.2%}")
    table.add_row("Annualized", f"{m.annualized_return:+.2%}")
    table.add_row("Max Drawdown", f"{m.max_drawdown:.2%}")
    table.add_row("Sharpe Ratio", f"{m.sharpe_ratio:.2f}")
    table.add_row(
        "Win Rate",
        f"{m.win_rate:.2%}" if m.n_trades > 0 else "[dim]n/a[/dim]",
    )
    table.add_row(
        "Profit Factor",
        ("∞" if math.isinf(m.profit_factor) else f"{m.profit_factor:.2f}")
        if m.n_trades > 0 else "[dim]n/a[/dim]",
    )
    table.add_row("# Trades", str(m.n_trades))
    console.print(table)


def save_equity_plot(
    result: BacktestResult,
    path: Path,
    *,
    strategy_label: str,
    symbol: str,
    timeframe: str,
    spot_prices: "pd.Series | None" = None,
) -> None:
    """Two-panel chart: equity curve on top, drawdown on the bottom.

    If `spot_prices` is supplied (a pd.Series indexed by timestamp), it is
    overlaid on a secondary y-axis of the equity panel for context.
    """
    curve = result.equity_curve
    if curve.empty:
        return

    path.parent.mkdir(parents=True, exist_ok=True)

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(12, 7), sharex=True,
        gridspec_kw={"height_ratios": [3, 1]},
    )

    ax1.plot(
        curve["timestamp"], curve["equity"],
        color="#3a6ea5", linewidth=1.4, label="equity",
    )
    ax1.set_ylabel("Equity ($)", color="#3a6ea5")
    ax1.grid(alpha=0.3)
    ax1.set_title(f"{strategy_label} — {symbol} {timeframe}")

    if spot_prices is not None and len(spot_prices) > 0:
        ax1b = ax1.twinx()
        ax1b.plot(
            spot_prices.index, spot_prices.values,
            color="#d18b3f", alpha=0.55, linewidth=1.0, label="spot",
        )
        ax1b.set_ylabel("Spot ($)", color="#d18b3f")

    peaks = curve["equity"].cummax()
    dd_pct = (curve["equity"] - peaks) / peaks * 100.0
    ax2.fill_between(curve["timestamp"], dd_pct, 0, color="#c0504d", alpha=0.45)
    ax2.set_ylabel("Drawdown (%)")
    ax2.set_xlabel("Date")
    ax2.grid(alpha=0.3)

    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
