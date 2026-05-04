# Hindcast

A crypto quant research playground built to learn-by-doing.
Data pipeline → backtest engine → strategy lab → paper-trading executor.

## Why this name

In meteorology and finance, *hindcasting* means feeding a model historical inputs to see whether it would have predicted what actually happened. That's exactly what backtesting is — and a useful reminder that fitting the past is easy; the hard part is whether the model says anything about tomorrow.

## Project layout

- `research/` — Python. Data ingestion, storage, backtest engine, strategy code, notebooks.
- `execution/` — TypeScript (added at Milestone 4). Live execution against exchange testnets, monitoring dashboard.
- `data/` — Local DuckDB and parquet files. Gitignored.

## Roadmap

- **M1 — Data layer.** Pull and store crypto OHLCV from exchanges. Incremental sync.
- **M2 — Backtest engine.** Event-driven backtester with slippage, fees, full equity curve.
- **M3 — Strategy lab.** Reproduce 3 classic strategies (MA crossover, Bollinger mean reversion, funding-rate arb). Write up findings.
- **M4 — Paper trading.** Wire the engine to Binance testnet via TypeScript. Real-time signal → order flow with full failure handling.

## Status

🟢 M1 in progress

## Setup

```bash
cd research
uv sync
uv run python scripts/hello.py
```

## Deploy

Public read-only demo on Fly.io (backend) + Cloudflare Pages (frontend).
See [DEPLOY.md](./DEPLOY.md) for the full guide.

## Daily use

After setup, the typical workflow is:

```bash
cd research

# See what markets are configured
uv run hindcast markets

# Sync everything (incremental — safe to run often)
uv run hindcast sync

# See what's in the local store
uv run hindcast status

# Sync just one symbol
uv run hindcast sync --symbol ETH/USDT
```

To add a new market, edit `research/hindcast/markets.toml` and run `sync` again.

## Stack

- **Research**: Python 3.11+, pandas, DuckDB, CCXT
- **Quality**: ruff, pyright, pytest
- **Execution (M4)**: TypeScript, ccxt-ts or native exchange SDKs
