"""Project-wide configuration.

Loaded from environment variables and `.env`. Pydantic does the validation
and type coercion, so misspellings or wrong types fail loudly at startup
rather than silently breaking 30 minutes into a sync job.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# config.py is at research/hindcast/config.py — parents[2] is the project root.
# Resolved this way so the default db_path doesn't depend on cwd.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ----- Storage -----
    db_path: Path = Field(
        default=_PROJECT_ROOT / "data" / "hindcast.duckdb",
        description="Path to the local DuckDB file.",
    )

    # ----- Network -----
    https_proxy: str | None = None
    http_proxy: str | None = None

    @property
    def proxy(self) -> str | None:
        """Pick whichever proxy env var is set."""
        return self.https_proxy or self.http_proxy


# Single shared instance — import this everywhere you need config.
settings = Settings()
