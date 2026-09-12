#!/usr/bin/env bash
# Live evals: collect real answers (runtime env), score with RAGAS (eval env),
# then run the live redteam.
#
#   ./scripts/live-evals.sh              # all rows
#   ./scripts/live-evals.sh --limit 4    # smoke (first 4 rows)
#
# ragas lives in .venv-eval (see apps/api/requirements-eval.txt) because it
# conflicts with the runtime's pinned langgraph. Traces from the live generate
# calls land in TRACE_STORE_DIR, so /metrics (or collect_metrics) can report
# real p95 / cost afterward.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
PY_EVAL="$ROOT/.venv-eval/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "No .venv found. Run 'make setup' first." >&2
  exit 2
fi
if [[ ! -x "$PY_EVAL" ]]; then
  echo "No .venv-eval found. Create it and install apps/api/requirements-eval.txt." >&2
  exit 2
fi

if [[ -z "${GROQ_API_KEY:-}" && -f "$ROOT/.env" ]]; then
  GROQ_API_KEY="$(grep -E '^GROQ_API_KEY=' "$ROOT/.env" | head -1 | cut -d= -f2-)"
  export GROQ_API_KEY
fi
if [[ -z "${GROQ_API_KEY:-}" ]]; then
  echo "GROQ_API_KEY is required for live evals" >&2
  exit 2
fi

LOG_DIR="${LIVE_LOG_DIR:-${TMPDIR:-/tmp}/citebench-live}"
mkdir -p "$LOG_DIR"
export EVAL_STORE_DIR="${EVAL_STORE_DIR:-$ROOT/evals/results}"
export TRACE_STORE_DIR="${TRACE_STORE_DIR:-$LOG_DIR/traces}"
export PYTHONPATH="$ROOT:$ROOT/apps/api"
ANSWERS="$LOG_DIR/answers.jsonl"

echo "== collect live answers (runtime env) =="
"$PY" -m citebench.eval.answers --out "$ANSWERS" "$@"

echo "== live RAGAS scoring (eval env) =="
"$PY_EVAL" -m citebench.eval.live_score \
  --answers "$ANSWERS" \
  --out "$EVAL_STORE_DIR/live.json" \
  --threshold 0.7

echo "== live redteam (runtime env) =="
"$PY" -m citebench.eval.redteam \
  --split evals/redteam.jsonl --live --store-dir "$EVAL_STORE_DIR"

echo "live evals done: artifact $EVAL_STORE_DIR/live.json, traces $TRACE_STORE_DIR"
