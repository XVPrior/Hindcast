"""Schema definitions for Hindcast's local DuckDB store.

Kept as raw SQL strings (rather than ORM models) on purpose:
- We want to see exactly what hits the database.
- DuckDB-specific features (like INSERT OR REPLACE) don't translate well
  through ORMs.
- Schema changes for a research project should be obvious in diffs.
"""

OHLCV_TABLE = "ohlcv"

OHLCV_DDL = """
CREATE TABLE IF NOT EXISTS ohlcv (
    exchange   VARCHAR     NOT NULL,
    symbol     VARCHAR     NOT NULL,
    timeframe  VARCHAR     NOT NULL,
    -- TIMESTAMPTZ (not TIMESTAMP): DuckDB's Python binding silently converts
    -- tz-aware inputs to local time before stripping tz when the column is
    -- naive. TIMESTAMPTZ stores epoch microseconds and round-trips UTC cleanly.
    timestamp  TIMESTAMPTZ NOT NULL,
    open       DOUBLE      NOT NULL,
    high       DOUBLE      NOT NULL,
    low        DOUBLE      NOT NULL,
    close      DOUBLE      NOT NULL,
    volume     DOUBLE      NOT NULL,
    PRIMARY KEY (exchange, symbol, timeframe, timestamp)
);
"""

# DuckDB primary key already gives us a lookup index, but an explicit one on
# (exchange, symbol, timeframe) helps range scans across many timestamps.
OHLCV_INDEX_DDL = """
CREATE INDEX IF NOT EXISTS idx_ohlcv_market
ON ohlcv (exchange, symbol, timeframe);
"""

ALL_DDL: list[str] = [OHLCV_DDL, OHLCV_INDEX_DDL]
