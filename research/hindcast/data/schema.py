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

FUNDING_RATE_TABLE = "funding_rate"

# Discrete funding events on a perpetual contract. Binance USDM is every 8h.
# `rate` is per-interval (not annualized) — multiply by 3 for daily, by 1095
# (365 * 3) for a naive annualized figure.
FUNDING_RATE_DDL = """
CREATE TABLE IF NOT EXISTS funding_rate (
    exchange   VARCHAR     NOT NULL,
    symbol     VARCHAR     NOT NULL,
    timestamp  TIMESTAMPTZ NOT NULL,
    rate       DOUBLE      NOT NULL,
    PRIMARY KEY (exchange, symbol, timestamp)
);
"""

FUNDING_RATE_INDEX_DDL = """
CREATE INDEX IF NOT EXISTS idx_funding_market
ON funding_rate (exchange, symbol);
"""

ALL_DDL: list[str] = [
    OHLCV_DDL,
    OHLCV_INDEX_DDL,
    FUNDING_RATE_DDL,
    FUNDING_RATE_INDEX_DDL,
]
