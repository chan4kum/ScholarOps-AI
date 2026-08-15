#!/usr/bin/env bash
# Local API — loopback only. Do not bind 0.0.0.0 without authentication.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
UVICORN="$ROOT/.venv/bin/uvicorn"
if [[ ! -x "$UVICORN" ]]; then
  echo "Missing $UVICORN — create the venv and pip install -e '.[dev]' first." >&2
  exit 1
fi
exec "$UVICORN" opportunity_intel.main:app --reload --app-dir src --host 127.0.0.1 --port 8000
