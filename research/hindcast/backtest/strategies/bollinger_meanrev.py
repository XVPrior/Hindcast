"""Bollinger Bands mean reversion. Long-only.

Logic (the canonical "swing the bands" form):
- Flat AND close < lower_band → buy  (oversold; expect mean reversion)
- Long AND close > upper_band → sell (back above fair value; book profit)

Bands are computed over a rolling `window` of closes:
    middle = mean(closes)
    upper  = middle + n_std * stdev(closes)
    lower  = middle - n_std * stdev(closes)

Maintains its own deque — engine doesn't track per-strategy state.
"""

from __future__ import annotations

import statistics
from collections import deque

from ..strategy import StrategyContext
from ..types import Bar, OrderIntent


class BollingerMeanReversion:
    def __init__(
        self,
        window: int = 20,
        n_std: float = 2.0,
        allocation_pct: float = 1.0,
    ) -> None:
        if window < 2:
            raise ValueError("window must be >= 2")
        if n_std <= 0:
            raise ValueError("n_std must be positive")
        if not 0 < allocation_pct <= 1:
            raise ValueError("allocation_pct must be in (0, 1]")

        self.window = window
        self.n_std = n_std
        self.allocation_pct = allocation_pct
        self._closes: deque[float] = deque(maxlen=window)

    def on_bar(self, bar: Bar, context: StrategyContext) -> list[OrderIntent]:
        self._closes.append(bar.close)
        if len(self._closes) < self.window:
            return []  # warmup

        arr = list(self._closes)
        middle = statistics.fmean(arr)
        std = statistics.stdev(arr)  # sample stdev (ddof=1), pandas default
        upper = middle + self.n_std * std
        lower = middle - self.n_std * std

        intents: list[OrderIntent] = []
        if context.current_position == 0 and bar.close < lower:
            qty = (context.current_cash * self.allocation_pct) / bar.close
            if qty > 0:
                intents.append(OrderIntent("buy", qty, bar.timestamp))
        elif context.current_position > 0 and bar.close > upper:
            intents.append(
                OrderIntent("sell", context.current_position, bar.timestamp)
            )

        return intents
