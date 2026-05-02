"""Live trading loop. Mirrors BacktestEngine semantics in real time.

Loop, per timeframe interval:
  1. Sleep until the next bar boundary + a few seconds buffer
  2. Fetch the latest closed bar from the exchange
  3. If it's new (timestamp > last processed):
     a. Settle any pending intents (sent now ≈ next-bar-open execution)
     b. Refresh cash/position from testnet
     c. mark_to_market → persist equity snapshot
     d. Call strategy.on_bar(bar, context) → collect new pending intents
     e. Persist audit log

Two safety properties:
  - dry_run defaults True; --live must be opt-in to actually send orders
  - SIGINT handler stops the loop cleanly between iterations
"""

from __future__ import annotations

import json
import signal
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import ccxt
from rich.console import Console

from hindcast.backtest.strategy import Strategy, StrategyContext
from hindcast.backtest.types import Bar, OrderIntent
from hindcast.data.fetcher import TIMEFRAME_MS
from hindcast.data.storage import Storage

console = Console()

# Wait this many seconds past the bar boundary before fetching, so the
# exchange has a chance to finalise the bar.
BAR_SETTLE_BUFFER_SEC = 5


@dataclass
class LiveSummary:
    run_id: str
    bars_processed: int
    intents_emitted: int
    orders_sent: int
    orders_skipped: int
    orders_errored: int


class LiveEngine:
    def __init__(
        self,
        strategy: Strategy,
        client: ccxt.Exchange,
        symbol: str,
        timeframe: str,
        storage: Storage,
        *,
        strategy_label: str,
        params: dict[str, Any] | None = None,
        dry_run: bool = True,
    ) -> None:
        if timeframe not in TIMEFRAME_MS:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        self.strategy = strategy
        self.client = client
        self.symbol = symbol
        self.timeframe = timeframe
        self.storage = storage
        self.strategy_label = strategy_label
        self.params = params or {}
        self.dry_run = dry_run

        self._stop = False
        self._pending: list[OrderIntent] = []
        self._history: list[Bar] = []
        self._last_processed_ts: datetime | None = None
        self.run_id = str(uuid.uuid4())

        # Counters for the final summary
        self._n_bars = 0
        self._n_intents = 0
        self._n_sent = 0
        self._n_skipped = 0
        self._n_errored = 0

    # ---------- public ----------

    def run(self) -> LiveSummary:
        self._install_signal_handler()
        self._record_start()

        mode = "[red]LIVE[/red]" if not self.dry_run else "[yellow]dry-run[/yellow]"
        console.print(
            f"[bold]LiveEngine started[/bold]  mode={mode}  "
            f"strategy={self.strategy_label}  symbol={self.symbol}  tf={self.timeframe}"
        )
        console.print(f"[dim]run_id: {self.run_id}[/dim]")
        if self.dry_run:
            console.print("[yellow]dry-run: intents will be logged but no orders will be placed[/yellow]")
        console.print("[dim]Ctrl-C to stop cleanly between iterations[/dim]\n")

        try:
            while not self._stop:
                self._sleep_until_next_bar()
                if self._stop:
                    break
                self._tick()
        finally:
            self._record_end()

        summary = LiveSummary(
            run_id=self.run_id,
            bars_processed=self._n_bars,
            intents_emitted=self._n_intents,
            orders_sent=self._n_sent,
            orders_skipped=self._n_skipped,
            orders_errored=self._n_errored,
        )
        self._print_summary(summary)
        return summary

    # ---------- one iteration ----------

    def _tick(self) -> None:
        bars = self._fetch_recent_bars(limit=3)
        new_bars = [b for b in bars if self._is_new(b)]
        if not new_bars:
            return

        for bar in new_bars:
            # 1. Settle pending intents from the previous bar
            for intent in self._pending:
                self._execute_intent(intent)
            self._pending = []

            # 2. Refresh state, mark-to-market
            cash, position = self._fetch_account_state()
            equity = cash + position * bar.close
            self.storage.record_live_equity(
                self.run_id, bar.timestamp, cash, position, bar.close, equity,
            )

            # 3. Ask the strategy
            ctx = StrategyContext(
                current_cash=cash,
                current_position=position,
                current_equity=equity,
                history=list(self._history),
            )
            try:
                new_intents = self.strategy.on_bar(bar, ctx)
            except Exception as e:
                console.print(f"[red]strategy raised: {type(e).__name__}: {e}[/red]")
                new_intents = []

            self._pending.extend(new_intents)
            self._n_intents += len(new_intents)
            self._history.append(bar)
            self._last_processed_ts = bar.timestamp
            self._n_bars += 1

            # log the bar
            console.print(
                f"[dim]{bar.timestamp.isoformat()}[/dim]  close={bar.close:.2f}  "
                f"cash={cash:.2f}  pos={position:.6f}  equity={equity:.2f}  "
                f"new_intents={len(new_intents)}"
            )

    # ---------- exchange I/O ----------

    def _fetch_recent_bars(self, limit: int = 3) -> list[Bar]:
        try:
            raw = self.client.fetch_ohlcv(
                self.symbol, timeframe=self.timeframe, limit=limit,
            )
        except Exception as e:
            console.print(f"[yellow]fetch_ohlcv failed: {type(e).__name__}: {e}[/yellow]")
            return []

        # Drop the last bar — it may still be the in-progress current minute.
        # We only act on closed bars.
        if len(raw) >= 2:
            raw = raw[:-1]

        return [
            Bar(
                timestamp=datetime.fromtimestamp(r[0] / 1000, tz=timezone.utc),
                open=float(r[1]), high=float(r[2]), low=float(r[3]),
                close=float(r[4]), volume=float(r[5]),
            )
            for r in raw
        ]

    def _fetch_account_state(self) -> tuple[float, float]:
        """Return (USDT cash, base-asset position) for self.symbol."""
        base, quote = self.symbol.split("/")
        try:
            balance = self.client.fetch_balance()
        except Exception as e:
            console.print(f"[yellow]fetch_balance failed, reusing zeros: {e}[/yellow]")
            return 0.0, 0.0
        cash = float(balance.get("total", {}).get(quote, 0.0))
        position = float(balance.get("total", {}).get(base, 0.0))
        return cash, position

    def _execute_intent(self, intent: OrderIntent) -> None:
        submit_ts = datetime.now(tz=timezone.utc)

        if self.dry_run:
            self.storage.record_live_order(
                self.run_id, intent.bar_timestamp, submit_ts,
                intent.side, intent.quantity,
                status="skipped_dryrun",
            )
            self._n_skipped += 1
            console.print(
                f"  [yellow]dry-run skip[/yellow]: {intent.side} {intent.quantity} {self.symbol}"
            )
            return

        try:
            if intent.side == "buy":
                order = self.client.create_market_buy_order(self.symbol, intent.quantity)
            else:
                order = self.client.create_market_sell_order(self.symbol, intent.quantity)
        except Exception as e:
            self.storage.record_live_order(
                self.run_id, intent.bar_timestamp, submit_ts,
                intent.side, intent.quantity,
                status="error",
                error_message=f"{type(e).__name__}: {e}",
            )
            self._n_errored += 1
            console.print(f"  [red]order failed[/red]: {type(e).__name__}: {e}")
            return

        order_id = self.storage.record_live_order(
            self.run_id, intent.bar_timestamp, submit_ts,
            intent.side, intent.quantity,
            status="filled",
            exchange_id=str(order.get("id")),
        )
        # CCXT may return aggregated trades or just a single summary. Trade
        # dicts can also have None for timestamp / amount / price (binance
        # spot regularly omits these). Fall back to order-level fields and
        # submit_ts in that case so we always log *something*.
        trades = order.get("trades") or []
        if trades:
            for t in trades:
                ts_ms = t.get("timestamp")
                fill_ts = (
                    datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
                    if isinstance(ts_ms, (int, float))
                    else submit_ts
                )
                fee_dict = t.get("fee") or {}
                self.storage.record_live_fill(
                    self.run_id, order_id,
                    fill_ts=fill_ts,
                    side=intent.side,
                    quantity=float(t.get("amount") or 0.0),
                    price=float(t.get("price") or 0.0),
                    fee=float(fee_dict.get("cost") or 0.0),
                    fee_currency=fee_dict.get("currency"),
                )
        else:
            self.storage.record_live_fill(
                self.run_id, order_id,
                fill_ts=submit_ts,
                side=intent.side,
                quantity=float(order.get("filled") or 0.0),
                price=float(order.get("average") or 0.0),
                fee=0.0,
            )
        self._n_sent += 1
        console.print(
            f"  [green]order filled[/green]: {intent.side} {order.get('filled')} @ {order.get('average')}"
        )

    # ---------- helpers ----------

    def _is_new(self, bar: Bar) -> bool:
        return self._last_processed_ts is None or bar.timestamp > self._last_processed_ts

    def _sleep_until_next_bar(self) -> None:
        interval_sec = TIMEFRAME_MS[self.timeframe] / 1000
        now = datetime.now(tz=timezone.utc).timestamp()
        seconds_into = now % interval_sec
        sleep_for = max(0.0, interval_sec - seconds_into + BAR_SETTLE_BUFFER_SEC)
        # Sleep in 1s slices so SIGINT response stays under 1s.
        end = time.time() + sleep_for
        while time.time() < end and not self._stop:
            time.sleep(min(1.0, end - time.time()))

    def _install_signal_handler(self) -> None:
        def _handler(signum: int, frame) -> None:  # noqa: ARG001
            console.print(
                "\n[yellow]SIGINT received — finishing current iteration then stopping[/yellow]"
            )
            self._stop = True
        signal.signal(signal.SIGINT, _handler)

    def _record_start(self) -> None:
        self.storage.start_live_run(
            run_id=self.run_id,
            started_at=datetime.now(tz=timezone.utc),
            strategy=self.strategy_label,
            symbol=self.symbol,
            timeframe=self.timeframe,
            dry_run=self.dry_run,
            params=json.dumps(self.params, default=str) if self.params else None,
        )

    def _record_end(self) -> None:
        try:
            self.storage.end_live_run(self.run_id, datetime.now(tz=timezone.utc))
        except Exception as e:
            console.print(f"[yellow]could not mark run ended: {e}[/yellow]")

    def _print_summary(self, s: LiveSummary) -> None:
        console.rule("[bold green]Live session ended")
        console.print(f"run_id          {s.run_id}")
        console.print(f"bars processed  {s.bars_processed}")
        console.print(f"intents emitted {s.intents_emitted}")
        console.print(f"orders sent     {s.orders_sent}")
        console.print(f"orders skipped  {s.orders_skipped}  (dry-run)")
        console.print(f"orders errored  {s.orders_errored}")
