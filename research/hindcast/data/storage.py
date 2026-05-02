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

    def __init__(self, db_path: str | Path, *, read_only: bool = False) -> None:
        self.db_path = Path(db_path)
        self.read_only = read_only
        # In read_only mode the file must already exist and be initialised by
        # the writer — this lets the API process coexist with the LiveEngine
        # (DuckDB allows N readers OR 1 writer per file, not r/w from two
        # processes simultaneously).
        if not read_only:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._init_schema()

    @contextmanager
    def connect(self) -> Iterator[duckdb.DuckDBPyConnection]:
        # DuckDB locks the file process-exclusively during a connection.
        # When the dashboard API and the LiveEngine both touch the same
        # database from separate processes, transient lock conflicts are
        # expected. Both sides retry briefly so neither side gives up on
        # what is really just a 50ms contention window.
        import time
        last_err: Exception | None = None
        for attempt in range(40):
            try:
                con = duckdb.connect(str(self.db_path), read_only=self.read_only)
                break
            except duckdb.IOException as e:
                if "Conflicting lock" not in str(e):
                    raise
                last_err = e
                time.sleep(0.05 + min(attempt, 10) * 0.05)
        else:
            assert last_err is not None
            raise last_err
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

    # ---------- live trading audit log ----------

    def start_live_run(
        self,
        run_id: str,
        started_at: datetime,
        strategy: str,
        symbol: str,
        timeframe: str,
        dry_run: bool,
        params: str | None = None,
    ) -> None:
        with self.connect() as con:
            con.execute(
                """
                INSERT INTO live_run (run_id, started_at, strategy, symbol, timeframe, dry_run, params)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [run_id, started_at, strategy, symbol, timeframe, dry_run, params],
            )

    def end_live_run(self, run_id: str, ended_at: datetime) -> None:
        with self.connect() as con:
            con.execute(
                "UPDATE live_run SET ended_at = ? WHERE run_id = ?",
                [ended_at, run_id],
            )

    def record_live_order(
        self,
        run_id: str,
        intent_ts: datetime,
        submit_ts: datetime,
        side: str,
        quantity: float,
        status: str,
        exchange_id: str | None = None,
        error_message: str | None = None,
    ) -> int:
        """Insert an order row, return the auto-allocated order_id."""
        with self.connect() as con:
            row = con.execute("SELECT nextval('live_order_id_seq')").fetchone()
            order_id = int(row[0]) if row else 0
            con.execute(
                """
                INSERT INTO live_orders
                (order_id, run_id, intent_ts, submit_ts, side, quantity, status, exchange_id, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [order_id, run_id, intent_ts, submit_ts, side, quantity, status, exchange_id, error_message],
            )
        return order_id

    def record_live_fill(
        self,
        run_id: str,
        order_id: int,
        fill_ts: datetime,
        side: str,
        quantity: float,
        price: float,
        fee: float,
        fee_currency: str | None = None,
    ) -> None:
        with self.connect() as con:
            con.execute(
                """
                INSERT OR REPLACE INTO live_fills
                (run_id, order_id, fill_ts, side, quantity, price, fee, fee_currency)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [run_id, order_id, fill_ts, side, quantity, price, fee, fee_currency],
            )

    def record_live_equity(
        self,
        run_id: str,
        timestamp: datetime,
        cash: float,
        position: float,
        price: float,
        equity: float,
    ) -> None:
        with self.connect() as con:
            con.execute(
                """
                INSERT OR REPLACE INTO live_equity
                (run_id, timestamp, cash, position, price, equity)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [run_id, timestamp, cash, position, price, equity],
            )

    def query_live_orders(self, run_id: str | None = None) -> pd.DataFrame:
        sql = "SELECT * FROM live_orders"
        params: list = []
        if run_id is not None:
            sql += " WHERE run_id = ?"
            params.append(run_id)
        sql += " ORDER BY submit_ts"
        with self.connect() as con:
            return con.execute(sql, params).df()

    def query_live_fills(self, run_id: str | None = None) -> pd.DataFrame:
        sql = "SELECT * FROM live_fills"
        params: list = []
        if run_id is not None:
            sql += " WHERE run_id = ?"
            params.append(run_id)
        sql += " ORDER BY fill_ts"
        with self.connect() as con:
            return con.execute(sql, params).df()

    def query_live_equity(self, run_id: str) -> pd.DataFrame:
        with self.connect() as con:
            return con.execute(
                "SELECT * FROM live_equity WHERE run_id = ? ORDER BY timestamp",
                [run_id],
            ).df()

    def list_live_runs(self) -> pd.DataFrame:
        with self.connect() as con:
            return con.execute(
                "SELECT * FROM live_run ORDER BY started_at DESC"
            ).df()

    def request_stop(self, run_id: str) -> bool:
        """Set stop_requested=true on a run. Returns True if a row was updated.

        Opens its own short r/w connection regardless of self.read_only —
        this is the one mutating call the API needs and a read-only Storage
        can't make. Retries briefly on lock contention with the live engine.
        """
        import time
        attempts = 0
        last_err: Exception | None = None
        while attempts < 10:
            try:
                con = duckdb.connect(str(self.db_path), read_only=False)
                try:
                    row = con.execute(
                        "SELECT 1 FROM live_run WHERE run_id = ? AND ended_at IS NULL",
                        [run_id],
                    ).fetchone()
                    if row is None:
                        return False
                    con.execute(
                        "UPDATE live_run SET stop_requested = TRUE WHERE run_id = ?",
                        [run_id],
                    )
                    return True
                finally:
                    con.close()
            except duckdb.IOException as e:
                last_err = e
                attempts += 1
                time.sleep(0.1)
        if last_err:
            raise last_err
        return False

    def is_stop_requested(self, run_id: str) -> bool:
        with self.connect() as con:
            row = con.execute(
                "SELECT stop_requested FROM live_run WHERE run_id = ?",
                [run_id],
            ).fetchone()
        return bool(row and row[0])

    def sweep_stale_runs(self, max_idle_seconds: int = 300) -> int:
        """Mark runs as crashed where ended_at is NULL and the last heartbeat
        (most recent equity row, or started_at if none) is older than the cutoff.

        Returns number of rows marked.
        """
        from datetime import datetime, timedelta, timezone
        cutoff = datetime.now(tz=timezone.utc) - timedelta(seconds=max_idle_seconds)
        now = datetime.now(tz=timezone.utc)
        with self.connect() as con:
            rows = con.execute(
                """
                SELECT lr.run_id,
                       COALESCE((SELECT MAX(timestamp) FROM live_equity WHERE run_id = lr.run_id),
                                lr.started_at) AS last_seen
                FROM live_run lr
                WHERE lr.ended_at IS NULL
                """,
            ).fetchall()
            stale = [r[0] for r in rows if r[1] is not None and pd.Timestamp(r[1]).to_pydatetime() < cutoff]
            for rid in stale:
                con.execute(
                    "UPDATE live_run SET ended_at = ?, crashed_at = ? WHERE run_id = ?",
                    [now, now, rid],
                )
        return len(stale)

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
