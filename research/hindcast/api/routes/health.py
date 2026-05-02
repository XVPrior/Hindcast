"""Liveness probe."""

from __future__ import annotations

from fastapi import APIRouter

from hindcast import __version__
from hindcast.api.models import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__)
