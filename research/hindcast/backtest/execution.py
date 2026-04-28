"""Execution models: turn an OrderIntent into a Fill.

The engine produces Intents on bar T's close and asks the ExecutionModel to
fill them on bar T+1's open. Slippage and fees live here.
"""

from __future__ import annotations

from typing import Protocol

from .types import Bar, Fill, OrderIntent


class ExecutionModel(Protocol):
    def execute(self, intent: OrderIntent, next_bar: Bar) -> Fill:
        ...


class SimpleExecutionModel:
    """Constant-percent slippage and fee.

    - Buy fills at next_bar.open * (1 + slippage_pct).
    - Sell fills at next_bar.open * (1 - slippage_pct).
    - Fee is `fee_pct` of notional, paid in the quote asset (USDT).
    """

    def __init__(
        self,
        fee_pct: float = 0.001,        # 0.1% — Binance spot taker default
        slippage_pct: float = 0.0005,  # 0.05%
    ) -> None:
        if fee_pct < 0:
            raise ValueError("fee_pct must be non-negative")
        if slippage_pct < 0:
            raise ValueError("slippage_pct must be non-negative")
        self.fee_pct = fee_pct
        self.slippage_pct = slippage_pct

    def execute(self, intent: OrderIntent, next_bar: Bar) -> Fill:
        if intent.side == "buy":
            exec_price = next_bar.open * (1 + self.slippage_pct)
        else:
            exec_price = next_bar.open * (1 - self.slippage_pct)

        notional = exec_price * intent.quantity
        fee = notional * self.fee_pct

        return Fill(
            timestamp=next_bar.timestamp,
            side=intent.side,
            quantity=intent.quantity,
            price=exec_price,
            fee=fee,
            intent_timestamp=intent.bar_timestamp,
        )
