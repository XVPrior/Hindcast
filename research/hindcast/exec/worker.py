"""Long-running multi-strategy supervisor for cloud deploy.

Spawns N LiveEngine instances in parallel threads against the same
shared DuckDB. Each engine is dry-run by default — no testnet orders
sent — but the virtual portfolios evolve as if filled, producing real
out-of-sample equity curves to compare against M3 backtest predictions.

Started by Fly's [processes.worker] entry: `python -m hindcast.exec.worker`
"""

from __future__ import annotations

import json
import os
import signal
import threading
import time
from typing import Any

from rich.console import Console

from hindcast.backtest.strategies.bollinger_meanrev import BollingerMeanReversion
from hindcast.backtest.strategies.buy_and_hold import BuyAndHold
from hindcast.backtest.strategies.ma_crossover import MACrossover
from hindcast.config import settings
from hindcast.data.storage import Storage
from hindcast.exec.binance_client import make_binance_testnet
from hindcast.exec.live_engine import LiveEngine

console = Console()


# Default forward-test config — 5 strategies on BTC/USDT 1h, all dry-run.
# Override by exporting WORKER_STRATEGIES as a JSON array of the same shape.
DEFAULT_STRATEGIES: list[dict[str, Any]] = [
    {
        "type": "buy_and_hold",
        "label": "buy_and_hold (forward)",
        "symbol": "BTC/USDT",
        "timeframe": "1h",
        "params": {"allocation_pct": 0.99},
    },
    {
        "type": "ma_crossover",
        "label": "ma_crossover (10/30) [M3-E2 best]",
        "symbol": "BTC/USDT",
        "timeframe": "1h",
        "params": {"fast_window": 10, "slow_window": 30, "allocation_pct": 0.99},
    },
    {
        "type": "ma_crossover",
        "label": "ma_crossover (5/20)",
        "symbol": "BTC/USDT",
        "timeframe": "1h",
        "params": {"fast_window": 5, "slow_window": 20, "allocation_pct": 0.99},
    },
    {
        "type": "bollinger_meanrev",
        "label": "bollinger (20, 2.0) [M3-E3 best]",
        "symbol": "BTC/USDT",
        "timeframe": "1h",
        "params": {"window": 20, "n_std": 2.0, "allocation_pct": 0.99},
    },
    {
        "type": "bollinger_meanrev",
        "label": "bollinger (10, 1.5) [aggressive]",
        "symbol": "BTC/USDT",
        "timeframe": "1h",
        "params": {"window": 10, "n_std": 1.5, "allocation_pct": 0.99},
    },
]

INITIAL_CASH = 10_000.0


def _load_strategy_config() -> list[dict[str, Any]]:
    raw = os.environ.get("WORKER_STRATEGIES")
    if not raw:
        return DEFAULT_STRATEGIES
    try:
        return json.loads(raw)
    except Exception as e:
        console.print(f"[red]WORKER_STRATEGIES is not valid JSON ({e}); using defaults[/red]")
        return DEFAULT_STRATEGIES


def _make_strategy(spec: dict[str, Any]):
    t = spec["type"]
    p = spec["params"]
    if t == "buy_and_hold":
        return BuyAndHold(allocation_pct=p["allocation_pct"])
    if t == "ma_crossover":
        return MACrossover(
            fast_window=p["fast_window"],
            slow_window=p["slow_window"],
            allocation_pct=p["allocation_pct"],
        )
    if t == "bollinger_meanrev":
        return BollingerMeanReversion(
            window=p["window"],
            n_std=p["n_std"],
            allocation_pct=p["allocation_pct"],
        )
    raise ValueError(f"Unknown strategy type: {t}")


def _make_engine(spec: dict[str, Any]) -> LiveEngine:
    storage = Storage(settings.db_path)
    client = make_binance_testnet()
    return LiveEngine(
        strategy=_make_strategy(spec),
        client=client,
        symbol=spec["symbol"],
        timeframe=spec["timeframe"],
        storage=storage,
        strategy_label=spec["label"],
        params={**spec["params"], "initial_cash": INITIAL_CASH},
        dry_run=True,
        initial_cash=INITIAL_CASH,
    )


def main() -> int:
    specs = _load_strategy_config()
    console.print(f"[bold]worker starting {len(specs)} engines[/bold]")
    console.print(f"[dim]db: {settings.db_path}[/dim]")
    console.print(f"[dim]testnet creds: {settings.testnet_key_fingerprint()}[/dim]\n")

    # Pre-create engines so the SIGINT handler can address all of them
    # without races against thread startup.
    engines: list[LiveEngine] = []
    for spec in specs:
        try:
            engines.append(_make_engine(spec))
            console.print(f"  ✓ {spec['label']}")
        except Exception as e:
            console.print(f"  [red]✗ {spec['label']}: {e}[/red]")

    if not engines:
        console.print("[red]no engines successfully constructed; exiting[/red]")
        return 1

    # SIGINT (or SIGTERM from Fly) → flag all engines to stop on next tick.
    # When the worker runs as a daemon thread under the API process (cloud
    # deploy), signal.signal raises ValueError because Python only allows
    # signal handlers from the main thread. The API's main thread already
    # owns SIGTERM and will tear down the whole process; daemon threads
    # exit with it, so skipping handler installation is safe there.
    def stop_all(signum: int, frame) -> None:  # noqa: ARG001
        console.print(f"\n[yellow]signal {signum} — stopping {len(engines)} engines[/yellow]")
        for e in engines:
            e._stop = True

    try:
        signal.signal(signal.SIGINT, stop_all)
        signal.signal(signal.SIGTERM, stop_all)
    except ValueError:
        console.print(
            "[dim]worker is not on the main thread — relying on parent process for signal handling[/dim]"
        )

    # Run each engine in its own thread. Engines do their own audit-log
    # writes; DuckDB allows multiple connections within one Python process,
    # so threads serialise cleanly through the shared file.
    threads: list[threading.Thread] = []
    for engine in engines:
        t = threading.Thread(
            target=lambda e=engine: e.run(install_signal_handler=False),
            name=engine.strategy_label,
            daemon=False,
        )
        t.start()
        threads.append(t)
        # Stagger starts slightly so initial DB writes don't all collide.
        time.sleep(0.5)

    for t in threads:
        t.join()

    console.print("[green]all engines exited cleanly[/green]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
