"""Probe Binance endpoints we'll rely on later.

Spot-only on purpose — see smoke_ccxt.py for why fanning out to all market
types trips the rate-limit ban.
"""

import os
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

import ccxt


def main() -> None:
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    config: dict = {
        "enableRateLimit": True,
        "options": {"defaultType": "spot", "fetchMarkets": ["spot"]},
    }
    if proxy:
        config["proxies"] = {"http": proxy, "https": proxy}

    ex = ccxt.binance(config)
    print(f"Proxy: {proxy or '(direct)'}\n")

    print("=== Server time ===")
    server_time_ms = ex.fetch_time()
    server_time = datetime.fromtimestamp(server_time_ms / 1000, tz=timezone.utc)
    local_time = datetime.now(timezone.utc)
    drift_sec = (local_time - server_time).total_seconds()
    print(f"  Binance: {server_time}")
    print(f"  Local:   {local_time}")
    print(f"  Drift:   {drift_sec:.2f}s")

    print("\n=== Recent BTC/USDT 1h candles ===")
    bars = ex.fetch_ohlcv("BTC/USDT", timeframe="1h", limit=5)
    for ts_ms, _o, _h, _l, c, v in bars:
        ts = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
        print(f"  {ts} | close={c} vol={v:.0f}")

    print("\n=== Historical (since 2024-01-01) ===")
    since_ms = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    bars = ex.fetch_ohlcv("BTC/USDT", timeframe="1d", since=since_ms, limit=5)
    for ts_ms, _o, _h, _l, c, _v in bars:
        ts = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
        print(f"  {ts} | close={c}")

    print("\n=== Market summary ===")
    markets = ex.load_markets()
    spot_pairs = [s for s, m in markets.items() if m.get("type") == "spot"]
    print(f"  Total markets: {len(markets)}")
    print(f"  Spot pairs:    {len(spot_pairs)}")
    print(f"  First 5 spot:  {spot_pairs[:5]}")

    print("\nAll probes passed.")


if __name__ == "__main__":
    main()
