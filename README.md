# Citebench

Citebench is a **citation-grounded retrieval bench**, not a chat product.

It answers questions about a **frozen public corpus** (14 Kubernetes and Azure docs) and scores whether those answers stay grounded. If the corpus cannot support the question, the system must **abstain** — not invent a password, a payroll row, or a citation.

The homepage is an index. The interesting surfaces are **Corpus**, **Playground**, **Traces**, and **Evals**. First screenshot for a reviewer: `/evals` or a failing `/traces` row, not a chat bubble.

## How it fits together

```
  14 pinned public URLs (corpus/MANIFEST.md, freeze 2026-09-05)
                 │
                 ▼
         ingest ──► Postgres 16 + pgvector
                 │     chunks (512 / 64, tiktoken cl100k_base)
                 │     dense (Groq nomic-embed-text-v1.5) + FTS
                 ▼
         retrieve ──► RRF (k=60) ──► FlashRank top-50 → top-8
                 │
                 ▼
         generate | abstain   (Groq llama-3.1-8b-instant, LangGraph)
                 │
                 ├── RunTrace (Langfuse or local JSON)
                 ├── /metrics  (p50/p95, cost/1k, last eval)
                 └── evals     (RAGAS gate 0.7 + 10 redteam cases)
```

| Piece | Role |
| --- | --- |
| `apps/api` | FastAPI: health, ingest, retrieve, generate, traces, evals, metrics |
| `apps/web` | Next.js App Router: `/` index plus four tabs |
| `db` | `pgvector/pgvector:pg16` — inspectable SQL, not a hosted vector SaaS |
| `citebench.eval` | RAGAS CI + redteam runners |
| `citebench.mcp` | Two tools: `search_corpus`, `get_trace` |
| `config.yaml` | Chunking, models, `top_k`, faithfulness threshold |

Groq is the only billed LLM. Embed + chat share `GROQ_API_KEY`. Langfuse is optional; missing keys fall back to a local trace store so `/traces` still works.

## Quick start

You need Docker (Compose) and Python 3.12+. A Groq key is required for ingest, retrieve, and generate ([console.groq.com/keys](https://console.groq.com/keys)).

```bash
make setup          # .env + .venv + pip install
# edit .env → GROQ_API_KEY=...
make start          # api :8000, web :3000, Postgres
make ingest         # index the 14 MANIFEST URLs
```

Open [http://localhost:3000/](http://localhost:3000/) (index), then `/corpus`, `/playground`, `/traces`, `/evals`.

If the page says **“Gotenberg has no UI, it's an API”**, that is [Gotenberg](https://gotenberg.dev/) (PDF conversion), not Citebench. It also binds **:3000**. Confirm Citebench with `curl -sS localhost:8000/health` → `{"status":"ok"}`. Then either stop Gotenberg (`docker ps | grep -i gotenberg`) or start Citebench on another port:

```bash
# stop the other container, or:
WEB_PORT=3100 make start
# open http://localhost:3100/
```

Equivalent without Make:

```bash
cp -n .env.example .env
docker compose up --build
curl -sS -X POST http://localhost:8000/ingest -H 'Content-Type: application/json' -d '{}'
```

| Make target | What it does |
| --- | --- |
| `make setup` | Copy `.env`, create `.venv`, install `apps/api` + pytest |
| `make start` | `docker compose up --build -d`, wait for `/health` (`WEB_PORT=3100` if :3000 is taken) |
| `make ingest` | `POST /ingest` |
| `make evals` | Local pytest + mock RAGAS + mock redteam (run before provision) |
| `make test` | Pytest only, via `.venv` |
| `make status` / `logs` / `stop` / `down` | Health, follow logs, stop stack |

Do **not** run bare `pytest` on system Python (`No module named 'fastapi'`). macOS often has `python3` and no `python`. Use `make evals` or `.venv/bin/python -m pytest apps/api`.

## What each tab is

| Route | What you see |
| --- | --- |
| `/` | Boring index. Not a chat homepage. |
| `/corpus` | Freeze + counts. Ingest / re-index the 14 public docs. |
| `/playground` | Ask UI: answer, citations, abstain, latency, estimated cost. Still not a chat product. |
| `/traces` | One `RunTrace` per ask: retrieve → rerank → generate\|abstain. |
| `/evals` | Last RAGAS artifact + 10 redteam cases. Public; no login wall. |

## Pipeline

**Ingest** fetches the pinned URLs, chunks at 512/64, embeds with `search_document:`, writes pgvector + FTS. Snapshots land in `corpus/raw/<id>/` with sha256.

**Retrieve** embeds the query with `search_query:`, fuses dense + lexical lists with RRF, then FlashRank (`ms-marco-MiniLM-L-12-v2`) keeps 8 hits. If rerank fails, order stays RRF and `rerank_skipped` is set — never a silent skip.

**Generate** is one LangGraph path: retrieve, then answer with citations **or** abstain (`I don't know`). Citations are always a subset of retrieved chunk ids. Empty retrieve, low FlashRank score, or ungrounded output → abstain.

```bash
curl -sS http://localhost:8000/health
curl -sS http://localhost:8000/corpus/stats
curl -sS -X POST http://localhost:8000/retrieve \
  -H 'Content-Type: application/json' \
  -d '{"query":"how does the kube-scheduler place pods onto nodes"}'
curl -sS -X POST http://localhost:8000/generate \
  -H 'Content-Type: application/json' \
  -d '{"query":"how does the kube-scheduler place pods onto nodes"}'
```

## Evals and redteam

Run these **on your laptop** before any public provision (`try-provision.sh` exits 3 until they pass).

```bash
make evals
# or:  ./scripts/local-evals.sh
# live redteam after compose + ingest + GROQ_API_KEY:
./scripts/local-evals.sh --live
```

- **Known-bad** (`evals/splits/known_bad.jsonl`) — InnovX passwords / Acme payroll. Any concrete answer fails.
- **RAGAS CI** — mean faithfulness **≥ 0.7** on `evals/splits/ci.jsonl`. That 0.7 is a CI gate, not a published product score.
- **Redteam** — exactly 10 cases in `evals/redteam.jsonl` (injection / pii_leak / jailbreak). A pass is a **block**: abstain, no cite, no leak.

GitHub Actions (`.github/workflows/eval-ci.yml`) runs pytest + mock RAGAS + mock redteam on `main` and PRs.

## Numbers (honest)

Counted from this repo, or tagged with the measurement. An em dash means we did not measure it — not that the value is zero.

| Metric | Value | Method |
| --- | --- | --- |
| Corpus docs | 14 | Pinned URLs in `corpus/MANIFEST.md` (freeze 2026-09-05). |
| Corpus pages | 14 | One HTML snapshot is one page. All 14 URLs are HTML. |
| Corpus chunks | 148 | `measured-under-live-html-fetch-2026-09-06`. tiktoken 512/64. After ingest, prefer `GET /corpus/stats`. |
| Faithfulness | 1.000 | `measured-under-mock-ragas-judge` on 3 CI rows. Fixture judge, not a live Groq/RAGAS run. Gate is 0.7. |
| Context precision | 0.833 | Same mock artifact (`evals/results/latest.json`). |
| p95 latency | — | Unmeasured until traces with `latency_ms > 0` exist. |
| Cost / 1k queries | — | Unmeasured. When traces exist: mean `citebench.cost.v1` USD × 1000. |

```bash
curl -sS http://localhost:8000/metrics
curl -sS 'http://localhost:8000/metrics?format=prometheus'
```

## MCP

Two tools over the Compose API. Not a marketplace. See `docs/mcp.md`.

```bash
make mcp-smoke
# after make start:
export CITEBENCH_API_URL=http://localhost:8000 PYTHONPATH=.
.venv/bin/python -m citebench.mcp --smoke --live
.venv/bin/python -m citebench.mcp          # stdio server
```

## Repo map

```
apps/api/           FastAPI + ingest/retrieve/generate/trace
apps/web/           Next.js tabs
citebench/eval/     RAGAS + redteam CLIs
citebench/mcp/      search_corpus + get_trace
corpus/MANIFEST.md  Frozen 14-URL list
evals/              ci.jsonl, known_bad.jsonl, redteam.jsonl, results/
docs/contracts/     Eval / trace / hybrid-retrieve contracts
infra/deploy/       Demo Compose overlay + Caddy
config.yaml         Models and knobs
DECISIONS.md        Why this stack
```

## Deploy

No public URL ships with the repo. After `make evals` locally, see `infra/deploy/README.md`. Playground and Evals stay public application routes.

```bash
make evals
make start
bash infra/deploy/try-provision.sh
```

Optional Langfuse (UI at http://localhost:3001):

```bash
# in .env
LANGFUSE_PUBLIC_KEY=pk-lf-citebench-dev
LANGFUSE_SECRET_KEY=sk-lf-citebench-dev
LANGFUSE_HOST=http://langfuse:3000
docker compose --profile langfuse up --build
```

## Further reading

- `DECISIONS.md` — Postgres, chunking, rerank, Groq-only, freeze, anti-theater
- `docs/contracts/` — eval JSONL, traces, hybrid retrieve
- `docs/mcp.md` — MCP host config
- `infra/deploy/README.md` — VM / Fly / Railway / Azure
