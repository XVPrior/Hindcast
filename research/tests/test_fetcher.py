"""Unit tests for fetcher's pure logic (no network)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from hindcast.data.fetcher import (
    TIMEFRAME_MS,
    Fetcher,
    _empty_frame,
)


def test_to_ms_with_datetime() -> None:
    dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert Fetcher._to_ms(dt) == 1704067200000


def test_to_ms_with_int_passthrough() -> None:
    assert Fetcher._to_ms(1704067200000) == 1704067200000


def test_to_ms_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Fetcher._to_ms(datetime(2024, 1, 1))


def test_timeframe_ms_mapping() -> None:
    assert TIMEFRAME_MS["1h"] == 3_600_000
    assert TIMEFRAME_MS["1d"] == 86_400_000
    assert TIMEFRAME_MS["1m"] * 60 == TIMEFRAME_MS["1h"]


def test_unknown_exchange_raises() -> None:
    with pytest.raises(ValueError, match="Unknown exchange"):
        Fetcher(exchange_name="totally_not_real_exchange_xyz")


def test_to_dataframe_with_empty_bars() -> None:
    f = Fetcher.__new__(Fetcher)  # bypass __init__ — no network
    f.exchange_name = "binance"
    df = f._to_dataframe([], "BTC/USDT", "1h")
    assert df.empty
    assert list(df.columns) == [
        "exchange", "symbol", "timeframe", "timestamp",
        "open", "high", "low", "close", "volume",
    ]


def test_to_dataframe_dedupes_overlapping() -> None:
    f = Fetcher.__new__(Fetcher)
    f.exchange_name = "binance"
    bars = [
        [1704067200000, 100.0, 101.0, 99.0, 100.5, 10.0],
        [1704067200000, 100.0, 101.0, 99.0, 100.5, 10.0],
        [1704070800000, 100.5, 101.5, 99.5, 101.0, 12.0],
    ]
    df = f._to_dataframe(bars, "BTC/USDT", "1h")
    assert len(df) == 2


def test_empty_frame_has_correct_columns() -> None:
    df = _empty_frame()
    assert df.empty
    assert "timestamp" in df.columns
    assert "close" in df.columns
