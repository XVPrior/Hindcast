"""Validate Binance testnet credentials end-to-end.

Default: read-only — fetch server time and balances, print a summary.
With --place-order: place a tiny market round-trip (BUY then SELL of
0.001 BTC) to confirm the write path is functional.

Use:
    uv run python scripts/testnet_check.py
    uv run python scripts/testnet_check.py --place-order
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from dotenv import load_dotenv
from rich.console import Console

load_dotenv()

import ccxt  # noqa: E402

from hindcast.config import settings  # noqa: E402
from hindcast.exec.binance_client import (  # noqa: E402
    TestnetCredentialsMissing,
    make_binance_testnet,
)

console = Console()

ROUND_TRIP_QTY = 0.001  # BTC; ~$50–100 notional, well above min_notional
ROUND_TRIP_SYMBOL = "BTC/USDT"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--place-order",
        action="store_true",
        help="Place a tiny market BUY+SELL round-trip on the testnet.",
    )
    args = parser.parse_args()

    # ----- credentials -----
    if not settings.has_testnet_creds:
        console.print("[red]Testnet credentials missing.[/red]")
        console.print("Add BINANCE_TESTNET_API_KEY and BINANCE_TESTNET_API_SECRET to research/.env")
        return 1
    console.print(f"[dim]API key fingerprint: {settings.testnet_key_fingerprint()}[/dim]")

    # ----- connect -----
    try:
        ex = make_binance_testnet()
    except TestnetCredentialsMissing as e:
        console.print(f"[red]{e}[/red]")
        return 1

    # ----- read-only checks -----
    try:
        server_ms = ex.fetch_time()
    except Exception as e:
        console.print(f"[red]fetch_time failed: {type(e).__name__}: {e}[/red]")
        return 2
    server_dt = datetime.fromtimestamp(server_ms / 1000, tz=timezone.utc)
    drift = (datetime.now(tz=timezone.utc) - server_dt).total_seconds()
    console.print(f"[green]✓ testnet reachable[/green] — server time {server_dt.isoformat()} (drift {drift:+.2f}s)")

    try:
        balance = ex.fetch_balance()
    except ccxt.AuthenticationError as e:
        console.print(f"[red]Auth failed: {e}[/red]")
        return 3
    except Exception as e:
        console.print(f"[red]fetch_balance failed: {type(e).__name__}: {e}[/red]")
        return 3

    # Show only non-zero balances
    nonzero = {
        asset: amt for asset, amt in balance.get("total", {}).items()
        if isinstance(amt, (int, float)) and amt > 0
    }
    if nonzero:
        console.print("[green]✓ balances:[/green]")
        for asset, amt in sorted(nonzero.items()):
            console.print(f"    {asset}: {amt:.8f}".rstrip("0").rstrip("."))
    else:
        console.print("[yellow]No non-zero balances on testnet.[/yellow]")

    if not args.place_order:
        console.print("\n[dim]Skipping order test. Re-run with --place-order to verify the write path.[/dim]")
        return 0

    # ----- write path: tiny round-trip -----
    console.rule("[bold yellow]Placing round-trip order")
    console.print(f"BUY  {ROUND_TRIP_QTY} {ROUND_TRIP_SYMBOL} @ market")
    try:
        buy = ex.create_market_buy_order(ROUND_TRIP_SYMBOL, ROUND_TRIP_QTY)
    except Exception as e:
        console.print(f"[red]BUY failed: {type(e).__name__}: {e}[/red]")
        return 4
    console.print(
        f"  filled qty={buy.get('filled')} avg_px={buy.get('average')} "
        f"cost={buy.get('cost')} status={buy.get('status')}"
    )

    console.print(f"SELL {ROUND_TRIP_QTY} {ROUND_TRIP_SYMBOL} @ market (flatten)")
    try:
        sell = ex.create_market_sell_order(ROUND_TRIP_SYMBOL, ROUND_TRIP_QTY)
    except Exception as e:
        console.print(f"[red]SELL failed: {type(e).__name__}: {e}[/red]")
        console.print("[red]Position may be open — check testnet UI.[/red]")
        return 5
    console.print(
        f"  filled qty={sell.get('filled')} avg_px={sell.get('average')} "
        f"cost={sell.get('cost')} status={sell.get('status')}"
    )

    pnl = float(sell.get("cost", 0)) - float(buy.get("cost", 0))
    console.print(f"\n[bold]Round-trip PnL (testnet, fake money):[/bold] ${pnl:+.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
