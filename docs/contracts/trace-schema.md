# Contract B — Trace schema

One `RunTrace` per user question. C1 defines the types and `emit_trace`.
Nothing is emitted at runtime. Langfuse is not in Compose.

## RunTrace

| Field | Type | Meaning |
| --- | --- | --- |
| `run_id` | string | UUID or ulid. Unique per attempt. |
| `query` | string | Exact question text. |
| `started_at` | datetime | UTC start. |
| `finished_at` | datetime | UTC end. Must be >= `started_at`. |
| `spans` | list[Span] | Tree ordered retrieve → rerank → generate\|abstain. |
| `citations` | list[ChunkRef] | Chunks actually used. Empty when abstaining. |
| `abstained` | bool | True iff the terminal span is `abstain`. |
| `cost` | CostEstimate | Token and USD estimate. Zeros allowed in C1. |
| `langfuse_trace_id` | string \| null | Set only after `emit_trace` succeeds. |
| `rerank_skipped` | bool | True if FlashRank was bypassed (see Contract C). |

Invariants: if `abstained` then `citations` is empty and no `generate` span
exists. If not `abstained` then exactly one `generate` span exists and
`citations` is non-empty when the eval row has `must_cite=true`.

## ChunkRef (`text_ref`, not payload)

| Field | Type | Meaning |
| --- | --- | --- |
| `chunk_id` | string | Stable id inside the frozen index. |
| `doc_id` | string | Manifest `id` (`k8s-pods`, `az-aks-intro`, …). |
| `text_ref` | string | Pointer only: `doc_id#chunk_id` or equivalent. |
| `score` | float \| null | Rerank score, or RRF score if `rerank_skipped`. |
| `rank` | int \| null | 1-based rank after the last ranking stage. |

`text_ref` must not embed the chunk body. Traces stay small; the body lives
in Postgres after C2 ingest. UI and Langfuse render by resolving `text_ref`.

## CostEstimate

| Field | Type | Meaning |
| --- | --- | --- |
| `prompt_tokens` | int | Generation prompt tokens. |
| `completion_tokens` | int | Generation completion tokens. |
| `embed_tokens` | int | Query embedding tokens. |
| `rerank_tokens` | int | Optional; 0 if unused or unknown. |
| `usd_estimate` | float | Non-negative. 0.0 when no Groq call ran. |

All ints are >= 0. `usd_estimate` is an estimate, not a billing export.

## Span tree

`Span.kind` is one of: `retrieve`, `rerank`, `generate`, `abstain`.

Required shape:

```
retrieve
  └─ rerank          # always present; may set rerank_skipped
       ├─ generate   # XOR
       └─ abstain    # XOR
```

| Field | Type | Meaning |
| --- | --- | --- |
| `span_id` | string | Unique inside the run. |
| `parent_id` | string \| null | Null on retrieve. |
| `kind` | enum | See above. |
| `started_at` / `finished_at` | datetime | UTC. |
| `status` | `ok` \| `error` | Error does not authorize silent rerank skip. |
| `attributes` | dict | Kind-specific. Must include `rerank_skipped` on rerank. |

A retrieve error fails the run. A rerank error sets `rerank_skipped=true`
and continues with RRF order (Contract C). A generate error is a failed run,
not an implicit abstain. Abstain is an explicit kind.

## Langfuse map

| Citebench | Langfuse |
| --- | --- |
| `RunTrace` | Trace (`name=citebench.run`, input=`query`) |
| `Span` | Span (`name=span.kind`) |
| `ChunkRef.text_ref` | Output metadata `citations` |
| `CostEstimate` | Trace metadata `cost` |
| `rerank_skipped` | Score / metadata flag, never hidden |

C1 does not configure a Langfuse host. Mapping is frozen so C2 does not
rename kinds.

## `emit_trace`

```
emit_trace(trace: RunTrace) -> None
```

Validates the tree, then (C2+) posts to Langfuse and sets
`langfuse_trace_id`. C1 stub raises `NotImplementedError`. Callers must not
swallow that error by dropping the in-memory `RunTrace`.
