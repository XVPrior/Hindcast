"""Build a deploy-friendly snapshot DB.

The full DB has ~700K 5m bars and a few crashed live sessions — neither
useful in a public demo. This script copies the main DB into a smaller
companion file:

  - Strips OHLCV at 5m timeframe (saves ~80% size)
  - Keeps everything else: 1d/4h/1h OHLCV, funding history, live audit
    log (orders/fills/equity), live_run rows
  - Marks any 'active' sessions as ended (no live engine in the deployed
    container; orphan active rows would mislead the dashboard)

Run before `flyctl deploy`:
    uv run python research/scripts/build_demo_db.py

The output lands at data/hindcast-demo.duckdb and is what the Dockerfile
copies into the image.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE = PROJECT_ROOT / "data" / "hindcast.duckdb"
TARGET = PROJECT_ROOT / "data" / "hindcast-demo.duckdb"


def main() -> None:
    if not SOURCE.exists():
        raise FileNotFoundError(f"Source DB not found: {SOURCE}")
    if TARGET.exists():
        TARGET.unlink()

    # Initialise the target with the current schema (creates empty tables).
    import sys
    sys.path.insert(0, str(PROJECT_ROOT / "research"))
    from hindcast.data.schema import ALL_DDL  # noqa: E402

    con = duckdb.connect(str(TARGET), read_only=False)
    for ddl in ALL_DDL:
        con.execute(ddl)

    # ATTACH the source as a read-only secondary database, then bulk-copy.
    con.execute(f"ATTACH '{SOURCE}' AS src (READ_ONLY)")
    con.execute(
        "INSERT INTO ohlcv SELECT * FROM src.ohlcv WHERE timeframe != '5m'"
    )
    con.execute("INSERT INTO funding_rate SELECT * FROM src.funding_rate")
    con.execute("INSERT INTO live_run SELECT * FROM src.live_run")
    con.execute("INSERT INTO live_orders SELECT * FROM src.live_orders")
    con.execute("INSERT INTO live_fills SELECT * FROM src.live_fills")
    con.execute("INSERT INTO live_equity SELECT * FROM src.live_equity")
    con.execute("DETACH src")

    # Any 'active' rows would lie to dashboard visitors — flatten them.
    con.execute(
        "UPDATE live_run SET ended_at = NOW(), crashed_at = NOW() "
        "WHERE ended_at IS NULL"
    )

    # Quick stats
    n_ohlcv = con.execute("SELECT COUNT(*) FROM ohlcv").fetchone()[0]
    n_fund = con.execute("SELECT COUNT(*) FROM funding_rate").fetchone()[0]
    n_runs = con.execute("SELECT COUNT(*) FROM live_run").fetchone()[0]
    con.close()

    size_mb = TARGET.stat().st_size / 1024 / 1024
    print(f"wrote {TARGET}")
    print(f"  size       : {size_mb:.1f} MB")
    print(f"  ohlcv rows : {n_ohlcv:,} (5m stripped)")
    print(f"  funding    : {n_fund:,}")
    print(f"  live runs  : {n_runs:,}")


if __name__ == "__main__":
    main()
