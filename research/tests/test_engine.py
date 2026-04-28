"""Integration tests for BacktestEngine."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pytest

from hindcast.backtest.engine import BacktestEngine, BacktestResult
from hindcast.backtest.execution import SimpleExecutionModel
from hindcast.backtest.portfolio import Portfolio
from hindcast.backtest.strategies.buy_and_hold import BuyAndHold
from hindcast.backtest.strategies.ma_crossover import MACrossover
from hindcast.backtest.strategy import StrategyContext
from hindcast.backtest.types import Bar, OrderIntent

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _bars(prices: list[float]) -> list[Bar]:
    """Build bars where open == close == price (clean math for tests)."""
    return [
        Bar(
            timestamp=T0 + timedelta(hours=i),
            open=p, high=p, low=p, close=p, volume=1.0,
        )
        for i, p in enumerate(prices)
    ]


# ---------- buy_and_hold end-to-end ----------


def test_buy_and_hold_final_equity_matches_hand_calc() -> None:
    """Buy on bar 0, fill on bar 1, ride a +10% move at bar 5, hold until end.

    Hand calc with zero fee/slippage and allocation_pct=1.0:
      bar 0: buy intent, qty = 10000 / 100 = 100
      bar 1: execute @ 100 → cash=0, pos=100, mtm equity = 0 + 100*100 = 10000
      bar 2..4: mtm at 100 → equity = 10000
      bar 5..9: mtm at 110 → equity = 0 + 100*110 = 11000
    """
    bars = _bars([100.0] * 5 + [110.0] * 5)
    engine = BacktestEngine(
        strategy=BuyAndHold(allocation_pct=1.0),
        execution_model=SimpleExecutionModel(fee_pct=0.0, slippage_pct=0.0),
        portfolio=Portfolio(initial_cash=10_000.0),
    )
    result = engine.run(bars)

    assert isinstance(result, BacktestResult)
    assert len(result.equity_curve) == 10
    assert len(result.fills) == 1
    assert result.fills[0].side == "buy"
    assert result.fills[0].quantity == pytest.approx(100.0)
    assert result.equity_curve["equity"].iloc[-1] == pytest.approx(11_000.0)
    # Sanity: equity is non-decreasing once we're in position with rising price.
    assert result.equity_curve["equity"].iloc[4] == pytest.approx(10_000.0)
    assert result.equity_curve["equity"].iloc[5] == pytest.approx(11_000.0)


# ---------- ma_crossover smoke ----------


def test_ma_crossover_runs_and_produces_fills() -> None:
    # 50 bars up from 100 to 150, then 50 bars down from 150 to 100.
    # Guarantees at least one up-cross and one down-cross with small windows.
    up = [100.0 + i for i in range(50)]
    down = [150.0 - i for i in range(50)]
    bars = _bars(up + down)

    engine = BacktestEngine(
        strategy=MACrossover(fast_window=5, slow_window=20, allocation_pct=0.99),
        execution_model=SimpleExecutionModel(fee_pct=0.001, slippage_pct=0.0005),
        portfolio=Portfolio(initial_cash=10_000.0),
    )
    result = engine.run(bars)

    assert len(result.equity_curve) == 100
    assert len(result.fills) > 0
    # By construction we should see both sides (up cross + down cross).
    sides = {f.side for f in result.fills}
    assert "buy" in sides
    assert "sell" in sides


# ---------- look-ahead-free invariants ----------


def test_intent_fills_strictly_after_decision_bar() -> None:
    bars = _bars([100.0, 100.0, 100.0])
    engine = BacktestEngine(
        BuyAndHold(),
        SimpleExecutionModel(fee_pct=0.0, slippage_pct=0.0),
        Portfolio(10_000.0),
    )
    result = engine.run(bars)
    for fill in result.fills:
        assert fill.timestamp > fill.intent_timestamp


def test_equity_history_length_matches_bars() -> None:
    bars = _bars([100.0] * 25)
    engine = BacktestEngine(
        BuyAndHold(),
        SimpleExecutionModel(fee_pct=0.0, slippage_pct=0.0),
        Portfolio(10_000.0),
    )
    result = engine.run(bars)
    assert len(result.equity_curve) == 25


# ---------- edge cases ----------


def test_single_bar_runs_with_no_fills() -> None:
    """One bar — strategy emits intent but there's no next bar to fill on."""
    bars = _bars([100.0])
    engine = BacktestEngine(
        BuyAndHold(),
        SimpleExecutionModel(fee_pct=0.0, slippage_pct=0.0),
        Portfolio(10_000.0),
    )
    result = engine.run(bars)
    assert len(result.equity_curve) == 1
    assert len(result.fills) == 0
    assert result.equity_curve["equity"].iloc[0] == pytest.approx(10_000.0)


def test_empty_bars_raises() -> None:
    engine = BacktestEngine(
        BuyAndHold(),
        SimpleExecutionModel(),
        Portfolio(10_000.0),
    )
    with pytest.raises(ValueError, match="empty"):
        engine.run([])


# ---------- can_afford skip + warning ----------


def test_unaffordable_intent_is_skipped_with_warning(caplog: pytest.LogCaptureFixture) -> None:
    """Strategy estimates by close ($100), but next-bar open jumps to $200."""

    class JumpyBars(list[Bar]):
        pass

    bars = [
        Bar(T0, 100.0, 100.0, 100.0, 100.0, 1.0),  # close=100, strategy sizes here
        Bar(T0 + timedelta(hours=1), 200.0, 200.0, 200.0, 200.0, 1.0),  # open=200, fills here
    ]
    engine = BacktestEngine(
        # allocation_pct=1.0 → strategy intends to spend all 10000 at $100 → 100 BTC.
        # On bar 1 open=200 → cost = 100 * 200 = 20000, cash only 10000 → reject.
        BuyAndHold(allocation_pct=1.0),
        SimpleExecutionModel(fee_pct=0.0, slippage_pct=0.0),
        Portfolio(initial_cash=10_000.0),
    )
    with caplog.at_level(logging.WARNING, logger="hindcast.backtest.engine"):
        result = engine.run(bars)

    assert len(result.fills) == 0
    # Cash and position unchanged.
    assert engine.portfolio.cash == 10_000.0
    assert engine.portfolio.position == 0.0
    assert any("Cannot afford" in rec.message for rec in caplog.records)


# ---------- context shape (regression: history excludes current) ----------


def test_strategy_sees_history_excluding_current_bar() -> None:
    seen_history_lengths: list[int] = []

    class HistoryProbe:
        def on_bar(self, bar: Bar, context: StrategyContext) -> list[OrderIntent]:
            seen_history_lengths.append(len(context.history))
            return []

    bars = _bars([100.0, 101.0, 102.0])
    engine = BacktestEngine(
        HistoryProbe(),
        SimpleExecutionModel(),
        Portfolio(10_000.0),
    )
    engine.run(bars)
    # On bar i, history should have i prior bars (0 on first call).
    assert seen_history_lengths == [0, 1, 2]
