"""Live trading loop. Mirrors BacktestEngine semantics in real time.

Strategy state in this engine is its OWN — we maintain a virtual Portfolio
(cash + position) starting from `initial_cash` rather than reading the
testnet balance. Reasons:

  - The strategy code (e.g. MA crossover's `if position == 0: buy`) was
    written assuming a flat-start portfolio. If we feed it the account's
    actual BTC balance, every bar looks like an existing position and the
    strategy can't enter.
  - Multiple strategies can share one account without interfering — each
    gets its own slice of virtual cash.
  - Backtest and live now use the SAME Portfolio class, ExecutionModel,
    StrategyContext. A backtest-validated strategy plug-and-plays here.
  - Dry-run sessions get a real simulated equity curve (executed against
    bar.open with configured slippage/fee), so they're backtest-equivalent
    on real-time data.

Real testnet orders still go out in --live mode and we record the actual
exchange fill price/qty into the audit log (and apply that to the virtual
portfolio so it tracks what really happened, not what we estimated).
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

from hindcast.backtest.execution import SimpleExecutionModel
from hindcast.backtest.portfolio import Portfolio
from hindcast.backtest.strategy import Strategy, StrategyContext
from hindcast.backtest.types import Bar, Fill, OrderIntent
from hindcast.data.fetcher import TIMEFRAME_MS
from hindcast.data.storage import Storage

console = Console()

BAR_SETTLE_BUFFER_SEC = 5


@dataclass
class LiveSummary:
    run_id: str
    bars_processed: int
    intents_emitted: int
    orders_sent: int       # real testnet fills
    orders_simulated: int  # dry-run fills applied to virtual portfolio
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
        initial_cash: float = 10_000.0,
        fee_pct: float = 0.001,
        slippage_pct: float = 0.0005,
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

        # Virtual portfolio — strategy state, decoupled from testnet balance
        self.portfolio = Portfolio(initial_cash=initial_cash)
        self.execution_model = SimpleExecutionModel(
            fee_pct=fee_pct, slippage_pct=slippage_pct,
        )

        self._stop = False
        self._pending: list[OrderIntent] = []
        self._history: list[Bar] = []
        self._last_processed_ts: datetime | None = None
        self.run_id = str(uuid.uuid4())

        self._n_bars = 0
        self._n_intents = 0
        self._n_simulated = 0
        self._n_sent = 0
        self._n_errored = 0

    # ---------- public ----------

    def run(self) -> LiveSummary:
        self._install_signal_handler()
        n_swept = self.storage.sweep_stale_runs(max_idle_seconds=300)
        if n_swept:
            console.print(
                f"[dim]Swept {n_swept} stale active run(s) — marked as crashed.[/dim]"
            )
        self._record_start()

        mode = "[red]LIVE[/red]" if not self.dry_run else "[yellow]dry-run[/yellow]"
        console.print(
            f"[bold]LiveEngine started[/bold]  mode={mode}  "
            f"strategy={self.strategy_label}  symbol={self.symbol}  tf={self.timeframe}"
        )
        console.print(
            f"[dim]virtual portfolio: cash=${self.portfolio.cash:.2f}, position=0  "
            f"(testnet account state is NOT mirrored — strategy starts flat)[/dim]"
        )
        console.print(f"[dim]run_id: {self.run_id}[/dim]")
        if self.dry_run:
            console.print(
                "[yellow]dry-run: orders are simulated against bar.open with configured "
                "fee/slippage; no testnet orders sent[/yellow]"
            )
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
            orders_simulated=self._n_simulated,
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
                self._execute_intent(intent, bar)
            self._pending = []

            # 2. Mark-to-market virtual portfolio (NOT testnet balance)
            self.portfolio.mark_to_market(bar)
            eq_pt = self.portfolio.equity_history[-1]
            self.storage.record_live_equity(
                self.run_id, bar.timestamp,
                cash=eq_pt.cash, position=eq_pt.position,
                price=eq_pt.price, equity=eq_pt.equity,
            )

            # 3. Ask the strategy
            ctx = StrategyContext(
                current_cash=self.portfolio.cash,
                current_position=self.portfolio.position,
                current_equity=eq_pt.equity,
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

            console.print(
                f"[dim]{bar.timestamp.isoformat()}[/dim]  close={bar.close:.2f}  "
                f"v_cash={self.portfolio.cash:.2f}  v_pos={self.portfolio.position:.6f}  "
                f"v_equity={eq_pt.equity:.2f}  new_intents={len(new_intents)}"
            )

    # ---------- intent execution ----------

    def _execute_intent(self, intent: OrderIntent, current_bar: Bar) -> None:
        submit_ts = datetime.now(tz=timezone.utc)

        try:
            if self.dry_run:
                fill = self.execution_model.execute(intent, current_bar)
                exchange_id: str | None = None
                fee_currency: str | None = None
            else:
                fill, exchange_id, fee_currency = self._send_to_testnet(intent, submit_ts)
        except Exception as e:
            self.storage.record_live_order(
                self.run_id, intent.bar_timestamp, submit_ts,
                intent.side, intent.quantity,
                status="error",
                error_message=f"{type(e).__name__}: {e}",
            )
            self._n_errored += 1
            console.print(f"  [red]execute failed: {type(e).__name__}: {e}[/red]")
            return

        if not self.portfolio.can_afford(fill):
            # Strategy emitted an intent the virtual portfolio can't actually
            # absorb — usually means the strategy sized off stale state.
            self.storage.record_live_order(
                self.run_id, intent.bar_timestamp, submit_ts,
                intent.side, intent.quantity,
                status="error",
                error_message="virtual portfolio cannot afford fill",
                exchange_id=exchange_id,
            )
            self._n_errored += 1
            console.print(
                f"  [red]virtual portfolio rejected fill[/red]: "
                f"{intent.side} {fill.quantity} @ {fill.price:.2f}"
            )
            return

        self.portfolio.apply_fill(fill)

        status = "simulated" if self.dry_run else "filled"
        order_id = self.storage.record_live_order(
            self.run_id, intent.bar_timestamp, submit_ts,
            intent.side, intent.quantity,
            status=status,
            exchange_id=exchange_id,
        )
        self.storage.record_live_fill(
            self.run_id, order_id,
            fill_ts=fill.timestamp,
            side=intent.side,
            quantity=fill.quantity, price=fill.price,
            fee=fill.fee, fee_currency=fee_currency,
        )

        if self.dry_run:
            self._n_simulated += 1
            console.print(
                f"  [yellow]simulated[/yellow]: {intent.side} {fill.quantity:.6f} @ {fill.price:.2f}"
            )
        else:
            self._n_sent += 1
            console.print(
                f"  [green]filled on testnet[/green]: "
                f"{intent.side} {fill.quantity:.6f} @ {fill.price:.2f}"
            )

    def _send_to_testnet(
        self, intent: OrderIntent, submit_ts: datetime,
    ) -> tuple[Fill, str | None, str | None]:
        """Send a real market order, return (Fill, exchange_id, fee_currency)."""
        if intent.side == "buy":
            order = self.client.create_market_buy_order(self.symbol, intent.quantity)
        else:
            order = self.client.create_market_sell_order(self.symbol, intent.quantity)

        avg_px = float(order.get("average") or 0.0)
        filled = float(order.get("filled") or 0.0)
        # Sum trade-level fees if we got them; else 0 (binance testnet often
        # returns no fees on spot).
        fee_total = 0.0
        fee_currency: str | None = None
        for t in order.get("trades") or []:
            fee_dict = t.get("fee") or {}
            fee_total += float(fee_dict.get("cost") or 0.0)
            fee_currency = fee_dict.get("currency") or fee_currency

        fill = Fill(
            timestamp=submit_ts,
            side=intent.side,
            quantity=filled,
            price=avg_px,
            fee=fee_total,
            intent_timestamp=intent.bar_timestamp,
        )
        return fill, str(order.get("id")) if order.get("id") is not None else None, fee_currency

    # ---------- exchange I/O ----------

    def _fetch_recent_bars(self, limit: int = 3) -> list[Bar]:
        try:
            raw = self.client.fetch_ohlcv(
                self.symbol, timeframe=self.timeframe, limit=limit,
            )
        except Exception as e:
            console.print(f"[yellow]fetch_ohlcv failed: {type(e).__name__}: {e}[/yellow]")
            return []

        if len(raw) >= 2:
            raw = raw[:-1]  # drop the in-progress current bar

        return [
            Bar(
                timestamp=datetime.fromtimestamp(r[0] / 1000, tz=timezone.utc),
                open=float(r[1]), high=float(r[2]), low=float(r[3]),
                close=float(r[4]), volume=float(r[5]),
            )
            for r in raw
        ]

    # ---------- helpers ----------

    def _is_new(self, bar: Bar) -> bool:
        return self._last_processed_ts is None or bar.timestamp > self._last_processed_ts

    def _sleep_until_next_bar(self) -> None:
        interval_sec = TIMEFRAME_MS[self.timeframe] / 1000
        now = datetime.now(tz=timezone.utc).timestamp()
        seconds_into = now % interval_sec
        sleep_for = max(0.0, interval_sec - seconds_into + BAR_SETTLE_BUFFER_SEC)
        end = time.time() + sleep_for
        last_db_poll = 0.0
        while time.time() < end and not self._stop:
            time.sleep(min(1.0, end - time.time()))
            now_t = time.time()
            if now_t - last_db_poll >= 5.0:
                if self.storage.is_stop_requested(self.run_id):
                    console.print(
                        "[yellow]Stop requested via dashboard — exiting after this iteration[/yellow]"
                    )
                    self._stop = True
                last_db_poll = now_t

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
        console.print(f"run_id            {s.run_id}")
        console.print(f"bars processed    {s.bars_processed}")
        console.print(f"intents emitted   {s.intents_emitted}")
        console.print(f"orders sent       {s.orders_sent}  (real testnet fills)")
        console.print(f"orders simulated  {s.orders_simulated}  (dry-run virtual fills)")
        console.print(f"orders errored    {s.orders_errored}")
        console.print(
            f"final virtual:    cash=${self.portfolio.cash:.2f}, "
            f"position={self.portfolio.position:.6f}"
        )
        if self.portfolio.equity_history:
            initial = self.portfolio.equity_history[0].equity
            final = self.portfolio.equity_history[-1].equity
            console.print(
                f"session PnL:      ${final - initial:+.2f}  "
                f"({(final/initial - 1):+.2%} from initial cash)"
            )
