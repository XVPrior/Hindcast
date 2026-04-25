"""Strategy interface.

A strategy is anything implementing `on_bar(bar, context) -> list[OrderIntent]`.
We use Protocol (not ABC) so users can write a plain class without inheritance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .types import Bar, OrderIntent


@dataclass(frozen=True, slots=True)
class StrategyContext:
    """Engine-supplied snapshot handed to the strategy each bar.

    `history` contains every bar seen *before* the current one, oldest first.
    The current bar is the `bar` argument to `on_bar` — not included here, so
    there's a clean past/present split.

    Strategies should treat `history` as read-only.
    """

    current_cash: float
    current_position: float  # base-asset units (e.g. BTC)
    current_equity: float
    history: list[Bar]


class Strategy(Protocol):
    """Anything with this method shape qualifies as a strategy."""

    def on_bar(self, bar: Bar, context: StrategyContext) -> list[OrderIntent]:
        ...
