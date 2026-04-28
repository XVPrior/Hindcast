"""Tests for backtest data types: construction + immutability."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pandas as pd
import pytest

from hindcast.backtest.types import (
    Bar,
    EquityPoint,
    Fill,
    Metrics,
    OrderIntent,
)


UTC = timezone.utc


# ---------- Bar ----------


def test_bar_construction() -> None:
    b = Bar(
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        open=100.0, high=101.0, low=99.0, close=100.5, volume=10.0,
    )
    assert b.open == 100.0
    assert b.timestamp.year == 2024


def test_bar_is_frozen() -> None:
    b = Bar(datetime(2024, 1, 1, tzinfo=UTC), 100.0, 101.0, 99.0, 100.5, 10.0)
    with pytest.raises(FrozenInstanceError):
        b.close = 200.0  # type: ignore[misc]


def test_bar_from_series() -> None:
    s = pd.Series({
        "timestamp": pd.Timestamp("2024-01-01", tz="UTC"),
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "volume": 10.0,
    })
    b = Bar.from_series(s)
    assert b.open == 100.0
    assert b.close == 100.5
    assert b.timestamp == datetime(2024, 1, 1, tzinfo=UTC)


def test_bar_from_series_ignores_extra_columns() -> None:
    # A row from Storage.query_ohlcv has exchange/symbol/timeframe too.
    s = pd.Series({
        "exchange": "binance",
        "symbol": "BTC/USDT",
        "timeframe": "1h",
        "timestamp": pd.Timestamp("2024-01-01", tz="UTC"),
        "open": 100.0, "high": 101.0, "low": 99.0,
        "close": 100.5, "volume": 10.0,
    })
    b = Bar.from_series(s)
    assert b.open == 100.0


# ---------- OrderIntent ----------


def test_order_intent_construction() -> None:
    intent = OrderIntent(
        side="buy", quantity=0.5,
        bar_timestamp=datetime(2024, 1, 1, tzinfo=UTC),
    )
    assert intent.side == "buy"
    assert intent.quantity == 0.5


def test_order_intent_is_frozen() -> None:
    intent = OrderIntent("buy", 0.5, datetime(2024, 1, 1, tzinfo=UTC))
    with pytest.raises(FrozenInstanceError):
        intent.quantity = 1.0  # type: ignore[misc]


# ---------- Fill ----------


def test_fill_construction() -> None:
    f = Fill(
        timestamp=datetime(2024, 1, 1, 1, tzinfo=UTC),
        side="buy", quantity=0.5, price=42000.0, fee=10.5,
        intent_timestamp=datetime(2024, 1, 1, 0, tzinfo=UTC),
    )
    assert f.price == 42000.0
    # Fill is on a later bar than the intent — the 1-bar delay.
    assert f.timestamp > f.intent_timestamp


def test_fill_is_frozen() -> None:
    f = Fill(
        datetime(2024, 1, 1, 1, tzinfo=UTC), "buy", 0.5, 42000.0, 10.5,
        datetime(2024, 1, 1, 0, tzinfo=UTC),
    )
    with pytest.raises(FrozenInstanceError):
        f.price = 0.0  # type: ignore[misc]


# ---------- EquityPoint ----------


def test_equity_point_construction() -> None:
    p = EquityPoint(
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        cash=500.0, position=1.0, price=10_000.0, equity=10_500.0,
    )
    assert p.equity == 10_500.0
    assert p.cash + p.position * p.price == pytest.approx(p.equity)


def test_equity_point_is_frozen() -> None:
    p = EquityPoint(
        datetime(2024, 1, 1, tzinfo=UTC), 500.0, 1.0, 10_000.0, 10_500.0,
    )
    with pytest.raises(FrozenInstanceError):
        p.equity = 0.0  # type: ignore[misc]


# ---------- Metrics ----------


def test_metrics_construction() -> None:
    m = Metrics(
        total_return=0.25, annualized_return=0.18, max_drawdown=-0.12,
        sharpe_ratio=1.4, win_rate=0.55, profit_factor=1.8, n_trades=42,
    )
    assert m.n_trades == 42
    assert m.sharpe_ratio == 1.4


def test_metrics_is_frozen() -> None:
    m = Metrics(0.25, 0.18, -0.12, 1.4, 0.55, 1.8, 42)
    with pytest.raises(FrozenInstanceError):
        m.sharpe_ratio = 0.0  # type: ignore[misc]
