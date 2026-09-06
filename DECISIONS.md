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

