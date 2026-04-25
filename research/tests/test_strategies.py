"""Strategy unit tests — feed bars directly, no engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from hindcast.backtest.strategies.buy_and_hold import BuyAndHold
from hindcast.backtest.strategies.ma_crossover import MACrossover
from hindcast.backtest.strategy import StrategyContext
from hindcast.backtest.types import Bar

UTC = timezone.utc


def _bar(i: int, close: float) -> Bar:
    return Bar(
        timestamp=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(hours=i),
        open=close, high=close, low=close, close=close, volume=1.0,
    )


def _ctx(cash: float = 10_000.0, position: float = 0.0) -> StrategyContext:
    return StrategyContext(
        current_cash=cash,
        current_position=position,
        current_equity=cash + position * 100.0,
        history=[],
    )


# ---------- BuyAndHold ----------


def test_buy_and_hold_buys_on_first_bar() -> None:
    strat = BuyAndHold(allocation_pct=1.0)
    intents = strat.on_bar(_bar(0, close=100.0), _ctx(cash=10_000.0))
    assert len(intents) == 1
    assert intents[0].side == "buy"
    assert intents[0].quantity == pytest.approx(100.0)  # 10000 / 100


def test_buy_and_hold_silent_after_first_buy() -> None:
    strat = BuyAndHold()
    strat.on_bar(_bar(0, 100.0), _ctx(cash=10_000.0))
    for i in range(1, 5):
        assert strat.on_bar(_bar(i, 100.0 + i), _ctx(cash=0.0, position=100.0)) == []


def test_buy_and_hold_respects_allocation_pct() -> None:
    strat = BuyAndHold(allocation_pct=0.5)
    intents = strat.on_bar(_bar(0, close=100.0), _ctx(cash=10_000.0))
    assert intents[0].quantity == pytest.approx(50.0)


def test_buy_and_hold_rejects_invalid_allocation() -> None:
    with pytest.raises(ValueError):
        BuyAndHold(allocation_pct=0.0)
    with pytest.raises(ValueError):
        BuyAndHold(allocation_pct=1.5)


# ---------- MACrossover ----------


def test_ma_crossover_warmup_emits_nothing() -> None:
    strat = MACrossover(fast_window=2, slow_window=4)
    # First 3 bars are warmup (slow_window=4 not yet reached).
    for i, price in enumerate([100.0, 100.0, 100.0]):
        assert strat.on_bar(_bar(i, price), _ctx()) == []


def test_ma_crossover_emits_buy_on_up_cross_when_flat() -> None:
    strat = MACrossover(fast_window=2, slow_window=4)
    # Prices: 100,100,100,100 (flat — signal=0 once warm), then 110 (up cross).
    prices = [100.0, 100.0, 100.0, 100.0, 110.0]
    intents_per_bar = [strat.on_bar(_bar(i, p), _ctx()) for i, p in enumerate(prices)]
    assert all(intents == [] for intents in intents_per_bar[:4])
    assert len(intents_per_bar[4]) == 1
    assert intents_per_bar[4][0].side == "buy"


def test_ma_crossover_emits_sell_on_down_cross_when_long() -> None:
    strat = MACrossover(fast_window=2, slow_window=4)
    # Up-cross at i=4, then a hard drop at i=6 should trigger a down-cross sell.
    prices = [100.0, 100.0, 100.0, 100.0, 110.0, 130.0, 50.0]
    contexts = [
        _ctx(cash=10_000.0, position=0.0),  # 0
        _ctx(cash=10_000.0, position=0.0),  # 1
        _ctx(cash=10_000.0, position=0.0),  # 2
        _ctx(cash=10_000.0, position=0.0),  # 3
        _ctx(cash=10_000.0, position=0.0),  # 4 — buy fires
        _ctx(cash=0.0, position=100.0),     # 5 — long, no signal change
        _ctx(cash=0.0, position=100.0),     # 6 — down cross, sell
    ]
    out = [strat.on_bar(_bar(i, p), c) for i, (p, c) in enumerate(zip(prices, contexts))]
    assert out[4][0].side == "buy"
    assert out[5] == []
    assert len(out[6]) == 1
    assert out[6][0].side == "sell"
    assert out[6][0].quantity == pytest.approx(100.0)  # liquidate full position


def test_ma_crossover_no_sell_when_flat() -> None:
    strat = MACrossover(fast_window=2, slow_window=4)
    # Bars where fast eventually crosses below slow, but we never bought.
    prices = [100.0, 100.0, 100.0, 100.0, 80.0]
    out = [strat.on_bar(_bar(i, p), _ctx(cash=10_000.0, position=0.0)) for i, p in enumerate(prices)]
    # Down-cross with no position → no sell intent.
    assert out[4] == []


def test_ma_crossover_validation() -> None:
    with pytest.raises(ValueError):
        MACrossover(fast_window=10, slow_window=10)
    with pytest.raises(ValueError):
        MACrossover(fast_window=30, slow_window=10)
    with pytest.raises(ValueError):
        MACrossover(fast_window=0, slow_window=10)
    with pytest.raises(ValueError):
        MACrossover(fast_window=2, slow_window=4, allocation_pct=2.0)
