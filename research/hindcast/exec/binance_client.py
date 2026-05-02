"""Factory for a ccxt.binance client wired to the SPOT TESTNET.

This is the only place in the codebase that constructs an authenticated
exchange client. Credentials are pulled from `settings`; nothing else
needs to know about them.

set_sandbox_mode(True) swaps the base URLs over to testnet.binance.vision
— mainnet endpoints are not reachable on a client built here.
"""

from __future__ import annotations

import ccxt

from hindcast.config import settings


class TestnetCredentialsMissing(RuntimeError):
    pass


def make_binance_testnet() -> ccxt.binance:
    """Return a ccxt.binance client locked to spot testnet.

    Raises TestnetCredentialsMissing if API key/secret aren't configured.
    """
    if not settings.has_testnet_creds:
        raise TestnetCredentialsMissing(
            "BINANCE_TESTNET_API_KEY and/or BINANCE_TESTNET_API_SECRET not set "
            "(check research/.env)"
        )

    config: dict = {
        "apiKey": settings.binance_testnet_api_key,
        "secret": settings.binance_testnet_api_secret,
        "enableRateLimit": True,
        # Spot-only avoids the multi-market-type load_markets fan-out that
        # we hit in M1 — see scripts/smoke_ccxt.py for the original story.
        "options": {"defaultType": "spot", "fetchMarkets": ["spot"]},
    }
    if settings.proxy:
        config["proxies"] = {"http": settings.proxy, "https": settings.proxy}

    ex = ccxt.binance(config)
    ex.set_sandbox_mode(True)  # → https://testnet.binance.vision
    return ex
