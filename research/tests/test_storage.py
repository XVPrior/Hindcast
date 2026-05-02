"""Tests for the storage layer."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from hindcast.data.storage import Storage


@pytest.fixture
def storage(tmp_path: Path) -> Storage:
    return Storage(tmp_path / "test.duckdb")


def make_df(n: int = 3, symbol: str = "BTC/USDT") -> pd.DataFrame:
    base = pd.Timestamp("2024-01-01", tz="UTC")
    return pd.DataFrame({
        "exchange": ["binance"] * n,
        "symbol": [symbol] * n,
        "timeframe": ["1h"] * n,
        "timestamp": [base + pd.Timedelta(hours=i) for i in range(n)],
        "open": [100.0 + i for i in range(n)],
        "high": [101.0 + i for i in range(n)],
        "low": [99.0 + i for i in range(n)],
        "close": [100.5 + i for i in range(n)],
        "volume": [10.0 + i for i in range(n)],
    })


def test_upsert_and_query_roundtrip(storage: Storage) -> None:
    df = make_df(5)
    n = storage.upsert_ohlcv(df)
    assert n == 5

    out = storage.query_ohlcv("binance", "BTC/USDT", "1h")
    assert len(out) == 5
    assert out["close"].tolist() == [100.5, 101.5, 102.5, 103.5, 104.5]


def test_upsert_is_idempotent(storage: Storage) -> None:
    df = make_df(3)
    storage.upsert_ohlcv(df)
    storage.upsert_ohlcv(df)
    assert storage.row_count() == 3


def test_upsert_overwrites_on_conflict(storage: Storage) -> None:
    df1 = make_df(3)
    storage.upsert_ohlcv(df1)

    df2 = df1.copy()
    df2["close"] = [999.0, 999.0, 999.0]
    storage.upsert_ohlcv(df2)

    out = storage.query_ohlcv("binance", "BTC/USDT", "1h")
    assert out["close"].tolist() == [999.0, 999.0, 999.0]
    assert len(out) == 3


def test_query_with_window(storage: Storage) -> None:
    df = make_df(10)
    storage.upsert_ohlcv(df)

    start = pd.Timestamp("2024-01-01 02:00", tz="UTC")
    end = pd.Timestamp("2024-01-01 05:00", tz="UTC")
    out = storage.query_ohlcv("binance", "BTC/USDT", "1h", start=start, end=end)

    assert len(out) == 3


def test_latest_timestamp(storage: Storage) -> None:
    assert storage.latest_timestamp("binance", "BTC/USDT", "1h") is None

    storage.upsert_ohlcv(make_df(5))
    latest = storage.latest_timestamp("binance", "BTC/USDT", "1h")
    assert latest == pd.Timestamp("2024-01-01 04:00", tz="UTC")


def test_latest_timestamp_unknown_market_with_other_data(storage: Storage) -> None:
    # Repro for the DuckDB 1.5.2 bug: MAX(TIMESTAMPTZ) with a WHERE filter
    # that matches no rows crashes when the table has rows for other filters.
    # ORDER BY ... LIMIT 1 avoids the bad codegen path.
    storage.upsert_ohlcv(make_df(3, symbol="BTC/USDT"))
    assert storage.latest_timestamp("binance", "ETH/USDT", "1h") is None


def test_multiple_symbols_isolated(storage: Storage) -> None:
    storage.upsert_ohlcv(make_df(3, symbol="BTC/USDT"))
    storage.upsert_ohlcv(make_df(3, symbol="ETH/USDT"))

    btc = storage.query_ohlcv("binance", "BTC/USDT", "1h")
    eth = storage.query_ohlcv("binance", "ETH/USDT", "1h")
    assert len(btc) == 3
    assert len(eth) == 3
    assert storage.row_count() == 6


def test_missing_column_raises(storage: Storage) -> None:
    df = make_df(3).drop(columns=["volume"])
    with pytest.raises(ValueError, match="missing columns"):
        storage.upsert_ohlcv(df)


# ---------- funding rate ----------


def make_funding_df(n: int = 3, symbol: str = "BTC/USDT:USDT") -> pd.DataFrame:
    base = pd.Timestamp("2024-01-01", tz="UTC")
    return pd.DataFrame({
        "exchange": ["binance"] * n,
        "symbol": [symbol] * n,
        # 8h spacing matches binance USDM funding cadence
        "timestamp": [base + pd.Timedelta(hours=8 * i) for i in range(n)],
        "rate": [0.0001 + i * 0.00001 for i in range(n)],
    })


def test_upsert_and_query_funding_roundtrip(storage: Storage) -> None:
    df = make_funding_df(5)
    n = storage.upsert_funding_rate(df)
    assert n == 5
    out = storage.query_funding_rate("binance", "BTC/USDT:USDT")
    assert len(out) == 5
    assert out["rate"].iloc[0] == pytest.approx(0.0001)


def test_funding_upsert_idempotent(storage: Storage) -> None:
    df = make_funding_df(4)
    storage.upsert_funding_rate(df)
    storage.upsert_funding_rate(df)
    out = storage.query_funding_rate("binance", "BTC/USDT:USDT")
    assert len(out) == 4


def test_latest_funding_timestamp(storage: Storage) -> None:
    assert storage.latest_funding_timestamp("binance", "BTC/USDT:USDT") is None
    storage.upsert_funding_rate(make_funding_df(3))
    latest = storage.latest_funding_timestamp("binance", "BTC/USDT:USDT")
    assert latest == pd.Timestamp("2024-01-01 16:00", tz="UTC")  # bar 0 + 16h


def test_funding_query_with_window(storage: Storage) -> None:
    storage.upsert_funding_rate(make_funding_df(10))
    start = pd.Timestamp("2024-01-01 16:00", tz="UTC")
    end = pd.Timestamp("2024-01-02 08:00", tz="UTC")
    out = storage.query_funding_rate("binance", "BTC/USDT:USDT", start=start, end=end)
    # 16:00 inclusive, 24:00 inclusive, 08:00 next-day exclusive → 2 rows
    assert len(out) == 2


def test_funding_missing_column_raises(storage: Storage) -> None:
    df = make_funding_df(2).drop(columns=["rate"])
    with pytest.raises(ValueError, match="missing columns"):
        storage.upsert_funding_rate(df)
