#!/usr/bin/env bash
# Sync FDP data into a remote Supabase Postgres database.
#
# Usage:
#   export DATABASE_URL="postgresql://postgres.[ref]:[password]@aws-1-us-east-2.pooler.supabase.com:5432/postgres"
#   bash scripts/sync_supabase.sh

set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "ERROR: DATABASE_URL is not set." >&2
    echo "Set it to your Supabase connection string before running this script." >&2
    exit 1
fi

echo "==> Creating FDP schema..."
uv run fdp init-db

echo "==> Loading registered parquets..."
uv run fdp load-pg

echo "==> Supabase sync complete."
