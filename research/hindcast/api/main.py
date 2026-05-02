"""FastAPI application entry point.

Started via `uv run hindcast api` (see hindcast.cli). Currently exposes
just /health — endpoints accrete in later M4 tasks.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from hindcast import __version__

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


class HealthResponse(BaseModel):
    status: str
    version: str


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__)
