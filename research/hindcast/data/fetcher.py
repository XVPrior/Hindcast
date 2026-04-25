"""Fetch OHLCV from exchanges with auto-pagination, retries, and progress.

Design notes:
- One Fetcher == one exchange. Don't reuse instances across exchanges.
- All times are UTC milliseconds internally. We only convert to datetime at
  the boundary (when building DataFrames or printing).
- We never silently skip data. If a chunk fails after all retries, we raise.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import ccxt
import pandas as pd
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

console = Console()


# Milliseconds per bar for each timeframe.
# Used to advance the pagination cursor.
TIMEFRAME_MS: dict[str, int] = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
}


class FetchError(RuntimeError):
    """Raised when fetching fails after all retries."""


class Fetcher:
    """Pulls OHLCV bars from a single exchange with pagination + retries."""

    def __init__(
        self,
        exchange_name: str = "binance",
        proxy: str | None = None,
        max_retries: int = 5,
        extra_config: dict | None = None,
    ) -> None:
        self.exchange_name = exchange_name
        self.max_retries = max_retries

        klass = getattr(ccxt, exchange_name, None)
        if klass is None:
            raise ValueError(f"Unknown exchange: {exchange_name}")

        config: dict = {"enableRateLimit": True}
        if proxy:
            config["proxies"] = {"http": proxy, "https": proxy}
        if extra_config:
            config.update(extra_config)

        self.exchange = klass(config)

    # ---------- public API ----------

    def fetch_range(
        self,
        symbol: str,
        timeframe: str,
        since: datetime | int,
        until: datetime | int | None = None,
        chunk_size: int = 1000,
    ) -> pd.DataFrame:
        """Fetch all OHLCV bars in [since, until).

        Args:
            symbol:    e.g. "BTC/USDT"
            timeframe: must be in TIMEFRAME_MS
            since:     UTC datetime or millisecond int
            until:     UTC datetime or millisecond int. None means "now".
            chunk_size: bars per request (Binance max = 1000)

        Returns:
            DataFrame with the canonical schema:
            [exchange, symbol, timeframe, timestamp, open, high, low, close, volume]
        """
        if timeframe not in TIMEFRAME_MS:
            raise ValueError(
                f"Unsupported timeframe: {timeframe}. "
                f"Known: {list(TIMEFRAME_MS)}"
            )

        since_ms = self._to_ms(since)
        until_ms = self._to_ms(until) if until is not None else _now_ms()
        step_ms = TIMEFRAME_MS[timeframe]

        if since_ms >= until_ms:
            return _empty_frame()

        all_bars: list[list] = []
        cursor = since_ms

        total_estimate = max(1, (until_ms - since_ms) // step_ms)

        with Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total} bars"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"Fetching {symbol} {timeframe}",
                total=total_estimate,
            )

            while cursor < until_ms:
                bars = self._fetch_chunk_with_retry(
                    symbol, timeframe, since_ms=cursor, limit=chunk_size
                )

                if not bars:
                    break

                bars = [b for b in bars if b[0] < until_ms]
                if not bars:
                    break

                all_bars.extend(bars)
                progress.update(task, completed=len(all_bars))

                last_ts = bars[-1][0]
                cursor = last_ts + step_ms

                if len(bars) < chunk_size:
                    break

                self._sleep_for_rate_limit()

            progress.update(task, completed=len(all_bars))

        return self._to_dataframe(all_bars, symbol, timeframe)

    # ---------- internals ----------

    def _fetch_chunk_with_retry(
        self, symbol: str, timeframe: str, since_ms: int, limit: int
    ) -> list[list]:
        """Single page fetch with exponential backoff."""
        last_err: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                return self.exchange.fetch_ohlcv(
                    symbol, timeframe=timeframe, since=since_ms, limit=limit
                )
            except ccxt.RateLimitExceeded as e:
                last_err = e
                wait = 2**attempt
                console.print(
                    f"[yellow]Rate limited (attempt {attempt}), "
                    f"sleeping {wait}s[/yellow]"
                )
                time.sleep(wait)
            except (ccxt.NetworkError, ccxt.ExchangeNotAvailable) as e:
                last_err = e
                wait = 2**attempt
                console.print(
                    f"[yellow]Network error: {e} (attempt {attempt}), "
                    f"retrying in {wait}s[/yellow]"
                )
                time.sleep(wait)
            except ccxt.BaseError as e:
                # Other CCXT errors (bad symbol, auth, etc.) — don't retry.
                raise FetchError(f"Unrecoverable: {e}") from e

        raise FetchError(
            f"Failed after {self.max_retries} retries. Last error: {last_err}"
        )

    def _sleep_for_rate_limit(self) -> None:
        """CCXT exposes the recommended interval as `rateLimit` in ms."""
        time.sleep(self.exchange.rateLimit / 1000)

    def _to_dataframe(
        self, bars: list[list], symbol: str, timeframe: str
    ) -> pd.DataFrame:
        if not bars:
            return _empty_frame()

        df = pd.DataFrame(
            bars,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df["exchange"] = self.exchange_name
        df["symbol"] = symbol
        df["timeframe"] = timeframe

        # Some exchanges treat `since` as inclusive, producing one bar of
        # overlap between consecutive pages. Dedupe on timestamp.
        df = df.drop_duplicates(subset=["timestamp"]).reset_index(drop=True)

        return df[[
            "exchange", "symbol", "timeframe", "timestamp",
            "open", "high", "low", "close", "volume",
        ]]

    @staticmethod
    def _to_ms(value: datetime | int) -> int:
        if isinstance(value, int):
            return value
        if value.tzinfo is None:
            raise ValueError(
                "datetime must be timezone-aware (use timezone.utc)"
            )
        return int(value.timestamp() * 1000)


# ---------- helpers ----------

def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "exchange", "symbol", "timeframe", "timestamp",
            "open", "high", "low", "close", "volume",
        ]
    )


def _now_ms() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp() * 1000)
