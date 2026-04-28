"""Tests for Portfolio. Aims for full branch coverage of the state machine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from hindcast.backtest.portfolio import (
    InsufficientFundsError,
    InsufficientPositionError,
    Portfolio,
)
from hindcast.backtest.types import Bar, Fill

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _bar(hours: int, close: float) -> Bar:
    return Bar(
        timestamp=T0 + timedelta(hours=hours),
        open=close, high=close, low=close, close=close, volume=1.0,
    )


def _fill(hours: int, side: str, qty: float, price: float, fee: float = 0.0) -> Fill:
    return Fill(
        timestamp=T0 + timedelta(hours=hours),
        side=side,  # type: ignore[arg-type]
        quantity=qty, price=price, fee=fee,
        intent_timestamp=T0 + timedelta(hours=hours - 1),
    )


# ---------- construction ----------


def test_initial_state() -> None:
    p = Portfolio(initial_cash=10_000.0)
    assert p.cash == 10_000.0
    assert p.position == 0.0
    assert p.fill_history == []
    assert p.equity_history == []


def test_negative_initial_cash_rejected() -> None:
    with pytest.raises(ValueError):
        Portfolio(initial_cash=-1.0)


# ---------- apply_fill: buy ----------


def test_apply_fill_buy_deducts_cost_and_adds_position() -> None:
    p = Portfolio(10_000.0)
    p.apply_fill(_fill(1, "buy", qty=1.0, price=100.0, fee=0.1))
    assert p.cash == pytest.approx(9_899.9)  # 10000 - (100 + 0.1)
    assert p.position == 1.0
    assert len(p.fill_history) == 1


def test_apply_fill_buy_insufficient_funds_raises() -> None:
    p = Portfolio(50.0)
    # Need 100.5; only 50 available.
    with pytest.raises(InsufficientFundsError, match="100.50000000"):
        p.apply_fill(_fill(1, "buy", qty=1.0, price=100.0, fee=0.5))
    # State must be untouched on failure.
    assert p.cash == 50.0
    assert p.position == 0.0
    assert p.fill_history == []


def test_apply_fill_buy_exactly_at_cash_succeeds() -> None:
    p = Portfolio(100.1)
    p.apply_fill(_fill(1, "buy", qty=1.0, price=100.0, fee=0.1))
    assert p.cash == pytest.approx(0.0)
    assert p.position == 1.0


# ---------- apply_fill: sell ----------


def test_apply_fill_sell_credits_proceeds_and_reduces_position() -> None:
    p = Portfolio(0.0)
    p.position = 2.0  # set up by hand for isolation
    p.apply_fill(_fill(1, "sell", qty=1.0, price=200.0, fee=0.2))
    assert p.cash == pytest.approx(199.8)  # 200 - 0.2
    assert p.position == 1.0


def test_apply_fill_sell_oversell_raises() -> None:
    p = Portfolio(0.0)
    p.position = 0.5
    with pytest.raises(InsufficientPositionError, match="1.00000000"):
        p.apply_fill(_fill(1, "sell", qty=1.0, price=200.0, fee=0.2))
    assert p.position == 0.5


def test_apply_fill_sell_full_liquidation() -> None:
    p = Portfolio(0.0)
    p.position = 1.0
    p.apply_fill(_fill(1, "sell", qty=1.0, price=200.0, fee=0.2))
    assert p.position == 0.0
    assert p.cash == pytest.approx(199.8)


# ---------- can_afford ----------


def test_can_afford_buy_true_when_sufficient() -> None:
    p = Portfolio(200.0)
    assert p.can_afford(_fill(1, "buy", 1.0, 100.0, fee=0.1)) is True


def test_can_afford_buy_false_when_short_by_a_cent() -> None:
    p = Portfolio(100.0)
    assert p.can_afford(_fill(1, "buy", 1.0, 100.0, fee=0.01)) is False


def test_can_afford_sell_true_when_position_sufficient() -> None:
    p = Portfolio(0.0)
    p.position = 1.0
    assert p.can_afford(_fill(1, "sell", 1.0, 100.0, fee=0.0)) is True


def test_can_afford_sell_false_when_oversell() -> None:
    p = Portfolio(0.0)
    p.position = 0.5
    assert p.can_afford(_fill(1, "sell", 1.0, 100.0, fee=0.0)) is False


# ---------- mark_to_market ----------


def test_mark_to_market_records_one_point_per_call() -> None:
    p = Portfolio(10_000.0)
    for i in range(5):
        p.mark_to_market(_bar(i, close=100.0 + i))
    assert len(p.equity_history) == 5
    assert [pt.equity for pt in p.equity_history] == [10_000.0] * 5  # no position


def test_mark_to_market_reflects_position_value() -> None:
    p = Portfolio(0.0)
    p.position = 2.0
    p.mark_to_market(_bar(0, close=150.0))
    pt = p.equity_history[-1]
    assert pt.equity == pytest.approx(300.0)
    assert pt.cash == 0.0
    assert pt.position == 2.0
    assert pt.price == 150.0
    assert pt.timestamp == T0


# ---------- end-to-end flow ----------


def test_full_buy_hold_sell_flow_matches_hand_calc() -> None:
    """Buy 1 BTC @ $100 (fee $0.1), hold 5 bars, sell @ $130 (fee $0.13).

    Hand calc:
      Initial cash: 10,000
      Buy:   cash = 10000 - (100*1 + 0.1) = 9899.9, pos = 1.0
      Hold:  equity_history grows by 5 entries during mark-to-market
      Sell:  cash = 9899.9 + (130*1 - 0.13) = 10029.77, pos = 0
      Final equity = 10029.77 (cash only, no position)
    """
    p = Portfolio(10_000.0)

    # Buy on bar 1 (decision was on bar 0)
    p.apply_fill(_fill(1, "buy", qty=1.0, price=100.0, fee=0.1))
    p.mark_to_market(_bar(1, close=100.0))
    assert p.equity_history[-1].equity == pytest.approx(9_999.9)  # 9899.9 + 100

    # Hold 5 more bars — varying prices but no trades
    hold_prices = [105.0, 110.0, 108.0, 115.0, 120.0]
    for i, price in enumerate(hold_prices, start=2):
        p.mark_to_market(_bar(i, close=price))

    assert len(p.equity_history) == 6  # 1 (post-buy) + 5 (hold)
    # equity at end of hold: cash + 1 * 120 = 9899.9 + 120 = 10019.9
    assert p.equity_history[-1].equity == pytest.approx(10_019.9)

    # Sell on bar 7
    p.apply_fill(_fill(7, "sell", qty=1.0, price=130.0, fee=0.13))
    p.mark_to_market(_bar(7, close=130.0))

    assert p.cash == pytest.approx(10_029.77)
    assert p.position == 0.0
    # post-sell equity = cash (no position)
    assert p.equity_history[-1].equity == pytest.approx(10_029.77)
    assert len(p.fill_history) == 2
    assert len(p.equity_history) == 7


def test_multiple_partial_buys_accumulate() -> None:
    p = Portfolio(1_000.0)
    p.apply_fill(_fill(1, "buy", 0.3, 100.0, fee=0.0))  # cost 30
    p.apply_fill(_fill(2, "buy", 0.4, 100.0, fee=0.0))  # cost 40
    p.apply_fill(_fill(3, "buy", 0.2, 100.0, fee=0.0))  # cost 20
    assert p.position == pytest.approx(0.9)
    assert p.cash == pytest.approx(910.0)
    assert len(p.fill_history) == 3
