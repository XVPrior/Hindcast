"""Tests for metrics: pair_fills_to_trades + compute_metrics."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from hindcast.backtest.metrics import compute_metrics, pair_fills_to_trades
from hindcast.backtest.types import Fill

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _fill(hours: int, side: str, qty: float, price: float, fee: float = 0.0) -> Fill:
    return Fill(
        timestamp=T0 + timedelta(hours=hours),
        side=side,  # type: ignore[arg-type]
        quantity=qty, price=price, fee=fee,
        intent_timestamp=T0 + timedelta(hours=max(0, hours - 1)),
    )


def _equity_df(values: list[float], bar_seconds: int = 86400) -> pd.DataFrame:
    return pd.DataFrame({
        "timestamp": [T0 + timedelta(seconds=i * bar_seconds) for i in range(len(values))],
        "equity": values,
    })


# ---------- pair_fills_to_trades ----------


def test_pair_simple_buy_then_sell() -> None:
    fills = [
        _fill(1, "buy", 1.0, 100.0, fee=0.1),
        _fill(2, "sell", 1.0, 110.0, fee=0.11),
    ]
    trades = pair_fills_to_trades(fills)
    assert len(trades) == 1
    t = trades[0]
    assert t.entry_price == 100.0
    assert t.exit_price == 110.0
    assert t.quantity == pytest.approx(1.0)
    assert t.fees == pytest.approx(0.21)
    assert t.pnl == pytest.approx((110 - 100) * 1.0 - 0.21)


def test_pair_fifo_with_partial_match() -> None:
    fills = [
        _fill(1, "buy", 1.0, 100.0),
        _fill(2, "buy", 1.0, 110.0),
        _fill(3, "sell", 1.5, 120.0),
    ]
    trades = pair_fills_to_trades(fills)
    # First trade: 1.0 @ 100 vs 1.0 @ 120
    # Second trade: 0.5 @ 110 vs 0.5 @ 120
    assert len(trades) == 2
    assert trades[0].quantity == pytest.approx(1.0)
    assert trades[0].pnl == pytest.approx(20.0)
    assert trades[1].quantity == pytest.approx(0.5)
    assert trades[1].pnl == pytest.approx((120 - 110) * 0.5)


def test_pair_zero_fills_returns_empty() -> None:
    assert pair_fills_to_trades([]) == []


def test_pair_unmatched_buy_left_open() -> None:
    fills = [_fill(1, "buy", 1.0, 100.0)]  # never sold
    assert pair_fills_to_trades(fills) == []


# ---------- compute_metrics: total / annualized return ----------


def test_total_return_simple() -> None:
    df = _equity_df([10_000.0, 11_000.0])
    m = compute_metrics(df, fills=[], bar_seconds=86400)
    assert m.total_return == pytest.approx(0.10)


def test_annualized_return_close_to_total_for_one_year() -> None:
    # 366 daily bars from 10000 → 11000 (∼1 year)
    n = 366
    equity = list(np.linspace(10_000.0, 11_000.0, n))
    df = _equity_df(equity)
    m = compute_metrics(df, fills=[], bar_seconds=86400)
    assert m.total_return == pytest.approx(0.10)
    assert m.annualized_return == pytest.approx(0.10, abs=0.005)


# ---------- max_drawdown ----------


def test_max_drawdown_zero_for_monotonic_up() -> None:
    df = _equity_df([100.0, 110.0, 120.0, 130.0])
    m = compute_metrics(df, fills=[], bar_seconds=86400)
    assert m.max_drawdown == pytest.approx(0.0)


def test_max_drawdown_negative_for_dip() -> None:
    df = _equity_df([100.0, 120.0, 90.0, 110.0])  # peak 120, trough 90 → -25%
    m = compute_metrics(df, fills=[], bar_seconds=86400)
    assert m.max_drawdown == pytest.approx(-0.25)


# ---------- sharpe ----------


def test_sharpe_zero_for_constant_equity() -> None:
    df = _equity_df([100.0] * 10)
    m = compute_metrics(df, fills=[], bar_seconds=86400)
    assert m.sharpe_ratio == 0.0


def test_sharpe_matches_formula() -> None:
    # Construct equity from explicit returns so we can reproduce the formula.
    rng = np.random.default_rng(42)
    rets = rng.normal(loc=0.001, scale=0.01, size=200)
    equity = (1 + rets).cumprod() * 100.0
    df = _equity_df([100.0] + list(equity))

    m = compute_metrics(df, fills=[], bar_seconds=86400)

    # Hand calc using pandas
    series = pd.Series(df["equity"].values).pct_change().dropna()
    expected = (series.mean() / series.std()) * math.sqrt(365.25)
    assert m.sharpe_ratio == pytest.approx(expected)


# ---------- win_rate / profit_factor / n_trades ----------


def test_win_rate_and_profit_factor_known() -> None:
    # 3 trades: 2 wins (+30 each), 1 loss (-20). pnl ignores fees here.
    fills = [
        _fill(1, "buy", 1.0, 100.0, fee=0.0),
        _fill(2, "sell", 1.0, 130.0, fee=0.0),  # +30
        _fill(3, "buy", 1.0, 130.0, fee=0.0),
        _fill(4, "sell", 1.0, 110.0, fee=0.0),  # -20
        _fill(5, "buy", 1.0, 110.0, fee=0.0),
        _fill(6, "sell", 1.0, 140.0, fee=0.0),  # +30
    ]
    df = _equity_df([10_000.0, 10_030.0, 10_010.0, 10_040.0])
    m = compute_metrics(df, fills, bar_seconds=86400)
    assert m.n_trades == 3
    assert m.win_rate == pytest.approx(2 / 3)
    assert m.profit_factor == pytest.approx(60.0 / 20.0)  # (30+30) / 20


def test_zero_trades() -> None:
    df = _equity_df([10_000.0, 10_000.0])
    m = compute_metrics(df, fills=[], bar_seconds=86400)
    assert m.n_trades == 0
    assert m.win_rate == 0.0
    assert m.profit_factor == 0.0


def test_single_winning_trade_gives_inf_profit_factor() -> None:
    fills = [
        _fill(1, "buy", 1.0, 100.0),
        _fill(2, "sell", 1.0, 110.0),
    ]
    df = _equity_df([10_000.0, 10_010.0])
    m = compute_metrics(df, fills, bar_seconds=86400)
    assert m.n_trades == 1
    assert m.win_rate == 1.0
    assert math.isinf(m.profit_factor)


def test_all_losing_trades() -> None:
    fills = [
        _fill(1, "buy", 1.0, 100.0),
        _fill(2, "sell", 1.0, 90.0),    # -10
        _fill(3, "buy", 1.0, 100.0),
        _fill(4, "sell", 1.0, 95.0),    # -5
    ]
    df = _equity_df([10_000.0, 9_990.0, 9_985.0])
    m = compute_metrics(df, fills, bar_seconds=86400)
    assert m.n_trades == 2
    assert m.win_rate == 0.0
    assert m.profit_factor == 0.0
