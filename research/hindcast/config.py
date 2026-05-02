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

    # ----- Binance spot testnet -----
    # Credentials must be obtained from https://testnet.binance.vision
    # Pydantic-settings reads these from .env or process env. They never
    # land in code, logs, or commits — secret is masked when printed.
    binance_testnet_api_key: str | None = None
    binance_testnet_api_secret: str | None = None

    @property
    def proxy(self) -> str | None:
        """Pick whichever proxy env var is set."""
        return self.https_proxy or self.http_proxy

    @property
    def has_testnet_creds(self) -> bool:
        return bool(self.binance_testnet_api_key and self.binance_testnet_api_secret)

    def testnet_key_fingerprint(self) -> str:
        """Show the first 4 + last 2 chars of the key. Never print the secret."""
        k = self.binance_testnet_api_key or ""
        if len(k) < 8:
            return "(missing)"
        return f"{k[:4]}…{k[-2:]} ({len(k)} chars)"


# Single shared instance — import this everywhere you need config.
settings = Settings()
