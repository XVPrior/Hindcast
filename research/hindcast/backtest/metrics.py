"""Metrics: derive summary stats from an equity curve and fill log.

The 6 numbers most analysts look at first:
- total_return / annualized_return — the bottom line
- max_drawdown — worst peak-to-trough loss
- sharpe_ratio — risk-adjusted return (annualized, rf=0)
- win_rate / profit_factor — quality of trades

Trade pairing is FIFO: each sell consumes the oldest open buy lot. Adequate
for single-asset long-only strategies. M3 will revisit when shorts arrive.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd

from .types import Fill, Metrics


@dataclass(frozen=True, slots=True)
class Trade:
    """A round-trip: a buy lot fully matched against a sell."""

    entry_timestamp: datetime
    exit_timestamp: datetime
    quantity: float
    entry_price: float
    exit_price: float
    fees: float  # entry + exit fees attributed proportionally to this match
    pnl: float


@dataclass
class _OpenLot:
    """Mutable buy lot tracker, used internally by pair_fills_to_trades."""

    timestamp: datetime
    qty_remaining: float
    price: float
    fee_per_unit: float


def pair_fills_to_trades(fills: list[Fill]) -> list[Trade]:
    """FIFO pair buy fills with subsequent sells.

    Partial matches are supported: one buy lot can be split across multiple
    sells, and one sell can consume multiple buy lots.
    """
    open_lots: deque[_OpenLot] = deque()
    trades: list[Trade] = []

    for fill in fills:
        if fill.quantity <= 0:
            continue

        if fill.side == "buy":
            open_lots.append(_OpenLot(
                timestamp=fill.timestamp,
                qty_remaining=fill.quantity,
                price=fill.price,
                fee_per_unit=fill.fee / fill.quantity,
            ))
            continue

        # sell
        sell_qty_remaining = fill.quantity
        sell_fee_per_unit = fill.fee / fill.quantity
        while sell_qty_remaining > 1e-12 and open_lots:
            lot = open_lots[0]
            match_qty = min(lot.qty_remaining, sell_qty_remaining)
            fees = match_qty * (lot.fee_per_unit + sell_fee_per_unit)
            pnl = match_qty * (fill.price - lot.price) - fees

            trades.append(Trade(
                entry_timestamp=lot.timestamp,
                exit_timestamp=fill.timestamp,
                quantity=match_qty,
                entry_price=lot.price,
                exit_price=fill.price,
                fees=fees,
                pnl=pnl,
            ))

            lot.qty_remaining -= match_qty
            sell_qty_remaining -= match_qty
            if lot.qty_remaining <= 1e-12:
                open_lots.popleft()

    return trades


def compute_metrics(
    equity_curve: pd.DataFrame,
    fills: list[Fill],
    bar_seconds: int,
) -> Metrics:
    """Compute summary metrics. Tolerant of degenerate inputs.

    Conventions for undefined cases:
    - flat equity / single bar / no returns variance → sharpe = 0
    - zero duration → annualized_return = 0
    - no trades → win_rate = 0, profit_factor = 0
    - all-winning trades → profit_factor = inf
    """
    if equity_curve.empty:
        return Metrics(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0)

    equity = equity_curve["equity"].astype(float)
    initial = float(equity.iloc[0])
    final = float(equity.iloc[-1])
    total_return = (final / initial) - 1.0 if initial > 0 else 0.0

    # ----- annualized return -----
    duration_seconds = (
        equity_curve["timestamp"].iloc[-1] - equity_curve["timestamp"].iloc[0]
    ).total_seconds()
    if duration_seconds > 0 and (1 + total_return) > 0:
        years = duration_seconds / (365.25 * 86400)
        annualized_return = (1 + total_return) ** (1 / years) - 1
    elif (1 + total_return) <= 0:
        annualized_return = -1.0  # wiped out
    else:
        annualized_return = 0.0

    # ----- max drawdown -----
    peaks = equity.cummax()
    # peaks > 0 always when initial > 0; guard div anyway.
    drawdowns = (equity - peaks) / peaks.where(peaks != 0, 1.0)
    max_drawdown = float(drawdowns.min()) if not drawdowns.empty else 0.0

    # ----- sharpe (annualized, rf=0) -----
    returns = equity.pct_change().dropna()
    if len(returns) > 1 and returns.std() > 0 and bar_seconds > 0:
        bars_per_year = (365.25 * 86400) / bar_seconds
        sharpe = float((returns.mean() / returns.std()) * np.sqrt(bars_per_year))
    else:
        sharpe = 0.0

    # ----- trade-derived metrics -----
    trades = pair_fills_to_trades(fills)
    if trades:
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl < 0]
        win_rate = len(wins) / len(trades)
        sum_wins = sum(t.pnl for t in wins)
        sum_losses = abs(sum(t.pnl for t in losses))
        if sum_losses > 0:
            profit_factor = sum_wins / sum_losses
        elif sum_wins > 0:
            profit_factor = float("inf")
        else:
            profit_factor = 0.0
    else:
        win_rate = 0.0
        profit_factor = 0.0

    return Metrics(
        total_return=total_return,
        annualized_return=annualized_return,
        max_drawdown=max_drawdown,
        sharpe_ratio=sharpe,
        win_rate=win_rate,
        profit_factor=profit_factor,
        n_trades=len(trades),
    )
