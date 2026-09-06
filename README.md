# Citebench

Citebench measures citation-grounded retrieval on a frozen public Kubernetes and Azure corpus.

## Run

```bash
cp -n .env.example .env   # then set GROQ_API_KEY
docker compose up --build
```

- API health: `GET http://localhost:8000/health` → `{"status":"ok"}`
- Web: `http://localhost:3000/` (index plus `/corpus`, `/playground`, `/traces`, `/evals`)
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
published Citebench score. The Evals tab shows the last CI artifact only.

`retrieve` is implemented (C3). `generate` is implemented (C4) as one
LangGraph path: retrieve → generate | abstain. `emit_trace` is implemented
(C5): every generate/ask run writes a `RunTrace` (Langfuse when configured,
local JSON store otherwise).

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
reads `/evals/latest` and shows last scores plus diff vs previous.

```bash
# API tests (includes C6 harness tests)
cd apps/api && pytest
```
