"""Portfolio: cash + position state machine.

This is the most bug-prone module in M2 — every fill mutates state, and
silent off-by-one floats compound across thousands of bars. Two invariants
are enforced loudly:

  1. cash >= 0 after every fill (no overdraft)
  2. position >= 0 after every fill (no naked shorts in v0)

Violations raise specific exceptions so a buggy strategy fails loud, not
silently producing impossible equity curves.
"""

from __future__ import annotations

from .types import Bar, EquityPoint, Fill


class PortfolioError(Exception):
    """Base for portfolio invariant violations."""


class InsufficientFundsError(PortfolioError):
    """A buy fill would push cash negative."""


class InsufficientPositionError(PortfolioError):
    """A sell fill would push position negative (naked short)."""


class Portfolio:
    def __init__(self, initial_cash: float) -> None:
        if initial_cash < 0:
            raise ValueError("initial_cash must be non-negative")
        self.cash: float = initial_cash
        self.position: float = 0.0
        self.fill_history: list[Fill] = []
        self.equity_history: list[EquityPoint] = []

    # ---------- mutating ----------

    def apply_fill(self, fill: Fill) -> None:
        """Commit a fill: update cash, position, and the fill log.

        Raises if the fill would violate an invariant — caller must check
        with `can_afford` first.
        """
        if fill.side == "buy":
            cost = fill.price * fill.quantity + fill.fee
            if cost > self.cash:
                raise InsufficientFundsError(
                    f"buy needs {cost:.8f} but only {self.cash:.8f} available"
                )
            self.cash -= cost
            self.position += fill.quantity
        else:  # sell
            if fill.quantity > self.position:
                raise InsufficientPositionError(
                    f"sell of {fill.quantity:.8f} exceeds position {self.position:.8f}"
                )
            proceeds = fill.price * fill.quantity - fill.fee
            self.cash += proceeds
            self.position -= fill.quantity

        self.fill_history.append(fill)

    def mark_to_market(self, bar: Bar) -> None:
        """Append an EquityPoint snapshot using `bar.close` as the mark price.

        Called once per bar by the engine — every bar contributes to the
        equity curve, even bars without trades.
        """
        equity = self.cash + self.position * bar.close
        self.equity_history.append(EquityPoint(
            timestamp=bar.timestamp,
            cash=self.cash,
            position=self.position,
            price=bar.close,
            equity=equity,
        ))

    # ---------- non-mutating ----------

    def can_afford(self, fill: Fill) -> bool:
        """Would `apply_fill(fill)` succeed?

        Note: takes a Fill, not (Intent, next_bar) — see commit message.
        Engine pattern: execute(intent)→fill, can_afford(fill), apply_fill(fill).
        """
        if fill.side == "buy":
            return fill.price * fill.quantity + fill.fee <= self.cash
        return fill.quantity <= self.position
