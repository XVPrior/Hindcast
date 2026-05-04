# Hindcast

A solo crypto quant research playground — built end-to-end to learn how
the whole stack actually feels in your hands. Data pipeline → backtest
engine → honest strategy research → paper-trading dashboard wired to
Binance testnet.

🌐 **Live demo · <https://hindcast.pages.dev>**
🔌 **API · <https://hindcast.fly.dev/api/health>**
📚 **Research blogs · 5 posts in [`blogs/`](./blogs/)**

> The live demo is read-only — the actual paper trading (real testnet
> orders) runs on my laptop. The dashboard shows the audit log of those
> sessions. See [DEPLOY.md](./DEPLOY.md) for how the two halves are split.

## Why this name

In meteorology and finance, *hindcasting* means feeding a model historical
inputs to see whether it would have predicted what actually happened.
That's exactly what backtesting is — and a useful reminder that fitting
the past is easy; the hard part is whether the model says anything about
tomorrow.

## Project layout

```
.
├── research/                  Python — the whole research + execution stack
│   ├── hindcast/
│   │   ├── data/              (M1) DuckDB storage, ccxt fetcher, incremental sync
│   │   ├── backtest/          (M2) Engine, Portfolio, ExecutionModel, types,
│   │   │                            strategies (BuyAndHold / MA / Bollinger), metrics
│   │   ├── exec/              (M4) Live trading loop, Binance testnet client
│   │   ├── api/               (M4) FastAPI — read-only dashboard backend
│   │   ├── cli.py             Typer CLI: sync / status / backtest / live / api
│   │   └── markets.toml       7 configured spot markets (BTC/ETH/SOL/BNB/XRP/DOGE/ADA)
│   ├── notebooks/             (M3) 5 executed research notebooks (figures embedded)
│   ├── scripts/               One-shot scripts: sync_funding, testnet_check, build_demo_db
│   └── tests/                 93 unit tests (pytest)
├── frontend/                  (M4) Vite + React 19 dashboard
│   └── src/
│       ├── routes/            File-based routes: / · /markets · /chart · /live · /live/$runId
│       ├── components/        PriceChart, EquityChart, RunBadges, Sparkline
│       └── lib/               Typed API client, run-status helpers
├── blogs/                     (M3) 5 research posts (Chinese drafts)
├── data/                      Gitignored: hindcast.duckdb (~110MB) + demo snapshot
├── Dockerfile                 (Deploy) Fly.io image, builds backend + bakes demo DB
├── fly.toml                   (Deploy) Fly app config
└── DEPLOY.md                  Walkthrough for Fly + Cloudflare Pages
```

## Milestones — planned vs actual

| | Plan | Actual |
|---|---|---|
| **M1 — Data** | Pull crypto OHLCV, store, incremental sync | ✅ + funding-rate data layer (added in M3-E4) |
| **M2 — Backtest** | Event-driven engine, slippage, fees, equity curve | ✅ + 60-line metrics module (Sharpe, win rate, profit factor, FIFO trade pairing) |
| **M3 — Strategy lab** | 3 classic strategies, write up findings | ✅ 4 strategies, 5 blog posts; **none beat buy-and-hold** on BTC 2024-2025 |
| **M4 — Paper trading** | TypeScript executor against Binance testnet | **Re-architected** — Python LiveEngine + FastAPI + React dashboard. Same `Portfolio` and `ExecutionModel` as backtest, real testnet orders verified end-to-end. |

The M4 pivot was the biggest deviation: by keeping execution in Python I
got code reuse with backtest (one `Portfolio` class, one fill model,
one strategy interface), and TypeScript focused on what it's actually
good at — the dashboard UI.

## M3 blogs — the honest research

The strategy lab's deliverable was 5 written posts, not running code.
They document what failed, with numbers:

1. [《量化的第零步》](./blogs/m3_e1_doing_nothing.md) — buy-and-hold as the unbeatable baseline (BTC +97% / ETH +26% over 2 years)
2. [《MA 交叉为什么跑不赢什么都不做》](./blogs/m3_e2_ma_crossover.md) — 0/13 MA variants beat buy_and_hold on BTC
3. [《用均值回归代替趋势跟踪》](./blogs/m3_e3_mean_reversion.md) — 0/9 Bollinger variants beat buy_and_hold either
4. [《资金费率套利还赚钱吗》](./blogs/m3_e4_funding_carry.md) — yes, 4-7% net APR, but visibly decaying quarter-over-quarter
5. [《散户量化的结构性问题》](./blogs/m3_e5_what_we_learned.md) — meta-synthesis: parameter fragility + fee leakage + retail edge structure

## Setup

```bash
git clone https://github.com/XVPrior/Hindcast
cd Hindcast/research
uv sync                                # Python deps via uv (Python 3.11)
uv run python scripts/hello.py         # smoke test

# In another terminal, for the dashboard:
cd ../frontend
pnpm install
```

For Binance testnet credentials (only needed if you want live paper
trading), grab keys from <https://testnet.binance.vision> and put them
in `research/.env`:

```
BINANCE_TESTNET_API_KEY=...
BINANCE_TESTNET_API_SECRET=...
HTTPS_PROXY=http://127.0.0.1:7897   # if you're behind one
```

Then `uv run hindcast testnet-check` verifies the round-trip.

## Daily use

```bash
cd research

# --- data ---
uv run hindcast markets                # configured markets list
uv run hindcast sync                   # incremental OHLCV pull
uv run python scripts/sync_funding.py  # funding-rate history
uv run hindcast status                 # bar counts per market

# --- backtest ---
uv run hindcast backtest \
    --strategy ma_crossover \
    --symbol BTC/USDT --timeframe 1d \
    --start 2024-01-01 --end 2026-01-01

# --- live (paper) ---
uv run hindcast testnet-check                # validate creds
uv run hindcast live --strategy ma_crossover \
    --timeframe 1m --allocation-pct 0.05     # dry-run default
uv run hindcast live --strategy ma_crossover \
    --timeframe 1m --live                    # actually places orders

# --- dashboard ---
uv run hindcast api                          # backend on :8000
cd ../frontend && pnpm dev                   # frontend on :5173
```

Adding a market: edit `research/hindcast/markets.toml`, then `sync`.

## Stack

| Layer | Tech |
|---|---|
| **Storage / data** | Python 3.11, DuckDB, pandas, pyarrow |
| **Exchange I/O** | ccxt (Binance spot + perp) |
| **Backtest engine** | Pure Python, frozen dataclasses, 88 tests |
| **Live engine** | ccxt → Binance testnet, audit log to DuckDB |
| **API** | FastAPI + Pydantic + uvicorn |
| **Frontend** | Vite + React 19 + TanStack Router (file-based) + TanStack Query |
| **Charts** | TradingView lightweight-charts v5 + inline SVG sparklines |
| **Styling** | Tailwind CSS v4 + shadcn-style component idioms |
| **Quality** | ruff, pyright, pytest |
| **Hosting** | Fly.io (API) · Cloudflare Pages (static SPA) |
| **Tooling** | uv (Python), pnpm workspaces (JS), nbconvert |

## Deploy

Public read-only demo: backend on Fly.io, frontend on Cloudflare Pages.
Step-by-step in [DEPLOY.md](./DEPLOY.md). First-time deploy is ~30 min;
incremental redeploys (`flyctl deploy` after `git push`) are <2 min.

## What this project intentionally doesn't do

- **No real-money trading.** Testnet only. Credentials never leave the
  laptop in prod (`exec/` is the only module that touches authenticated
  endpoints, and the Fly container doesn't have keys).
- **No exotic strategies.** Trend, mean-revert, carry — done honestly.
- **No ML / RL.** The M3 finding is that even classical methods don't
  beat passive holding on this sample, so any ML pretensions would be
  downstream of solving that.
- **No multi-asset portfolio optimisation.** Single-leg, single-symbol.
- **No production hardening.** Single instance, scale-to-zero, no alerts.

## Status

🟢 **M1–M4 complete + deployed.** Code feature-frozen while the M3
blogs get edited into thesis chapters.
