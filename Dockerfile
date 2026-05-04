# Hindcast API — read-only dashboard backend container.
# Multi-stage so the runtime image is just python + venv + package + DB.

# --------------------------------------------------------------------
FROM python:3.11-slim AS builder

# uv is the fastest path to install a frozen dep set.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app/research

# pyproject.toml drives uv sync. uv.lock isn't committed in this repo,
# so we let uv re-resolve from the version constraints (still fast).
COPY research/pyproject.toml ./
COPY research/hindcast ./hindcast

RUN uv sync --no-dev

# --------------------------------------------------------------------
FROM python:3.11-slim

WORKDIR /app/research

# Copy the resolved venv from the builder stage.
COPY --from=builder /app/research/.venv ./.venv
COPY --from=builder /app/research/hindcast ./hindcast
COPY research/pyproject.toml ./

# Bake the demo DB into the image. Default config.db_path resolves to
# /app/data/hindcast.duckdb via Path(__file__).parents[2].
COPY data/hindcast-demo.duckdb /app/data/hindcast.duckdb

ENV PATH="/app/research/.venv/bin:$PATH"
# Permissive defaults; override at deploy time for tighter CORS.
ENV CORS_ALLOW_ORIGINS="*"

EXPOSE 8000

# Run uvicorn directly — uv adds startup latency we don't need here.
CMD ["uvicorn", "hindcast.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
