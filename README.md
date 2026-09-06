# Citebench

Citebench measures citation-grounded retrieval on a frozen public Kubernetes and Azure corpus.

## Numbers

Counted from this repo, or tagged with the measurement. An em dash means
we did not measure it here — not that the value is zero.

| Metric | Value | Method |
| --- | --- | --- |
| Corpus docs | 14 | Pinned URLs in `corpus/MANIFEST.md` (freeze 2026-09-05). |
| Corpus pages | 14 | One HTML snapshot is one page (`parse_doc`). All 14 URLs are HTML. |
| Corpus chunks | 148 | `measured-under-live-html-fetch-2026-09-06`. tiktoken `cl100k_base` 512/64 on pages fetched that day, recorded in `evals/results/corpus.json`. Not the frozen 2026-09-05 sha256 snapshots (those are not in git). Counts move if the public pages change. After ingest, prefer `GET /corpus/stats`. |
| Faithfulness | 1.000 | `measured-under-mock-ragas-judge`. Mean on `evals/splits/ci.jsonl` (3 rows) from `evals/results/latest.json` (`mode=mock`). Fixture judge, not a live ragas/Groq run. The CI gate is 0.7; this is not a published product score. |
| Context precision | 0.833 | Same mock artifact as faithfulness. Exact value in `latest.json` is `0.8333…`. |
| p95 latency | — | Unmeasured. No live Groq generate sample in this environment. `GET /metrics` returns `null` until traces with `latency_ms > 0` exist. |
| Cost / 1k queries | — | Unmeasured. Same reason. When traces exist: mean `citebench.cost.v1` USD × 1000. Rates are in `config.yaml`. |

```bash
curl -sS http://localhost:8000/metrics
curl -sS 'http://localhost:8000/metrics?format=prometheus'
```

## Run

```bash
cp -n .env.example .env   # then set GROQ_API_KEY
docker compose up --build
```

- API health: `GET http://localhost:8000/health` → `{"status":"ok"}`
- Web: `http://localhost:3000/` (index plus `/corpus`, `/playground`, `/traces`, `/evals`)
- Playground and Evals are public application routes. There is no login wall
  that hides Evals. Optional single demo password (Caddy overlay): user
  `citebench` / password `citebench` — see `infra/deploy/README.md`.
- **First screenshot:** `/evals` (redteam table or last RAGAS run) or a
  failing `/traces` row. Not a Playground chat bubble.
- Database: Postgres 16 with pgvector (`CREATE EXTENSION vector`)

Langfuse is optional. Unset keys or a down host fail soft to a local
`RunTrace` store so the Traces tab still works. Cloud:

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com   # or https://us.cloud.langfuse.com
```

Self-host (optional Compose profile; UI at http://localhost:3001):

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-citebench-dev
LANGFUSE_SECRET_KEY=sk-lf-citebench-dev
LANGFUSE_HOST=http://langfuse:3000
docker compose --profile langfuse up --build
```

## Ingest (C2)

Set `GROQ_API_KEY` (https://console.groq.com/keys). Embeddings use only Groq
`nomic-embed-text-v1.5` via the OpenAI-compatible API.

```bash
# idempotent re-index of the 14 MANIFEST URLs
curl -sS -X POST http://localhost:8000/ingest -H 'Content-Type: application/json' -d '{}'

# optional wipe + reload
curl -sS -X POST http://localhost:8000/ingest -H 'Content-Type: application/json' -d '{"wipe":true}'

# stats (same counts as the Corpus tab)
curl -sS http://localhost:8000/corpus/stats
```

Or open `/corpus` and click **Ingest / Re-index**. Snapshots go to
`corpus/raw/<id>/` with `sha256` recorded on `documents.sha256` and in
`corpus/raw/<id>/sha256`.

## Config

See `config.yaml`. Chunking is 512 tokens / 64 overlap with tiktoken
`cl100k_base`. `faithfulness_threshold: 0.7` is the C6 RAGAS CI gate, not a
published Citebench score. The Evals tab shows the last CI artifact and the
C8 redteam table.

`retrieve` is implemented (C3). `generate` is implemented (C4) as one
LangGraph path: retrieve → generate | abstain. `emit_trace` is implemented
(C5): every generate/ask run writes a `RunTrace` (Langfuse when configured,
local JSON store otherwise). `GET /metrics` is implemented (C7). MCP is
implemented (C9): two tools, `search_corpus` and `get_trace` — see
`docs/mcp.md`.

## Retrieve (C3)

Hybrid search over the ingested chunks. Query embed uses Groq
`nomic-embed-text-v1.5` with prefix `search_query:` (same `GROQ_API_KEY`;
**503** if missing). Dense + FTS lists are fused with RRF `k=60`, then
FlashRank `ms-marco-MiniLM-L-12-v2` reranks the top 50 and returns `top_k=8`.

```bash
curl -sS -X POST http://localhost:8000/retrieve \
  -H 'Content-Type: application/json' \
  -d '{"query":"how does the kube-scheduler place pods onto nodes"}'
```

FlashRank loads `ms-marco-MiniLM-L-12-v2` once per process into
`FLASHRANK_CACHE_DIR` (default `/tmp/flashrank`). If rerank fails to load or
score, the response keeps RRF order and sets `rerank_skipped` on every hit.

Unit tests use the 5-doc fixture at `apps/api/tests/fixtures/retrieve_5doc/`
and inject embed / search / `RerankFn` stubs (no live Groq).

## Generate (C4)

One LangGraph path. `retrieve()` runs first; then the graph routes to
**generate** (answer + citations) or **abstain** (`I don't know`). Chat is
Groq only (`llama-3.1-8b-instant` in `config.yaml`, override `GROQ_CHAT_MODEL`).
Missing `GROQ_API_KEY` on `POST /generate` is **503**; `/health` stays 200.

```bash
curl -sS -X POST http://localhost:8000/generate \
  -H 'Content-Type: application/json' \
  -d '{"query":"how does the kube-scheduler place pods onto nodes"}'
```

Playground tab (`/playground`) is the ask UI: answer, citations, abstain
path, latency, and `citebench.cost.v1` estimated cost. `/` stays an index.

Citations are always a subset of retrieved chunk ids. Empty retrieve, low
FlashRank confidence, out-of-corpus model abstain, and ungrounded (no valid
cites) all abstain. Policy is in `apps/api/generate.py` and `DECISIONS.md`.

## Traces (C5)

Every `POST /generate` / Playground ask emits one `RunTrace` via `emit_trace`.
Span tree is retrieve → rerank → generate|abstain. Citations use `text_ref`
(`doc_id#chunk_id`), not chunk bodies. Cost is `citebench.cost.v1` (USD +
method). Langfuse mapping: trace `name=citebench.run`, spans named by
`span.kind`, citations and cost in metadata, `rerank_skipped` as a score.

```bash
curl -sS http://localhost:8000/traces
curl -sS http://localhost:8000/traces/<run_id>
```

The Traces tab lists one row per run. Click a row for retrieval and
generation/abstain spans. If Langfuse keys are missing or the host is down,
the same tab reads the local store (`TRACE_STORE_DIR`, default
`/tmp/citebench-traces`).

## Evals (C6)

RAGAS CI gate. Known-bad runs first and must fail the naive success assert
(abstain). Then `evals/splits/ci.jsonl` is scored. The job fails on loader
errors, an unclean known-bad phase, or mean **faithfulness < 0.7**.
Context precision and answer relevancy are logged, not gates.

```bash
# CI default: fixture RAGAS judge + real known-bad fail-closed (no Groq)
python -m citebench.eval.ci \
  --split evals/splits/ci.jsonl \
  --known-bad evals/splits/known_bad.jsonl \
  --threshold-faithfulness 0.7 \
  --mock

# Live Groq generate + ragas library (requires GROQ_API_KEY)
python -m citebench.eval.ci \
  --split evals/splits/ci.jsonl \
  --known-bad evals/splits/known_bad.jsonl \
  --threshold-faithfulness 0.7 \
  --live
```

GitHub Actions workflow `.github/workflows/eval-ci.yml` runs `pytest` then
this command with `--mock` on `main` and pull requests. Score artifact:
`evals/results/latest.json` (previous run rotated to `previous.json`).
Failing rows emit a C5 `RunTrace` into `TRACE_STORE_DIR`. The Evals tab
reads `/evals/latest` and `/evals/redteam` (public; no login). It shows
last RAGAS scores plus the 10 C8 redteam cases.

```bash
# API tests (includes C6 and C8 harness tests) — use the repo venv
./scripts/local-evals.sh
# or:  .venv/bin/python -m pytest apps/api
```

## Redteam (C8)

Exactly 10 Contract A rows in `evals/redteam.jsonl`. Each row has `tags`
including `redteam`, plus `attack_type` (`injection` / `pii_leak` /
`jailbreak`) and `expect_block`. The runner reuses the generate → abstain
path (mock: empty retrieve, no Groq).

```bash
# from repo root, with .venv (not `cd apps/api`; not bare `python`)
./scripts/local-evals.sh

# or, after `source .venv/bin/activate`:
python -m citebench.eval.redteam --split evals/redteam.jsonl --mock
python -m citebench.eval.redteam --split evals/redteam.jsonl --live
```

A pass is a block: abstain, no concrete answer, no citations. Leaks write a
C5 `RunTrace`. Artifact: `evals/results/redteam.json`. This is not the RAGAS
0.7 gate.

## Local evals before provision (C8)

Run evals on your laptop before `try-provision.sh` or any public host.
System Python will fail collection (`No module named 'fastapi'` / `tiktoken`).
macOS often has `python3` and no `python`. Use the script from the **repo
root**, not `apps/api`:

```bash
./scripts/local-evals.sh          # .venv + pytest + mock RAGAS + mock redteam
# after compose up, ingest, and GROQ_API_KEY:
./scripts/local-evals.sh --live
```

Equivalent by hand:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r apps/api/requirements-dev.txt
cd apps/api && pytest && cd ../..
python3 -m citebench.eval.redteam --split evals/redteam.jsonl --mock
```

`infra/deploy/try-provision.sh` exits 3 until
`evals/results/.local-evals-ok` exists (`--force` skips that gate).

## Demo URL

No public URL is shipped from this change unless you deploy it. This
environment had no Fly/Railway/Render/Azure/GHCR credentials.

What you must click: follow `infra/deploy/README.md` (Compose on a VM, or
Azure Container Apps / Fly / Railway / Render). After the host is up, open
`/evals` first. Optional password: `citebench` / `citebench`.

```bash
./scripts/local-evals.sh   # required first
docker compose -f docker-compose.yml -f infra/deploy/docker-compose.demo.yml up --build
bash infra/deploy/try-provision.sh   # exits 3 if local evals missing; 2 if no cloud creds
```

## Metrics (C7)

`GET /metrics` is JSON by default. `?format=prometheus` is the text scrape.

- **p50 / p95 latency** — traces with `latency_ms > 0`
- **cost / 1k** — mean billed `CostEstimate.usd_estimate` × 1000
- **faithfulness** — last eval artifact, including `mode`
- **corpus** — pgvector stats if indexed, else `evals/results/corpus.json`, else MANIFEST docs/pages

Null means “not measured yet,” not zero.

## MCP (C9)

Two tools against the Compose API. Not a marketplace and not extra
connectors. Full run notes: `docs/mcp.md`.

```bash
export CITEBENCH_API_URL=http://localhost:8000
export PYTHONPATH=.
python -m citebench.mcp --smoke          # protocol only
python -m citebench.mcp --smoke --live   # after docker compose up
python -m citebench.mcp                  # stdio server
```
