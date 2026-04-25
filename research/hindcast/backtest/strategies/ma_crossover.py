"""Dual moving-average crossover. Long-only.

Signal logic:
- fast SMA crosses *above* slow SMA → enter long (when flat)
- fast SMA crosses *below* slow SMA → exit long (when in position)

Maintains its own rolling window — the engine doesn't track per-strategy state.
"""

from __future__ import annotations

from collections import deque

from ..strategy import StrategyContext
from ..types import Bar, OrderIntent


class MACrossover:
    def __init__(
        self,
        fast_window: int = 10,
        slow_window: int = 30,
        allocation_pct: float = 1.0,
    ) -> None:
        if fast_window <= 0 or slow_window <= 0:
            raise ValueError("windows must be positive")
        if fast_window >= slow_window:
            raise ValueError("fast_window must be < slow_window")
        if not 0 < allocation_pct <= 1:
            raise ValueError("allocation_pct must be in (0, 1]")

        self.fast_window = fast_window
        self.slow_window = slow_window
        self.allocation_pct = allocation_pct
        self._closes: deque[float] = deque(maxlen=slow_window)
        self._prev_signal: int = 0  # +1 fast>slow, -1 fast<slow, 0 undecided

    def on_bar(self, bar: Bar, context: StrategyContext) -> list[OrderIntent]:
        self._closes.append(bar.close)

        if len(self._closes) < self.slow_window:
            return []  # warmup

        arr = list(self._closes)
        fast = sum(arr[-self.fast_window:]) / self.fast_window
        slow = sum(arr) / self.slow_window
        signal = 1 if fast > slow else (-1 if fast < slow else 0)

        intents: list[OrderIntent] = []
        if signal == 1 and self._prev_signal != 1 and context.current_position == 0:
            qty = (context.current_cash * self.allocation_pct) / bar.close
            if qty > 0:
                intents.append(
                    OrderIntent("buy", qty, bar.timestamp)
                )
        elif signal == -1 and self._prev_signal != -1 and context.current_position > 0:
            intents.append(
                OrderIntent("sell", context.current_position, bar.timestamp)
            )

        # Only update prev when signal is decisive; flat ties don't reset state.
        if signal != 0:
            self._prev_signal = signal

        return intents
