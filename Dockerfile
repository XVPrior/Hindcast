# Hindcast container — runs the FastAPI dashboard backend or the
# multi-strategy live worker depending on which process group Fly starts.
# Same image, different CMD per process.

# --------------------------------------------------------------------
FROM python:3.11-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app/research

COPY research/pyproject.toml ./
COPY research/hindcast ./hindcast

RUN uv sync --no-dev

# --------------------------------------------------------------------
FROM python:3.11-slim

WORKDIR /app/research

COPY --from=builder /app/research/.venv ./.venv
COPY --from=builder /app/research/hindcast ./hindcast
COPY research/pyproject.toml ./

# Demo DB lives at /opt/seed (NOT under /app/data) so the Fly volume
# mounted at /data can seed itself from this snapshot on first boot
# without colliding with build-time content.
COPY data/hindcast-demo.duckdb /opt/seed/hindcast.duckdb

# Entry script bootstraps /data/hindcast.duckdb from the seed if missing.
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENV PATH="/app/research/.venv/bin:$PATH"
ENV CORS_ALLOW_ORIGINS="*"
# Pydantic-settings reads DB_PATH (case-insensitive) into Settings.db_path,
# overriding the default _PROJECT_ROOT/data/hindcast.duckdb.
ENV DB_PATH="/data/hindcast.duckdb"

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

# Single CMD. The FastAPI lifespan spawns the live worker as a daemon
# thread when ENABLE_WORKER=true (set in fly.toml).
CMD ["uvicorn", "hindcast.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
