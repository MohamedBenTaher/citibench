# Contract C — Hybrid retrieval

```
retrieve(query: str, config: RetrieveConfig | None = None) -> list[ChunkHit]
```

C1 stub raises `NotImplementedError`. This file freezes the call shape so C2
ingest can implement it without changing callers.

## RetrieveConfig defaults

Values match root `config.yaml` unless noted.

| Field | Default | Notes |
| --- | --- | --- |
| `chunk_size` | 512 | Token window used at ingest. |
| `chunk_overlap` | 64 | Token overlap used at ingest. |
| `embed_model` | `nomic-embed-text-v1.5` | Query prefix `search_query:`. |
| `rerank_model` | `ms-marco-MiniLM-L-12-v2` | FlashRank cross-encoder. |
| `rrf_k` | 60 | Cormack RRF constant. |
| `rerank_pool` | 50 | Fused hits sent to FlashRank. |
| `top_k` | 8 | Hits returned to the generator. |
| `lexical_k` | 50 | Private lexical pool size. |
| `dense_k` | 50 | Private dense pool size. |

Callers pass a full config or `None` (defaults). Partial override objects are
not part of the contract.

## Pipeline

1. Embed the query with `nomic-embed-text-v1.5` and prefix `search_query:`.
2. Dense search: top `dense_k` from pgvector (cosine).
3. Lexical search: top `lexical_k` from Postgres full-text / BM25.
4. Fuse with RRF, `k=60`. Score of doc `d` is
   `sum 1 / (k + rank_i(d))` over lists that contain `d`.
5. Take the top `rerank_pool` (50) fused hits.
6. FlashRank `ms-marco-MiniLM-L-12-v2` scores the 50; keep `top_k` (8).
7. Return `list[ChunkHit]` length `<= top_k`, rank 1-based.

Lexical and dense candidate **pools are private**. They are not fields on
`ChunkHit`, not on `RunTrace.citations`, and not HTTP. Debug them only inside
the retrieve span attributes if a later decision allows it.

## Rerank failure

If FlashRank cannot load or score, do not stop the request and do not invent
scores. Truncate the RRF list to `top_k`, set `rerank_skipped=true` on every
returned `ChunkHit` and on the rerank span / `RunTrace`. Silent fallback is
a contract violation.

## ChunkHit

| Field | Type | Meaning |
| --- | --- | --- |
| `chunk_id` | string | Index id. |
| `doc_id` | string | Manifest id. |
| `score` | float | FlashRank score, or RRF score if skipped. |
| `rank` | int | 1-based after the last stage. |
| `rerank_skipped` | bool | Must match the run-level flag. |
| `text` | string \| null | Null in C1. C2 may fill for generation only. |
| `vector_score` / `fts_score` / `fused_score` / `rerank_score` | float \| null | Stage diagnostics. |
| `title` / `source` / `product` / `doc_type` / `version` / `license` | string \| null | Display metadata from `documents` (C6). |
| `page` | int \| null | Page from the PDF `[page N]` marker. |
| `section` | string \| null | Nearest heading path (`A > B`) or page label. |
| `url` | string \| null | Page URL; anchors are not resolved yet. |

`text` is not a citation. Citations use `ChunkRef.text_ref` (Contract B).
Display metadata is for UI/traces only and is never used for ranking.

## Out of scope

PDF ingest, LangGraph, MCP, connectors, and chat. `retrieve` is a function,
not a graph node, until a later contract says otherwise.
