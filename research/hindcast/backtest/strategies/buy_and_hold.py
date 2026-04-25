"""Buy-and-hold: spend cash on the first bar, then sit forever.

The benchmark every other strategy must beat. If a clever strategy
underperforms this, it's noise — or worse, it's destroying value through
fees and slippage.
"""

from __future__ import annotations

from ..strategy import StrategyContext
from ..types import Bar, OrderIntent


class BuyAndHold:
    """Allocate `allocation_pct` of starting cash on the very first bar."""

    def __init__(self, allocation_pct: float = 1.0) -> None:
        if not 0 < allocation_pct <= 1:
            raise ValueError("allocation_pct must be in (0, 1]")
        self.allocation_pct = allocation_pct
        self._has_bought = False

    def on_bar(self, bar: Bar, context: StrategyContext) -> list[OrderIntent]:
        if self._has_bought:
            return []

        # Size by current close as an estimate; actual fill price will be the
        # next bar's open. Engine's affordability check rejects if too aggressive.
        budget = context.current_cash * self.allocation_pct
        qty = budget / bar.close
        if qty <= 0:
            return []

        self._has_bought = True
        return [OrderIntent(side="buy", quantity=qty, bar_timestamp=bar.timestamp)]
