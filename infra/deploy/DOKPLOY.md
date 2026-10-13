# Citebench on Dokploy

Two ways to deploy. **Use Docker Compose** unless you have a specific reason not
to — it gives working service DNS (`db`, `api`, `web`) and runs pgvector, which
Dokploy's managed Postgres does not include.

Everything below assumes the repo `MohamedBenTaher/citibench`, branch `main`.

---

## Path A — Docker Compose (recommended)

`Dokploy → Create Service → Compose`

| Field | Value |
|---|---|
| Provider | `GitHub` |
| Github Account | the account you connected (`Dokploy-…`), not your personal one |
| Repository | `citibench` |
| Branch | `main` |
| **Compose Path** | `docker-compose.dokploy.yml` |
| Trigger Type | `On Push` |
| Watch Paths | `apps/api/*` `apps/web/*` `docker-compose.dokploy.yml` `config.yaml` `pyproject.toml` `uv.lock` |

Then, on the same service:

**Environment tab** — paste these keys (values per your host):

```env
POSTGRES_PASSWORD=<pick-a-strong-one>
POSTGRES_USER=citebench
POSTGRES_DB=citebench
GROQ_API_KEY=<https://console.groq.com/keys>
VITE_API_URL=https://<api-domain>
CORS_ORIGINS=https://<web-domain>
```

> The `db` service reads `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB`,
> and the `api` service builds its `DATABASE_URL` from the same three. Postgres
> applies `POSTGRES_*` only when it first initializes an empty data dir — change
> them after the first deploy only together with wiping the `citebench_pgdata`
> volume (or an `ALTER ROLE`).

> `VITE_API_URL` is a **build argument** — it is compiled into the browser
> bundle. Changing it requires a rebuild, not just a restart.

**Domains tab** — add two domains:

| Domain | Service | Port | Purpose |
|---|---|---|---|
| `<web-domain>` | `web` | `3000` | the reviewer entry point (`/evals`) |
| `<api-domain>` | `api` | `8000` | the browser calls this directly |

`web` talks to `api` internally over Compose DNS (`http://api:8000`), so the API
domain is only needed for the browser. Do **not** expose `db`.

Click **Deploy**.

---

## Path B — three separate Applications

Only if you need them as independent Dokploy apps. Service discovery is manual
here — prefer Path A.

### B1 — `citebench-db`

`Create Service → Application`. Provider: **Docker** (deploy an image, no build).

| Field | Value |
|---|---|
| Provider | `Docker` |
| Docker Image | `pgvector/pgvector:pg16` |

- **Environment**: `POSTGRES_USER=citebench`, `POSTGRES_DB=citebench`, `POSTGRES_PASSWORD=<strong>`
- **Advanced → Volumes**: create a volume `citebench_pgdata` mounted at `/var/lib/postgresql/data`
- No domain.

### B2 — `citebench-api`

`Create Service → Application`. Provider: **GitHub**.

| Field | Value |
|---|---|
| Repository | `citibench` |
| Branch | `main` |
| **Build Path** | `/` |
| Trigger Type | `On Push` |
| Watch Paths | `apps/api/*` `pyproject.toml` `uv.lock` `config.yaml` `citebench/*` |
| **Build Type** | `Dockerfile` |
| **Docker File** | `apps/api/Dockerfile` |
| **Docker Context Path** | `.` |
| **Docker Build Stage** | *(leave empty)* |

> **Build Path must be `/`**, not `/apps/api`. The Dockerfile needs
> `pyproject.toml` + `uv.lock` from the repo root (`uv sync --frozen`), and it
> copies `config.yaml`, `corpus/`, `evals/`, and `citebench/` as well.

- **Environment**:

```env
DATABASE_URL=postgresql://citebench:<POSTGRES_PASSWORD>@<db-host>:5432/citebench
GROQ_API_KEY=<key>
CONFIG_PATH=/app/config.yaml
CORPUS_DIR=/app/corpus
EVAL_STORE_DIR=/app/evals/results
REDTEAM_JSONL=/app/evals/redteam.jsonl
TRACE_STORE_DIR=/tmp/citebench-traces
NOMIC_CACHE_DIR=/tmp/nomic-embed
FLASHRANK_CACHE_DIR=/tmp/flashrank
CORS_ORIGINS=https://<web-domain>
CITEBENCH_MANIFEST=corpus/v0/MANIFEST.md
CITEBENCH_SNAPSHOT_ONLY=1
```

  `<db-host>` is the hostname Dokploy gives the `citebench-db` container on
  `dokploy-network` — check the DB app's container name in Dokploy and use it.

- **Advanced → Volumes**: named volumes at `/tmp/nomic-embed`, `/tmp/flashrank`,
  `/tmp/citebench-traces` (avoid re-downloading the ~0.5 GB ONNX model and
  re-running FlashRank warmup on every deploy).
- **Domain**: `<api-domain>` → port `8000`.

### B3 — `citebench-web`

`Create Service → Application`. Provider: **GitHub**.

| Field | Value |
|---|---|
| Repository | `citibench` |
| Branch | `main` |
| **Build Path** | `/apps/web` |
| Trigger Type | `On Push` |
| Watch Paths | `apps/web/*` |
| **Build Type** | `Dockerfile` |
| **Docker File** | `Dockerfile` |
| **Docker Context Path** | `.` |
| **Docker Build Stage** | *(leave empty)* |

- **Environment**:

```env
API_URL=http://<api-host>:8000
HOST=0.0.0.0
PORT=3000
NITRO_HOST=0.0.0.0
NITRO_PORT=3000
```

- **Environment → Build Time Arguments** (Dockerfile builds only):
  `VITE_API_URL=https://<api-domain>`

  This is the one that matters — it is baked into the browser bundle.
- **Domain**: `<web-domain>` → port `3000`.

---

## After the first deploy: seed the corpus

A fresh database is empty, so `/corpus` reports no documents until you ingest.
The Compose file defaults to the **14-URL offline smoke corpus** so the first
ingest is fast and needs no network.

From the API container (Dokploy → the api service → Open Terminal):

```bash
curl -sS -X POST http://127.0.0.1:8000/ingest -H 'Content-Type: application/json' -d '{}'
```

Or use the **Ingest / Re-index** button on `/corpus`.

First ingest downloads the local embedding model (~0.5 GB) into
`NOMIC_CACHE_DIR`; that is why the cache volume matters.

### Switch to the full 1,487-doc freeze

Set both of these and re-ingest (this fetches ~638 MB over the network and
takes considerably longer):

```env
CITEBENCH_MANIFEST=corpus/MANIFEST.md
CITEBENCH_SNAPSHOT_ONLY=0
```

## Health checks

```bash
curl -sS https://<api-domain>/health          # {"status":"ok"}
curl -sS https://<api-domain>/evals/redteam   # case_count 10
curl -sS https://<web-domain>/evals           # HTML, no login wall
```

## Troubleshooting

- **`/corpus` or `/traces` shows Internal Server Error.** The browser is calling
  the wrong API origin. `VITE_API_URL` must be the *public* API domain and the
  web image must be **rebuilt** after changing it.
- **Ask fails with a CORS error.** `CORS_ORIGINS` must contain the exact web
  origin (`https://<web-domain>`, no trailing slash).
- **`database unavailable: Name or service not known`.** The API cannot resolve
  the DB. On Path A that means the `db` container is unhealthy; on Path B the
  `DATABASE_URL` host is wrong.
- **Ingest returns 401.** `GROQ_API_KEY` is missing/invalid (a *missing* key
  returns 503; a *rejected* key returns 401).
- **The page says "Gotenberg has no UI".** You hit another app on port 3000 —
  Dokploy domains avoid this, so it means the domain is not pointing at `web`.

## Files

- `docker-compose.dokploy.yml` (repo root) — the Compose file Path A uses. It
  mounts no host paths (the api image bakes its assets), only named volumes.
- `infra/deploy/docker-compose.demo.yml` + `Caddyfile` — the non-Dokploy VM
  path (Caddy instead of Traefik). Not used with Dokploy.
- `.dockerignore` (repo root) — keeps the API build context small; the API image
  builds from the repo root.
