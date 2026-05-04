"""FastAPI application entry point.

Started via `uv run hindcast api` (see hindcast.cli). Routes live in
hindcast.api.routes.* and are mounted here.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from hindcast import __version__
from hindcast.api.routes import health, markets, overview, runs

app = FastAPI(
    title="Hindcast API",
    version=__version__,
    description="Local dashboard backend for the Hindcast trading toolkit.",
)

# CORS origins are env-driven so dev (Vite at :5173) and prod (Cloudflare
# Pages domain) can both work without code changes. Comma-separated list,
# or "*" to allow any origin (use only for the public read-only demo).
_default_origins = "http://localhost:5173,http://127.0.0.1:5173"
_origins_env = os.environ.get("CORS_ALLOW_ORIGINS", _default_origins)
allow_origins = [o.strip() for o in _origins_env.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Root health probe — Fly's HTTP service check hits /health (no /api prefix).
@app.get("/health")
def root_health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}

# All routes live under /api so dev (Vite proxy) and prod (Cloudflare →
# Fly cross-origin) share the same path shape — no rewrite needed.
api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(markets.router)
api_router.include_router(runs.router)
api_router.include_router(overview.router)
app.include_router(api_router)
