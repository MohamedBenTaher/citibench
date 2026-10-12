# Citebench demo deploy

**Dokploy?** See [`DOKPLOY.md`](DOKPLOY.md) — it has the exact field values for
the Compose service or three separate applications.

**Run C8 evals on your laptop before provisioning a public host.**

```bash
# from the repo root — uses python3, creates .venv, does not use bare `python`
./scripts/local-evals.sh
```

`try-provision.sh` exits 3 until `evals/results/.local-evals-ok` exists.
That stamp is written only after pytest, mock RAGAS, and mock redteam pass.
Do not deploy a demo that has not blocked the 10 redteam cases locally.

**Before tagging a public release**, run the live gate on the full freeze:
`make evals-live` (needs `GROQ_API_KEY` and `.venv-eval` from
`apps/api/requirements-eval.txt`). CI runs the same live gate on `main`/manual
dispatch when the `GROQ_API_KEY` secret is set. Do not publish with a mock
`latest.json`; the live artifact is `evals/results/live.json` (`mode=live`,
`judge_model`, `measured_at`).

Playground (`/playground`) and Evals (`/evals`) are public application
routes. Do not put a login wall in front of Evals only. If you need one
password for a public host, use the optional Caddy `basic_auth` block and
document it (default: user `citebench`, password `citebench`).

**First screenshot:** `/evals` (redteam table or RAGAS scores) or a failing
`/traces` row. Not a Playground chat bubble.

## What this environment could not do

This Cloud Agent VM had no Fly.io, Railway, Render, Azure, or GHCR
credentials and no Docker daemon. **No public demo URL was provisioned.**
Do not invent one. A reviewer must pick a host and click deploy.

## Compose on a VM (preferred)

1. Provision a VM (any cloud) with Docker Engine + Compose plugin.
2. Clone this repo and copy `.env.example` to `.env`.
3. Set `GROQ_API_KEY`. Optional: `CORS_ORIGINS=https://<your-host>`.
4. Start:

```bash
docker compose -f docker-compose.yml -f infra/deploy/docker-compose.demo.yml up --build -d
curl -sS http://127.0.0.1:8000/health
curl -sS http://127.0.0.1:8000/evals/redteam
```

5. Open `http://<vm-ip>/evals` (Caddy) or `http://<vm-ip>:3000/evals`.
6. Ingest the freeze, then ask from Playground if you want live traces.

```bash
curl -sS -X POST http://127.0.0.1:8000/ingest -H 'Content-Type: application/json' -d '{}'
```

Optional password: uncomment `basic_auth` in `infra/deploy/Caddyfile`, hash
`citebench` with `caddy hash-password`, recreate `proxy`.

## Azure Container Apps

Needs `az login` and a subscription. This agent did not have those.

```bash
az group create -n citebench-demo -l eastus
az containerapp env create -n citebench-env -g citebench-demo -l eastus
# Build and push api + web images to a registry you control, then:
az containerapp create -n citebench-web -g citebench-demo --environment citebench-env \
  --image <registry>/citebench-web:c8 --ingress external --target-port 3000 \
  --env-vars API_URL=http://citebench-api VITE_API_URL=<public-api-origin>
az containerapp create -n citebench-api -g citebench-demo --environment citebench-env \
  --image <registry>/citebench-api:c8 --ingress internal --target-port 8000 \
  --env-vars GROQ_API_KEY=<secret> DATABASE_URL=<postgres> \
             EVAL_STORE_DIR=/app/evals/results REDTEAM_JSONL=/app/evals/redteam.jsonl
```

Add a Postgres Flexible Server (pgvector) or run the `db` service on the VM
path above. After ingress is public, the demo URL is the Container App FQDN
+ `/evals`.

## Fly.io / Railway / Render / GHCR

If you have an account:

- **Fly.io:** `fly launch` from the repo (two apps: api + web) or a single
  VM running the Compose overlay. Set `GROQ_API_KEY` as a secret.
- **Railway / Render:** new project from this GitHub repo, Docker Compose
  or two services (`apps/api`, `apps/web`). Inject `GROQ_API_KEY`.
- **GHCR + Compose:** `docker build` both images, `docker push ghcr.io/<org>/citebench-{api,web}:c8`,
  then pull them on a VM with the overlay file.

Click the provider “Deploy” button after secrets are set. The live URL is
whatever hostname the provider prints. Point reviewers at `/evals`.

## Health checks

```bash
curl -sS http://<host>:8000/health          # {"status":"ok"}
curl -sS http://<host>:8000/evals/redteam   # case_count 10
curl -sS http://<host>:3000/evals           # HTML, no login
```
