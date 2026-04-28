"""Tests for ExecutionModel."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from hindcast.backtest.execution import SimpleExecutionModel
from hindcast.backtest.types import Bar, OrderIntent

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)
T1 = T0 + timedelta(hours=1)


def _bar(open_: float, ts: datetime = T1) -> Bar:
    return Bar(timestamp=ts, open=open_, high=open_, low=open_, close=open_, volume=1.0)


def _intent(side: str, qty: float = 1.0) -> OrderIntent:
    return OrderIntent(side=side, quantity=qty, bar_timestamp=T0)  # type: ignore[arg-type]


# ---------- direction of slippage ----------


def test_buy_slippage_pushes_price_up() -> None:
    em = SimpleExecutionModel(fee_pct=0.0, slippage_pct=0.001)
    fill = em.execute(_intent("buy"), _bar(100.0))
    assert fill.price > 100.0
    assert fill.price == pytest.approx(100.0 * 1.001)


def test_sell_slippage_pushes_price_down() -> None:
    em = SimpleExecutionModel(fee_pct=0.0, slippage_pct=0.001)
    fill = em.execute(_intent("sell"), _bar(100.0))
    assert fill.price < 100.0
    assert fill.price == pytest.approx(100.0 * 0.999)


# ---------- fees ----------


def test_fee_is_pct_of_notional() -> None:
    em = SimpleExecutionModel(fee_pct=0.002, slippage_pct=0.0)
    fill = em.execute(_intent("buy", qty=2.0), _bar(500.0))
    # exec_price = 500, notional = 1000, fee = 1000 * 0.002 = 2.0
    assert fill.price == pytest.approx(500.0)
    assert fill.fee == pytest.approx(2.0)


def test_zero_slippage_zero_fee_is_lossless() -> None:
    em = SimpleExecutionModel(fee_pct=0.0, slippage_pct=0.0)
    fill = em.execute(_intent("buy", qty=1.0), _bar(123.45))
    assert fill.price == pytest.approx(123.45)
    assert fill.fee == 0.0
    fill_s = em.execute(_intent("sell", qty=1.0), _bar(123.45))
    assert fill_s.price == pytest.approx(123.45)
    assert fill_s.fee == 0.0


# ---------- canonical default-params trade ----------


def test_default_params_one_btc_buy() -> None:
    """1 BTC buy at $100,000 with default fee/slippage.

    exec_price = 100000 * (1 + 0.0005) = 100050.0
    notional   = 100050.0
    fee        = 100050.0 * 0.001 = 100.05
    """
    em = SimpleExecutionModel()  # defaults: fee=0.001, slip=0.0005
    fill = em.execute(_intent("buy", qty=1.0), _bar(100_000.0))
    assert fill.price == pytest.approx(100_050.0)
    assert fill.fee == pytest.approx(100.05)
    assert fill.side == "buy"
    assert fill.quantity == 1.0


# ---------- linkage / metadata ----------


def test_fill_links_back_to_intent_and_uses_next_bar_timestamp() -> None:
    em = SimpleExecutionModel()
    intent = _intent("buy", qty=1.0)
    bar = _bar(100.0, ts=T1)
    fill = em.execute(intent, bar)
    assert fill.intent_timestamp == T0  # original decision time
    assert fill.timestamp == T1  # actual execution time = next bar


# ---------- validation ----------


def test_negative_fee_or_slippage_rejected() -> None:
    with pytest.raises(ValueError):
        SimpleExecutionModel(fee_pct=-0.001)
    with pytest.raises(ValueError):
        SimpleExecutionModel(slippage_pct=-0.0005)
