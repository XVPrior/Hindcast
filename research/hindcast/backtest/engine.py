"""BacktestEngine — the event loop that wires Strategy + Execution + Portfolio.

The loop is intentionally short. The look-ahead-free guarantee comes from
*ordering* alone:

  for each bar t:
    1. fill any intents produced on bar t-1, using t.open
    2. mark-to-market using t.close
    3. ask the strategy for new intents, given everything up to t

Intents produced on the final bar never fill — there is no t+1.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterable

import pandas as pd

from .execution import ExecutionModel
from .metrics import compute_metrics
from .portfolio import Portfolio
from .strategy import Strategy, StrategyContext
from .types import Bar, Fill, Metrics, OrderIntent

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    equity_curve: pd.DataFrame
    fills: list[Fill]
    metrics: Metrics | None = None  # populated in Task 2.6


class BacktestEngine:
    def __init__(
        self,
        strategy: Strategy,
        execution_model: ExecutionModel,
        portfolio: Portfolio,
    ) -> None:
        self.strategy = strategy
        self.execution_model = execution_model
        self.portfolio = portfolio

    def run(self, bars: Iterable[Bar]) -> BacktestResult:
        bars_list = list(bars)
        if not bars_list:
            raise ValueError("bars is empty — nothing to backtest")

        pending: list[OrderIntent] = []
        history: list[Bar] = []  # all bars seen *before* current

        for current_bar in bars_list:
            # 1. Settle anything pending from the previous bar.
            if pending:
                self._execute_pending(pending, current_bar)
                pending = []

            # 2. Mark-to-market using current bar's close. Always one entry
            #    per bar, regardless of whether anything traded.
            self.portfolio.mark_to_market(current_bar)

            # 3. Ask the strategy for new intents. context.history excludes
            #    the current bar (the `bar` arg carries that).
            ctx = StrategyContext(
                current_cash=self.portfolio.cash,
                current_position=self.portfolio.position,
                current_equity=self.portfolio.equity_history[-1].equity,
                history=history,
            )
            new_intents = self.strategy.on_bar(current_bar, ctx)
            pending.extend(new_intents)

            # 4. Now current bar joins the past for subsequent calls.
            history.append(current_bar)

        if pending:
            logger.info(
                "Backtest ended with %d unfilled intent(s) on the last bar",
                len(pending),
            )

        equity_curve_df = self._equity_curve_df()
        bar_seconds = (
            int((bars_list[1].timestamp - bars_list[0].timestamp).total_seconds())
            if len(bars_list) >= 2
            else 0
        )
        metrics = compute_metrics(
            equity_curve_df, self.portfolio.fill_history, bar_seconds
        )
        return BacktestResult(
            equity_curve=equity_curve_df,
            fills=self.portfolio.fill_history,
            metrics=metrics,
        )

    # ---------- internals ----------

    def _execute_pending(
        self, pending: list[OrderIntent], current_bar: Bar
    ) -> None:
        for intent in pending:
            fill = self.execution_model.execute(intent, current_bar)
            if self.portfolio.can_afford(fill):
                self.portfolio.apply_fill(fill)
            else:
                logger.warning(
                    "Cannot afford intent %s (fill price=%.6f, fee=%.6f); skipping",
                    intent, fill.price, fill.fee,
                )

    def _equity_curve_df(self) -> pd.DataFrame:
        records = [
            {
                "timestamp": p.timestamp,
                "cash": p.cash,
                "position": p.position,
                "price": p.price,
                "equity": p.equity,
            }
            for p in self.portfolio.equity_history
        ]
        return pd.DataFrame(records)
