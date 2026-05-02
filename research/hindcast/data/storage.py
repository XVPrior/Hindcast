"""DuckDB-backed storage for OHLCV data."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

import duckdb
import pandas as pd

from .schema import ALL_DDL


class Storage:
    """Thin wrapper around a local DuckDB file.

    One Storage instance == one database file. Connections are short-lived
    (opened per operation) which keeps things simple and safe across threads
    or notebook reloads.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def connect(self) -> Iterator[duckdb.DuckDBPyConnection]:
        con = duckdb.connect(str(self.db_path))
        try:
            yield con
        finally:
            con.close()

    def _init_schema(self) -> None:
        with self.connect() as con:
            for ddl in ALL_DDL:
                con.execute(ddl)

    # ---------- write ----------

    def upsert_ohlcv(self, df: pd.DataFrame) -> int:
        """Insert or replace OHLCV rows. Returns number of rows written.

        Expects columns:
            exchange, symbol, timeframe, timestamp, open, high, low, close, volume
        `timestamp` must be a pandas datetime (tz-aware UTC or naive UTC).
        """
        if df.empty:
            return 0

        required = {
            "exchange", "symbol", "timeframe", "timestamp",
            "open", "high", "low", "close", "volume",
        }
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"DataFrame missing columns: {missing}")

        df = df[[
            "exchange", "symbol", "timeframe", "timestamp",
            "open", "high", "low", "close", "volume",
        ]]

        with self.connect() as con:
            con.register("incoming_ohlcv", df)
            con.execute("INSERT OR REPLACE INTO ohlcv SELECT * FROM incoming_ohlcv")
            con.unregister("incoming_ohlcv")
        return len(df)

    # ---------- read ----------

    def query_ohlcv(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        start: datetime | str | None = None,
        end: datetime | str | None = None,
    ) -> pd.DataFrame:
        """Read OHLCV rows in a [start, end) window, ordered by timestamp."""
        sql = """
            SELECT exchange, symbol, timeframe, timestamp,
                   open, high, low, close, volume
            FROM ohlcv
            WHERE exchange = ? AND symbol = ? AND timeframe = ?
        """
        params: list = [exchange, symbol, timeframe]

        if start is not None:
            sql += " AND timestamp >= ?"
            params.append(start)
        if end is not None:
            sql += " AND timestamp < ?"
            params.append(end)
        sql += " ORDER BY timestamp"

        with self.connect() as con:
            return con.execute(sql, params).df()

    def latest_timestamp(
        self, exchange: str, symbol: str, timeframe: str
    ) -> pd.Timestamp | None:
        """Return the most recent stored timestamp for this market, or None.

        Uses ORDER BY ... LIMIT 1 instead of MAX(timestamp): DuckDB 1.5.2
        crashes ("Attempted to access index 0 within vector of size 0") when
        MAX is taken over a TIMESTAMPTZ column with a WHERE filter that
        matches no rows while the table has rows for other filters.
        """
        with self.connect() as con:
            row = con.execute(
                """
                SELECT timestamp FROM ohlcv
                WHERE exchange = ? AND symbol = ? AND timeframe = ?
                ORDER BY timestamp DESC LIMIT 1
                """,
                [exchange, symbol, timeframe],
            ).fetchone()
        if row is None:
            return None
        return pd.Timestamp(row[0])

    # ---------- funding rate ----------

    def upsert_funding_rate(self, df: pd.DataFrame) -> int:
        """Insert or replace funding-rate rows. Returns number of rows written.

        Expects columns: exchange, symbol, timestamp, rate
        """
        if df.empty:
            return 0

        required = {"exchange", "symbol", "timestamp", "rate"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"DataFrame missing columns: {missing}")

        df = df[["exchange", "symbol", "timestamp", "rate"]]

        with self.connect() as con:
            con.register("incoming_funding", df)
            con.execute(
                "INSERT OR REPLACE INTO funding_rate SELECT * FROM incoming_funding"
            )
            con.unregister("incoming_funding")
        return len(df)

    def query_funding_rate(
        self,
        exchange: str,
        symbol: str,
        start: datetime | str | None = None,
        end: datetime | str | None = None,
    ) -> pd.DataFrame:
        """Read funding-rate rows in [start, end), ordered by timestamp."""
        sql = """
            SELECT exchange, symbol, timestamp, rate
            FROM funding_rate
            WHERE exchange = ? AND symbol = ?
        """
        params: list = [exchange, symbol]
        if start is not None:
            sql += " AND timestamp >= ?"
            params.append(start)
        if end is not None:
            sql += " AND timestamp < ?"
            params.append(end)
        sql += " ORDER BY timestamp"
        with self.connect() as con:
            return con.execute(sql, params).df()

    def latest_funding_timestamp(
        self, exchange: str, symbol: str
    ) -> pd.Timestamp | None:
        """Most recent stored funding timestamp for this market, or None."""
        with self.connect() as con:
            row = con.execute(
                """
                SELECT timestamp FROM funding_rate
                WHERE exchange = ? AND symbol = ?
                ORDER BY timestamp DESC LIMIT 1
                """,
                [exchange, symbol],
            ).fetchone()
        if row is None:
            return None
        return pd.Timestamp(row[0])

    # ---------- counts ----------

    def row_count(
        self,
        exchange: str | None = None,
        symbol: str | None = None,
        timeframe: str | None = None,
    ) -> int:
        """Count rows, optionally filtered. Useful for sanity checks."""
        sql = "SELECT COUNT(*) FROM ohlcv WHERE 1=1"
        params: list = []
        if exchange:
            sql += " AND exchange = ?"
            params.append(exchange)
        if symbol:
            sql += " AND symbol = ?"
            params.append(symbol)
        if timeframe:
            sql += " AND timeframe = ?"
            params.append(timeframe)

        with self.connect() as con:
            row = con.execute(sql, params).fetchone()
        return int(row[0]) if row else 0
