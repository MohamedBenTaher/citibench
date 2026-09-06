# Citebench decisions

Arena-binding choices for C1. Later ingest, retrieve, and eval work must follow this file.

## Why Postgres + pgvector

Citebench is a citation bench, not a chat product. The store must be inspectable
SQL, not a hosted vector SaaS. Postgres 16 plus `pgvector` keeps chunks, BM25
payloads, and dense vectors in one process we can dump, freeze, and CI against.
`CREATE EXTENSION vector` is the only C1 database requirement. Hybrid lexical
plus dense retrieval in C2 reads the same tables. We rejected dedicated vector
hosts because they hide the freeze and make known-bad abstention harder to audit.

## Chunk 512 / 64 + Groq + nomic-embed-text-v1.5

Chunk size 512 tokens with overlap 64 is the default in `config.yaml`. That
window is large enough to keep a Kubernetes or Azure concept intact and small
enough that a citation maps to one heading-sized passage. Overlap 64 covers
sentence splits at boundaries without doubling the index.

Embeddings use `nomic-embed-text-v1.5` (768-d, Matryoshka) with the documented
`search_document:` / `search_query:` prefixes. The model is open, local-capable,
and good enough that we do not pay an embed API. Groq is the sole *generation*
provider; embeddings are not Groq-hosted. `chat_model` stays empty in C1.

## Rerank: FlashRank ms-marco-MiniLM-L-12-v2, top-50 → top-8

Hybrid retrieval (Contract C) fuses lexical and dense lists with RRF (`k=60`),
then FlashRank scores the top 50 fused hits with `ms-marco-MiniLM-L-12-v2`
and keeps `top_k=8`. The generator must only see that reranked context.

If FlashRank fails to load or score, the pipeline must not invent order. It
falls back to the RRF list, truncated to 8, and records `rerank_skipped=true`
on the retrieve span and on each `ChunkHit`. Silent skip is a contract violation.

## Why not fine-tune

The frozen corpus is 14 public pages. Fine-tuning an embedder or reranker on
that set would leak eval into the index and manufacture theater scores. We use
off-the-shelf nomic + MiniLM and measure them. Domain adaptation is out of
scope until the corpus and splits are large enough that train/eval leakage can
be proven absent.

## Why Langfuse

Langfuse is the C2+ destination for `RunTrace` (Contract B): one trace per
query, spans `retrieve → rerank → generate|abstain`, plus cost. C1 does not
run Langfuse in Compose and does not require a cloud key. `emit_trace` is a
stub. We still chose Langfuse now so span names, `text_ref` citations, and
cost fields do not get redesigned when observability lands.

## Why Groq is the sole LLM

One billed generation provider. Groq is fast enough for playground iteration
and cheap enough for RAGAS batches. We do not add OpenAI, Anthropic, or local
chat models in C1–C2. Embeddings and rerank stay local/open. `provider: groq`
and empty `chat_model` in `config.yaml` make that explicit: no chat surface
ships until a model id is filled by a later change.

## Corpus freeze (Kubernetes + Azure)

Freeze date **2026-09-05**. Policy: public Kubernetes.io concept pages and
public Microsoft Learn Azure pages only. Fourteen URLs are pinned in
`corpus/MANIFEST.md`. No PDFs, no private runbooks, no InnovX or Acme fixtures
in the index. Re-freeze requires a new date, a full URL list, and a decision-
trail row. Ingest itself is C2.

## Arena references

- Cormack et al., Reciprocal Rank Fusion, SIGIR 2009 (`k=60`).
- FlashRank / `cross-encoder/ms-marco-MiniLM-L-12-v2`.
- nomic-ai/nomic-embed-text-v1.5 model card (prefixes, 768-d).
- pgvector extension on Postgres 16.
- RAGAS faithfulness (CI gate 0.7, not a published C1 score).
- Langfuse trace/span mapping in Contract B.
- Kubernetes and Azure public documentation licenses (CC BY 4.0).

## Eval framework: RAGAS 0.7 + known_bad anti-theater

Faithfulness threshold **0.7** is a *future CI gate only*. C1 ships no RAGAS
run and no metric dashboards. The first executable split is
`evals/splits/known_bad.jsonl`: questions whose answers are not in the freeze
(InnovX passwords, Acme payroll). Any concrete answer is a failure. Abstention
is required. This exists so later RAGAS numbers cannot hide retrieval theater.

Loaders, retrieve, and emit_trace remain `NotImplemented` in `docs/contracts/stubs/schemas.py` until C2.

## C2 ingest binding (2026-09-06)

C2 is snapshot → parse → chunk → embed → pgvector only. The 14 MANIFEST URLs
are the only allowed sources. Each snapshot lands in `corpus/raw/<id>/` with
`sha256` on the `documents` row and in a companion `sha256` file.

Chunk boundaries use tiktoken `cl100k_base` at 512 / 64 so re-index is stable.
Embeddings call Groq's OpenAI-compatible `/embeddings` with
`nomic-embed-text-v1.5` (768-d) and `GROQ_API_KEY`. If the key is missing, ingest
fails with setup instructions. There is no second embed provider.

`retrieve` and `emit_trace` stay `NotImplemented`. Hybrid retrieve, rerank,
Langfuse, Playground ask, and eval CI are out of scope for this slice.

## C3 retrieve binding (2026-09-06)

C3 implements Contract C only. `retrieve(query, config=None)` embeds the query
with Groq `nomic-embed-text-v1.5` and prefix `search_query:`, pulls private
pgvector (`dense_k` / `vector_k`) and Postgres FTS (`lexical_k` / `fts_k`)
pools, fuses them with Cormack RRF `k=60`, then FlashRank
`ms-marco-MiniLM-L-12-v2` scores the top `rerank_pool` / `rerank_input_k` (50)
and keeps `top_k=8`.

`ChunkHit` carries Contract C fields plus `vector_score`, `fts_score`,
`fused_score`, and `rerank_score`. Pools are not public. If FlashRank cannot
load or score, the RRF list is truncated to `top_k` and every hit has
`rerank_skipped=true` (testable with an injected `RerankFn`). Empty hits
return `[]`. Missing `GROQ_API_KEY` on the embed path is HTTP 503.

LangGraph generate/abstain, Langfuse, eval CI, MCP, Playground ask UI,
connectors, a second reranker, and a second embed vendor stay out of scope.

## C4 generate binding (2026-09-06)

C4 is one LangGraph path: `retrieve` (the C3 function) → `generate` XOR
`abstain`. No second provider, no node editor, no chat homepage.

Default chat model is Groq production `llama-3.1-8b-instant`
(https://console.groq.com/docs/models). Override with `GROQ_CHAT_MODEL`.

Abstain policy (enforced in `apps/api/generate.py`):

1. `empty_retrieve` — no hits, including a blank query. No chat call.
2. `low_confidence` — FlashRank ran and the top hit score is below
   `abstain_min_score` (default 0.12). Not applied when `rerank_skipped`
   (RRF scores are a different scale).
3. `out_of_corpus` — the model sets `abstain: true` or answers "I don't know".
4. `ungrounded` — the model answered but no `citation_ids` remain after
   intersecting with retrieved chunk ids. Fabricated ids are dropped; an
   uncited answer is not served.

Abstain answer is exactly `I don't know`. Citations are `ChunkRef` rows
(`text_ref` = `doc_id#chunk_id`) and are empty when abstaining.

Cost uses Contract B `CostEstimate`. Method string `citebench.cost.v1` encodes
the rates and the formula
`(prompt*prompt_usd_per_1m + completion*completion_usd_per_1m + embed*embed_usd_per_1m)/1e6`.
`rerank_tokens` is 0 (local FlashRank). Rates live in `config.yaml` so the
estimate is reproducible without Langfuse (C5).

Playground (`/playground`) is the ask UI. `/` stays an index.

## C5 traces binding (2026-09-06)

C5 implements Contract B `emit_trace`. Langfuse is the named backend. The
Traces tab is a thin local view, not a second tracer product.

Every generate/ask run builds one `RunTrace` with the required tree
`retrieve → rerank → generate|abstain`. `text_ref` is `doc_id#chunk_id`.
Chunk bodies stay in Postgres. Extra run fields required by the job
(`model`, `tokens_in`/`tokens_out`, `latency_ms`, `cost_method`) sit on
`RunTrace` next to Contract B `cost`.

Langfuse SDK posts `name=citebench.run`, child spans named by `span.kind`,
citation `text_ref`s on output metadata, `CostEstimate` + method on
metadata, and `rerank_skipped` as a score. Configure
`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_HOST` (cloud or
`http://langfuse:3000` for the optional Compose profile). If keys are unset
or Langfuse errors, `emit_trace` keeps the in-memory/local JSON store and
leaves `langfuse_trace_id` null so `/traces` still works.

Eval CI is C6. `/metrics` README numbers are C7. MCP, connectors, a chat
homepage, and an analytics product stay out of scope.

## C6 eval CI binding (2026-09-06)

C6 is RAGAS only (not DeepEval). Entrypoint:

`python -m citebench.eval.ci --split evals/splits/ci.jsonl --known-bad evals/splits/known_bad.jsonl --threshold-faithfulness 0.7`

Order is fail-closed: load JSONL (Contract A, no skipped invalid rows) →
execute `known_bad.jsonl` in full → RAGAS on non-abstain CI rows. The job
fails if the loader errors, if a known_bad row *passes* the naive success
assert (concrete answer / fabricated cite / generate without abstain), or if
mean faithfulness is below 0.7. Known-bad asserts stay real even when CI
uses the fixture judge because Groq is unavailable.

Companion metrics (context precision, answer relevancy) are written to
`evals/results/latest.json` and shown on the Evals tab with a diff vs
`previous.json`. They do not gate CI. C7 may quote that artifact only with
its `mode` (mock vs live). Failing rows call C5 `emit_trace` into the local
store.

Live mode (`--live` / `GROQ_API_KEY`) may call `generate` plus the ragas
library. MCP, redteam deploy, and dual eval frameworks stay out of scope.

## C7 metrics binding (2026-09-06)

C7 is `GET /metrics` and a README table that only prints numbers we can
reproduce. JSON is the default scrape; `?format=prometheus` is the text
scrape. Null means unmeasured, not zero.

Latency p50/p95 is linear interpolation over `RunTrace.latency_ms` where
`latency_ms > 0` (C5 local store + memory). Empty store → `null`.
TODO(C7): p95 unmeasured — no `GROQ_API_KEY`, no live generate sample.

Cost per 1k queries is `mean(CostEstimate.usd_estimate) * 1000` over traces
with a billed cost (`usd_estimate > 0` or any token count > 0). Rates are
`citebench.cost.v1` in `config.yaml` (Groq `llama-3.1-8b-instant`, nomic
embed table, FlashRank $0). TODO(C7): cost/1k unmeasured for the same
reason. The method string is still on the scrape.

Faithfulness is `metrics.faithfulness` on the last
`evals/results/latest.json`, with `mode`. The committed artifact is
`mode=mock` (fixture RAGAS judge, `evals/splits/ci.jsonl`, 3 rows):
faithfulness 1.0, context precision 0.833. Tag:
`measured-under-mock-ragas-judge`. Not a live ragas/Groq number. The CI
gate stays 0.7. Missing file → `null`.

Corpus: 14 MANIFEST URLs (freeze 2026-09-05). Pages = 1 per HTML snapshot.
Chunks = tiktoken `cl100k_base` 512 / 64. No frozen `corpus/raw` sha256
tree and no pgvector ingest in this environment, so chunks were counted
from a live HTML fetch on 2026-09-06: 148, tagged
`measured-under-live-html-fetch-2026-09-06` in `evals/results/corpus.json`.
After ingest, `/metrics` prefers `/corpus/stats`.

C1–C5 bindings are unchanged: Postgres 16 + pgvector, chunk 512 / 64,
FlashRank MiniLM top-50 → top-8, no fine-tune on the 14-page freeze,
Langfuse as the named trace backend, Groq as the only generation provider.

C8 redteam + deploy is this slice. A chat homepage and connectors stay
out of scope. C9 is the thin MCP only.

## C8 redteam + demo binding (2026-09-06)

C8 is a 10-row Contract A split and a public demo path. It is not a
security product and not MCP.

`evals/redteam.jsonl` is exactly ten rows. Each row includes the `redteam`
tag, `attack_type` ∈ {injection, pii_leak, jailbreak}, and `expect_block`.
`expect_block` true implies `abstain` true and `must_cite` false. The mix
must include all three attack types. Extra loader fields landed with a
decision-trail row; CI / known-bad rows omit them.

Runner: `python -m citebench.eval.redteam --split evals/redteam.jsonl`.
Mock reuses the C6 generate/abstain empty-retrieve path (no Groq). Live
calls `generate`. A block is `not naive_success_assert` (abstain, no
concrete answer, no citations). The job is not the RAGAS 0.7 gate. Leaks
emit a C5 `RunTrace`. Artifact `evals/results/redteam.json` is shown on
the Evals tab above RAGAS.

Playground and Evals stay public. No login wall that hides Evals. A single
optional demo password (`citebench` / `citebench` on the Caddy overlay) is
documented in `infra/deploy/README.md` and the README. First demo
screenshot is `/evals` or a failing trace, not a chat bubble.

Deploy is best-effort. Compose overlay lives in `infra/deploy/`. Azure
Container Apps, Fly, Railway, Render, and GHCR are runbook-only unless
credentials exist. Do not invent a demo URL. C9 is the thin MCP only.

## C9 MCP binding (2026-09-06)

C9 is two MCP tools over the running Compose API. It is not a marketplace,
not a connector platform, and not a new UI.

stdio JSON-RPC (`python -m citebench.mcp`). `CITEBENCH_API_URL` defaults
to `http://localhost:8000`.

1. `search_corpus` — wraps `POST /retrieve` (C3 hybrid). Argument: `query`.
2. `get_trace` — wraps `GET /traces/{id}` (C5 local store). Argument:
   `run_id`, which may be the Citebench run id or `langfuse_trace_id`
   when that field is present.

No third tool. No agent catalog. No Dify-style platform. No chat
homepage. Runbook: `docs/mcp.md`. Smoke:
`python -m citebench.mcp --smoke` (protocol) and `--smoke --live` (API).

## TanStack Start instead of Next.js (2026-09-06)

The four product tabs were already client islands plus a thin BFF over
FastAPI. Next.js App Router added RSC/document-reload ceremony we were
not using: `/` is a boring index, Playground is one ask, and Evals is a
public last-run table. That is a navigation-and-loader problem, not an
App Router problem.

TanStack Start keeps SSR for first paint and same-origin server
functions, but tab switches are TanStack Router transitions with
`preload: intent`, typed `?run_id=` search, and pending/error
boundaries. No login wall on Playground or Evals. FastAPI contracts
are unchanged. Compose `web` still binds :3000 and proxies with
server-only `API_URL=http://api:8000` for GET loaders; browser ask/ingest
use `VITE_API_URL` (Compose build-arg, default `http://localhost:8000`)
because Nitro aborts POST server-function bodies. That is the
`NEXT_PUBLIC_API_URL` rename.

The four product tabs use **shadcn/ui** on the Start/Vite path
(`npx shadcn@latest init --template start --preset nova`), not a Next.js
App Router install. Nova + Tailwind v4 + Base UI primitives: nav buttons,
cards, tables, form controls, alerts, and Sonner toasts. No login wall.
`next-themes` is not required.

Rejected: rewriting the LangGraph pipeline, chat-as-homepage, a second
component library, or inventing demo metrics. C8/C9 bindings stay.

