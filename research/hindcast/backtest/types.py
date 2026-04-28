"""Immutable data types for the backtest engine.

These are the nouns shared by every other module: Bars in, Intents and
Fills moving through, Equity points coming out, Metrics summarising.

All frozen — once an engine has handed a value to a strategy, that value
must not change underfoot.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import pandas as pd

Side = Literal["buy", "sell"]


@dataclass(frozen=True, slots=True)
class Bar:
    """One OHLCV candle. The unit of information a strategy sees per step."""

    timestamp: datetime  # UTC; the bar's open time
    open: float
    high: float
    low: float
    close: float
    volume: float

    @classmethod
    def from_series(cls, s: pd.Series) -> Bar:
        """Build a Bar from a row of an OHLCV DataFrame.

        Extra columns (exchange, symbol, timeframe, ...) are ignored, so
        rows from `Storage.query_ohlcv` work directly.
        """
        ts = s["timestamp"]
        if isinstance(ts, pd.Timestamp):
            ts = ts.to_pydatetime()
        return cls(
            timestamp=ts,
            open=float(s["open"]),
            high=float(s["high"]),
            low=float(s["low"]),
            close=float(s["close"]),
            volume=float(s["volume"]),
        )


@dataclass(frozen=True, slots=True)
class OrderIntent:
    """A trade the strategy *wants* to make. Not yet executed."""

    side: Side
    quantity: float  # in base-asset units (e.g. BTC count, not USDT)
    bar_timestamp: datetime  # the bar on which the strategy decided


@dataclass(frozen=True, slots=True)
class Fill:
    """The realised result of an OrderIntent: actually transacted."""

    timestamp: datetime  # when the fill happened (the next bar's open)
    side: Side
    quantity: float
    price: float  # post-slippage execution price
    fee: float  # quote-asset fee (USDT)
    intent_timestamp: datetime  # which bar the originating intent came from


@dataclass(frozen=True, slots=True)
class EquityPoint:
    """A single mark-to-market snapshot.

    Carries the breakdown (cash + position * price = equity) so downstream
    analysis doesn't have to recompute it from fills.
    """

    timestamp: datetime
    cash: float
    position: float
    price: float  # mark price used to value the position
    equity: float


@dataclass(frozen=True, slots=True)
class Metrics:
    """Summary statistics derived from an equity curve and fill log."""

    total_return: float
    annualized_return: float
    max_drawdown: float
    sharpe_ratio: float
    win_rate: float
    profit_factor: float
    n_trades: int
