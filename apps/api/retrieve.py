"""Hybrid retrieve: embed → pgvector + FTS → RRF (k=60) → FlashRank → top_k.

C3 implements Contract C. Candidate pools stay private.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from pydantic import BaseModel


class RetrieveConfig(BaseModel):
    chunk_size: int = 512
    chunk_overlap: int = 64
    embed_model: str = "nomic-embed-text-v1.5"
    rerank_model: str = "ms-marco-MiniLM-L-12-v2"
    rrf_k: int = 60
    rerank_pool: int = 50
    top_k: int = 8
    lexical_k: int = 50
    dense_k: int = 50


class ChunkHit(BaseModel):
    chunk_id: str
    doc_id: str
    score: float
    rank: int
    rerank_skipped: bool = False
    text: str | None = None
    vector_score: float | None = None
    fts_score: float | None = None
    fused_score: float | None = None
    rerank_score: float | None = None


class ScoredChunk(BaseModel):
    chunk_id: str
    doc_id: str
    text: str
    score: float | None = None


class FusedChunk(BaseModel):
    chunk_id: str
    doc_id: str
    text: str
    vector_score: float | None = None
    fts_score: float | None = None
    fused_score: float = 0.0


class EmbedQueryFn(Protocol):
    def __call__(self, query: str) -> Sequence[float]: ...


class VectorSearchFn(Protocol):
    def __call__(self, query_vec: Sequence[float], k: int) -> Sequence[ScoredChunk]: ...


class FtsSearchFn(Protocol):
    def __call__(self, query: str, k: int) -> Sequence[ScoredChunk]: ...


class RerankFn(Protocol):
    def __call__(self, query: str, hits: Sequence[FusedChunk]) -> Sequence[float]: ...


def rrf_fuse(
    dense: Sequence[ScoredChunk],
    lexical: Sequence[ScoredChunk],
    *,
    k: int = 60,
) -> list[FusedChunk]:
    """Cormack RRF: score(d) = sum 1/(k + rank_i(d)) over lists that contain d."""
    raise NotImplementedError("C3: rrf_fuse")


def retrieve(
    query: str,
    config: RetrieveConfig | None = None,
    *,
    embed_query_fn: EmbedQueryFn | None = None,
    vector_search_fn: VectorSearchFn | None = None,
    fts_search_fn: FtsSearchFn | None = None,
    rerank_fn: RerankFn | None = None,
    settings: object | None = None,
) -> list[ChunkHit]:
    raise NotImplementedError("C3: retrieve")
