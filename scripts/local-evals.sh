#!/usr/bin/env bash
# Run C6 + C8 evals on this machine before any public provision.
# Usage (from anywhere):
#   ./scripts/local-evals.sh           # venv, pytest, mock RAGAS, mock redteam
#   ./scripts/local-evals.sh --live    # same, then live redteam (needs GROQ + ingest)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

LIVE=0
if [[ "${1:-}" == "--live" ]]; then
  LIVE=1
elif [[ -n "${1:-}" ]]; then
  echo "usage: $0 [--live]" >&2
  exit 2
fi

UV="${UV:-uv}"

if [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PY="${ROOT}/.venv/bin/python"
elif command -v "$UV" >/dev/null 2>&1; then
  echo "creating ${ROOT}/.venv with uv"
  "$UV" sync --frozen
  PY="${ROOT}/.venv/bin/python"
else
  echo "uv not found. Install uv (https://docs.astral.sh/uv/) and retry." >&2
  exit 2
fi

echo "interpreter: $PY"

export PYTHONPATH="${ROOT}:${ROOT}/apps/api${PYTHONPATH:+:$PYTHONPATH}"
export EVAL_STORE_DIR="${EVAL_STORE_DIR:-${ROOT}/evals/results}"
export TRACE_STORE_DIR="${TRACE_STORE_DIR:-${TMPDIR:-/tmp}/citebench-traces}"
mkdir -p "$EVAL_STORE_DIR" "$TRACE_STORE_DIR"

echo "== pytest (apps/api) =="
(cd "${ROOT}/apps/api" && "$PY" -m pytest)

echo "== C6 RAGAS mock =="
"$PY" -m citebench.eval.ci \
  --split evals/splits/ci.jsonl \
  --known-bad evals/splits/known_bad.jsonl \
  --threshold-faithfulness 0.7 \
  --mock \
  --store-dir "$EVAL_STORE_DIR"

echo "== C8 redteam mock =="
"$PY" -m citebench.eval.redteam \
  --split evals/redteam.jsonl \
  --mock \
  --store-dir "$EVAL_STORE_DIR"

if [[ "$LIVE" -eq 1 ]]; then
  if [[ -z "${GROQ_API_KEY:-}" ]]; then
    echo "GROQ_API_KEY is required for --live. Skipping live redteam." >&2
    exit 2
  fi
  echo "== C8 redteam live =="
  "$PY" -m citebench.eval.redteam \
    --split evals/redteam.jsonl \
    --live \
    --store-dir "$EVAL_STORE_DIR"
fi

stamp="${EVAL_STORE_DIR}/.local-evals-ok"
{
  echo "utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "mode=$([[ "$LIVE" -eq 1 ]] && echo live || echo mock)"
  echo "interpreter=$PY"
} >"$stamp"

echo
echo "Local evals passed. Stamp: $stamp"
echo "Provision only after this: bash infra/deploy/try-provision.sh"
