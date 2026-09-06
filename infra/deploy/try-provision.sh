#!/usr/bin/env bash
# Best-effort public URL. Exits 2 when this environment cannot deploy.
# Exits 3 when local C8 evals have not been run on this machine.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FORCE=0
if [[ "${1:-}" == "--force" ]]; then
  FORCE=1
fi

stamp="${EVAL_STORE_DIR:-${ROOT}/evals/results}/.local-evals-ok"
if [[ "$FORCE" -eq 0 && ! -f "$stamp" ]]; then
  cat <<EOF
Local C8 evals have not been run on this machine.

Do this first (laptop, not a fresh VM):

  ./scripts/local-evals.sh

That creates .venv, installs apps/api deps, runs pytest, mock RAGAS,
and mock redteam. Then re-run this provisioner.

Override only if you mean it: $0 --force
EOF
  exit 3
fi

echo "citebench demo provisioner"
if [[ -f "$stamp" ]]; then
  echo "local evals stamp: $stamp"
  cat "$stamp"
fi
echo "checking for cloud credentials..."

found=0
for name in FLY_API_TOKEN FLY_ACCESS_TOKEN RAILWAY_TOKEN RENDER_API_KEY \
            AZURE_CLIENT_ID ARM_CLIENT_ID GHCR_TOKEN GHCR_PAT; do
  if [[ -n "${!name:-}" ]]; then
    echo "  found $name"
    found=1
  fi
done

if command -v flyctl >/dev/null 2>&1 || command -v fly >/dev/null 2>&1; then
  echo "  found fly CLI"
  found=1
fi
if command -v railway >/dev/null 2>&1; then
  echo "  found railway CLI"
  found=1
fi
if command -v render >/dev/null 2>&1; then
  echo "  found render CLI"
  found=1
fi
if command -v az >/dev/null 2>&1; then
  echo "  found az CLI"
  found=1
fi

if [[ "$found" -eq 0 ]]; then
  cat <<'EOF'
No Fly.io, Railway, Render, Azure, or GHCR credentials in this environment.
Demo URL was not provisioned.

What you must click:
  1. Create a VM or a Fly/Railway/Render/Azure app.
  2. Set GROQ_API_KEY (and optional DEMO_PASSWORD=citebench).
  3. Run the Compose overlay in infra/deploy/README.md
     or paste that README into the provider deploy UI.
  4. Open https://<your-host>/evals — first screenshot is Evals, not chat.

EOF
  exit 2
fi

echo "Credentials exist. Follow infra/deploy/README.md for the provider you have."
exit 0
