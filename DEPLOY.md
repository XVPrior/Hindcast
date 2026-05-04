# Deploy

Public-demo deployment of Hindcast: read-only dashboard, snapshot data, no
live trading on the server. Architecture:

```
   visitor browser
        │
        ▼
  Cloudflare Pages          Fly.io
  (static React app)  ────► (FastAPI + DuckDB snapshot)
                       fetch /api/*
```

The live engine **stays on your laptop** — testnet credentials never
leave your machine. The deployed backend serves only the audit log of
sessions you've already run.

---

## Prerequisites

- `flyctl` installed and `flyctl auth login` done
- Cloudflare account
- Local DB populated (run `uv run hindcast sync` and
  `uv run python research/scripts/sync_funding.py` if you haven't)

---

## Backend → Fly.io

### 1. Build the snapshot DB (locally)

```bash
cd research && uv run python scripts/build_demo_db.py
```

Strips 5m bars and marks any orphan "active" runs as ended. Output is
`data/hindcast-demo.duckdb` (~25 MB), what the Dockerfile bakes in.

### 2. Provision the Fly app (first time only)

```bash
flyctl launch --copy-config --no-deploy
```

It'll ask for:
- App name → e.g. `hindcast-dashboard` (must be globally unique)
- Region → pick one close to you (`hkg`, `nrt`, `sjc`, `ams`, etc.)
- Postgres / Redis → **No** to both
- Deploy now → **No** (we want to inspect fly.toml first)

This rewrites `fly.toml` with your chosen app name and region. Open it
and confirm `internal_port = 8000` and the `[http_service.checks]`
section are still there.

### 3. Deploy

```bash
flyctl deploy
```

Fly's remote builder will run the Dockerfile. First build takes ~3-5 min;
incremental builds are <1 min thanks to layer caching.

When it's done:

```bash
flyctl status
flyctl logs           # tail logs
curl https://<your-app>.fly.dev/health   # → {"status":"ok",...}
```

### 4. Lock down CORS to your frontend domain

After Cloudflare Pages gives you a URL, run:

```bash
flyctl secrets set CORS_ALLOW_ORIGINS="https://<your-pages-domain>.pages.dev"
```

This redeploys with tighter CORS.

---

## Frontend → Cloudflare Pages

### 1. Connect the GitHub repo

Cloudflare dashboard → **Workers & Pages** → **Create** → **Pages** →
**Connect to Git** → select the `Hindcast` repo.

### 2. Build settings

| Field | Value |
|---|---|
| Framework preset | None |
| Build command | `cd frontend && pnpm install && pnpm build` |
| Build output directory | `frontend/dist` |
| Root directory | `/` (default) |

### 3. Environment variables

Under **Settings → Environment variables**, add:

| Name | Value |
|---|---|
| `VITE_API_BASE` | `https://<your-fly-app>.fly.dev` |
| `NODE_VERSION` | `20` |

`VITE_*` env vars are baked into the static bundle at build time; if you
change the API URL later you need to redeploy the frontend.

### 4. Save and Deploy

First build takes ~2 min. Subsequent pushes to `main` auto-deploy.

---

## Updating data

The DuckDB file is baked into the image. To refresh:

```bash
cd research && uv run hindcast sync                   # pull new OHLCV
cd research && uv run python scripts/sync_funding.py   # pull new funding
cd research && uv run python scripts/build_demo_db.py  # rebuild snapshot
flyctl deploy                                          # ship it
```

A future enhancement is a Fly cron machine that does this on a schedule —
out of scope for the read-only demo.

---

## What the public site shows

- `/` overview — health, market snapshot, recent sessions
- `/markets` — 7 spot pairs with price / 24h / funding 7d sparkline
- `/chart` — interactive candlestick browser (1d/4h/1h available; 5m
  was stripped to keep image small)
- `/live` — every paper-trading session in the audit log (orders, fills,
  equity curve). The **Stop** button is harmless on prod since no engine
  process is actually polling — clicks set the flag and nothing
  receives it. (Can be hidden by a small frontend tweak if needed.)

## What it doesn't show

- 5m OHLCV (use local `hindcast.duckdb` for that)
- Live trading (engine runs locally only — credentials don't leave
  your laptop)
- Backtest runs (those produce one-off PNGs and notebooks, not DB rows)
