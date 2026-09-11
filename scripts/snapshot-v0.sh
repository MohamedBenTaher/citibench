#!/usr/bin/env bash
# Fetch the corpus-v0 smoke snapshots (14 URLs) into corpus/v0/raw/.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "No .venv found. Run 'make setup' first." >&2
  exit 2
fi
exec "$PY" "$ROOT/apps/api/snapshot_v0.py" "$@"
