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

# ----- Live trading audit log -----
# A "run" is one invocation of `hindcast live`. Each session gets a UUID;
# orders / fills / equity snapshots reference it. Testnet is treated as
# the source of truth for actual balances — these tables are an audit
# log, not a portfolio replica.

LIVE_RUN_DDL = """
CREATE TABLE IF NOT EXISTS live_run (
    run_id          VARCHAR     NOT NULL PRIMARY KEY,
    started_at      TIMESTAMPTZ NOT NULL,
    ended_at        TIMESTAMPTZ,
    strategy        VARCHAR     NOT NULL,
    symbol          VARCHAR     NOT NULL,
    timeframe       VARCHAR     NOT NULL,
    dry_run         BOOLEAN     NOT NULL,
    params          VARCHAR
);
"""

# Idempotent column adds — required because earlier T4 sessions exist with
# the older 8-column shape. DuckDB's ALTER ... IF NOT EXISTS is a no-op
# when the column is already there.
LIVE_RUN_MIGRATIONS = [
    "ALTER TABLE live_run ADD COLUMN IF NOT EXISTS stop_requested BOOLEAN DEFAULT FALSE",
    "ALTER TABLE live_run ADD COLUMN IF NOT EXISTS crashed_at TIMESTAMPTZ",
]

LIVE_ORDER_SEQ_DDL = "CREATE SEQUENCE IF NOT EXISTS live_order_id_seq START 1;"

LIVE_ORDERS_DDL = """
CREATE TABLE IF NOT EXISTS live_orders (
    order_id        BIGINT      NOT NULL PRIMARY KEY,
    run_id          VARCHAR     NOT NULL,
    intent_ts       TIMESTAMPTZ NOT NULL,
    submit_ts       TIMESTAMPTZ NOT NULL,
    side            VARCHAR     NOT NULL,
    quantity        DOUBLE      NOT NULL,
    status          VARCHAR     NOT NULL,
    exchange_id     VARCHAR,
    error_message   VARCHAR
);
"""

LIVE_FILLS_DDL = """
CREATE TABLE IF NOT EXISTS live_fills (
    run_id        VARCHAR     NOT NULL,
    order_id      BIGINT      NOT NULL,
    fill_ts       TIMESTAMPTZ NOT NULL,
    side          VARCHAR     NOT NULL,
    quantity      DOUBLE      NOT NULL,
    price         DOUBLE      NOT NULL,
    fee           DOUBLE      NOT NULL,
    fee_currency  VARCHAR,
    PRIMARY KEY (run_id, order_id, fill_ts)
);
"""

LIVE_EQUITY_DDL = """
CREATE TABLE IF NOT EXISTS live_equity (
    run_id    VARCHAR     NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    cash      DOUBLE      NOT NULL,
    position  DOUBLE      NOT NULL,
    price     DOUBLE      NOT NULL,
    equity    DOUBLE      NOT NULL,
    PRIMARY KEY (run_id, timestamp)
);
"""

ALL_DDL: list[str] = [
    OHLCV_DDL,
    OHLCV_INDEX_DDL,
    FUNDING_RATE_DDL,
    FUNDING_RATE_INDEX_DDL,
    LIVE_RUN_DDL,
    *LIVE_RUN_MIGRATIONS,
    LIVE_ORDER_SEQ_DDL,
    LIVE_ORDERS_DDL,
    LIVE_FILLS_DDL,
    LIVE_EQUITY_DDL,
]
