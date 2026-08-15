#!/usr/bin/env bash
# Clock helper when n8n is not running. Business logic is in Python.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
exec "$ROOT/.venv/bin/python" -m opportunity_intel.ops.nightly_cli
