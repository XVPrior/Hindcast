"""Smoke test: can we reach Binance and pull a few candles?

Two non-obvious things:
- ccxt.binance sets session.trust_env=False, so HTTPS_PROXY env vars are
  ignored. Read the proxy from .env and pass it to ccxt explicitly.
- Default load_markets() fans out to spot + USD-M + COIN-M + options
  exchangeInfo (~60MB total). On a shared proxy egress IP that easily
  trips Binance's 418 rate-limit ban. We only care about spot here.
"""

import os

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

    exchange = ccxt.binance(config)
    print(f"CCXT version: {ccxt.__version__}")
    print(f"Exchange: {exchange.name}")
    print(f"Proxy: {proxy or '(direct)'}")

    bars = exchange.fetch_ohlcv("BTC/USDT", timeframe="1h", limit=10)

    print(f"\nGot {len(bars)} bars:")
    for ts_ms, o, h, l, c, v in bars:
        print(f"  ts={ts_ms}  o={o}  h={h}  l={l}  c={c}  v={v:.2f}")


if __name__ == "__main__":
    main()
