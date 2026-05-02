"""FastAPI application entry point.

Started via `uv run hindcast api` (see hindcast.cli). Routes live in
hindcast.api.routes.* and are mounted here.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from hindcast import __version__
from hindcast.api.routes import health, markets

app = FastAPI(
    title="Hindcast API",
    version=__version__,
    description="Local dashboard backend for the Hindcast trading toolkit.",
)

# Vite dev server origin — extend when staging/prod arrives.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(markets.router)
