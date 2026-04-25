"""Load and validate the markets config."""

from __future__ import annotations

import tomllib
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, field_validator


class MarketSpec(BaseModel):
    exchange: str
    symbol: str
    timeframes: list[str]
    fallback_since: datetime

    @field_validator("fallback_since", mode="before")
    @classmethod
    def parse_date(cls, v: str | datetime) -> datetime:
        dt = v if isinstance(v, datetime) else datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt


def load_markets(path: Path) -> list[MarketSpec]:
    raw = tomllib.loads(path.read_text())
    return [MarketSpec(**m) for m in raw.get("markets", [])]
