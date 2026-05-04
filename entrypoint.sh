#!/bin/sh
# Bootstrap the persistent volume on first boot.
#
# Fly mounts an empty volume at /data on first deploy. We seed it from
# the snapshot baked into the image at /opt/seed/. On subsequent boots
# the volume already has the DB and we skip — that's how live trading
# data accumulates across deploys.

set -e

DB_FILE="${DB_PATH:-/data/hindcast.duckdb}"

if [ ! -f "$DB_FILE" ]; then
    echo "[entrypoint] $DB_FILE missing — seeding from /opt/seed/hindcast.duckdb"
    mkdir -p "$(dirname "$DB_FILE")"
    cp /opt/seed/hindcast.duckdb "$DB_FILE"
else
    echo "[entrypoint] $DB_FILE present — keeping existing data"
fi

exec "$@"
