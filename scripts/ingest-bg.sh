#!/usr/bin/env bash
# Low-priority incremental ingest for the frozen corpus.
#
# Runs in the background with a small ONNX thread count and `nice` so it does
# not compete with interactive work. Every document is committed, so it is safe
# to stop at any time; re-run to resume.
#
#   ./scripts/ingest-bg.sh              # start (default 2 threads, ~2 cores)
#   tail -f /tmp/citebench-run/ingest-incremental.log
#   pkill -f ingest_incremental.py      # stop
#
# Tune with env vars: BATCH, DOC_PAUSE, CYCLE_PAUSE, THREADS, LOG.
# THREADS=1 is the gentlest (~1 core); THREADS=4 is ~2x faster (~4 cores).
# Note: `taskpolicy -b` (macOS background QoS) throttles this workload ~10x,
# so it is NOT used by default; set BG_QOS=1 if you want it anyway.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "No .venv found. Run 'make setup' first." >&2
  exit 2
fi

BATCH="${BATCH:-10}"
DOC_PAUSE="${DOC_PAUSE:-0.2}"
CYCLE_PAUSE="${CYCLE_PAUSE:-2}"
THREADS="${THREADS:-2}"
BG_QOS="${BG_QOS:-0}"
LOG="${LOG:-/tmp/citebench-run/ingest-incremental.log}"
mkdir -p "$(dirname "$LOG")"

export CITEBENCH_SNAPSHOT_ONLY=1
export CITEBENCH_INGEST_PAUSE="$DOC_PAUSE"
export FASTEMBED_THREADS="$THREADS"

if [[ "$BG_QOS" == "1" ]] && command -v taskpolicy >/dev/null 2>&1; then
  LAUNCH=(taskpolicy -b nice -n 10)
else
  LAUNCH=(nice -n 10)
fi

nohup "${LAUNCH[@]}" "$PY" "$ROOT/scripts/ingest_incremental.py" \
  --batch "$BATCH" --cycle-pause "$CYCLE_PAUSE" >>"$LOG" 2>&1 &
echo "started pid=$! log=$LOG (batch=$BATCH threads=$THREADS doc_pause=${DOC_PAUSE}s)"
