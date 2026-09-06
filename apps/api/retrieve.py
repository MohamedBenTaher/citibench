"""Hybrid retrieve: embed → pgvector + FTS → RRF (k=60) → FlashRank → top_k.

C3 implements Contract C. Candidate pools stay private.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any, Protocol

from pydantic import BaseModel

from db import connect, ensure_schema
from embed import embed_query
from rerank import flashrank_rerank
from settings import Settings, load_settings

log = logging.getLogger("citebench.retrieve")


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


def retrieve_config_from_settings(settings: Settings) -> RetrieveConfig:
    return RetrieveConfig(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        embed_model=settings.embed_model,
        rerank_model=settings.rerank_model,
        rrf_k=settings.rrf_k,
        rerank_pool=settings.rerank_pool,
        top_k=settings.top_k,
        lexical_k=settings.lexical_k,
        dense_k=settings.dense_k,
    )


def rrf_fuse(
    dense: Sequence[ScoredChunk],
    lexical: Sequence[ScoredChunk],
    *,
    k: int = 60,
) -> list[FusedChunk]:
    """Cormack RRF: score(d) = sum 1/(k + rank_i(d)) over lists that contain d."""
    fused_scores: dict[str, float] = {}
    by_id: dict[str, FusedChunk] = {}

    def _upsert(hit: ScoredChunk, *, kind: str) -> None:
        current = by_id.get(hit.chunk_id)
        if current is None:
            current = FusedChunk(
                chunk_id=hit.chunk_id,
                doc_id=hit.doc_id,
                text=hit.text,
            )
            by_id[hit.chunk_id] = current
        match kind:
            case "vector":
                current.vector_score = hit.score
            case "fts":
                current.fts_score = hit.score
            case _:
                raise ValueError(f"unknown score kind: {kind}")

    for rank, hit in enumerate(dense, start=1):
        _upsert(hit, kind="vector")
        fused_scores[hit.chunk_id] = fused_scores.get(hit.chunk_id, 0.0) + 1.0 / (k + rank)
    for rank, hit in enumerate(lexical, start=1):
        _upsert(hit, kind="fts")
        fused_scores[hit.chunk_id] = fused_scores.get(hit.chunk_id, 0.0) + 1.0 / (k + rank)

    fused = [
        by_id[chunk_id].model_copy(update={"fused_score": score})
        for chunk_id, score in fused_scores.items()
    ]
    fused.sort(key=lambda item: (-item.fused_score, item.chunk_id))
    return fused


def retrieve(
    query: str,
    config: RetrieveConfig | None = None,
    *,
    embed_query_fn: EmbedQueryFn | None = None,
    vector_search_fn: VectorSearchFn | None = None,
    fts_search_fn: FtsSearchFn | None = None,
    rerank_fn: RerankFn | None = None,
    settings: Settings | None = None,
    stage_sink: list[dict[str, Any]] | None = None,
) -> list[ChunkHit]:
    cfg = config or (retrieve_config_from_settings(settings) if settings is not None else RetrieveConfig())
    query_text = (query or "").strip()
    retrieve_started = datetime.now(timezone.utc)
    if not query_text:
        _record_empty_stages(stage_sink, retrieve_started, rerank_model=cfg.rerank_model)
        return []

    embed_fn = embed_query_fn or _default_embed(settings)
    vector_fn = vector_search_fn or _default_vector(settings)
    fts_fn = fts_search_fn or _default_fts(settings)
    rank_fn = rerank_fn or flashrank_rerank

    try:
        query_vec = embed_fn(query_text)
        dense = list(vector_fn(query_vec, cfg.dense_k))
        lexical = list(fts_fn(query_text, cfg.lexical_k))
    except Exception as exc:
        now = datetime.now(timezone.utc)
        _append_stage(
            stage_sink,
            kind="retrieve",
            started_at=retrieve_started,
            finished_at=now,
            status="error",
            attributes={"error": str(exc), "hit_count": 0, "chunks": []},
        )
        _append_stage(
            stage_sink,
            kind="rerank",
            started_at=now,
            finished_at=now,
            status="error",
            attributes={"rerank_skipped": True, "rerank_model": cfg.rerank_model, "error": str(exc)},
        )
        raise

    if not dense and not lexical:
        now = datetime.now(timezone.utc)
        _record_empty_stages(stage_sink, retrieve_started, rerank_model=cfg.rerank_model)
        return []

    fused = rrf_fuse(dense, lexical, k=cfg.rrf_k)
    pool = fused[: cfg.rerank_pool]
    rerank_started = datetime.now(timezone.utc)
    rerank_skipped = False
    rerank_status = "ok"
    rerank_error: str | None = None
    rerank_scores: list[float] | None = None
    try:
        rerank_scores = [float(score) for score in rank_fn(query_text, pool)]
        if len(rerank_scores) != len(pool):
            raise RuntimeError("rerank score count does not match the fused pool")
    except Exception as exc:
        rerank_skipped = True
        rerank_status = "error"
        rerank_error = str(exc)
        log.warning("FlashRank failed; falling back to RRF order: %s", exc)

    if rerank_skipped:
        hits = [
            _to_hit(item, rank=rank, skipped=True, score=item.fused_score, rerank_score=None)
            for rank, item in enumerate(pool[: cfg.top_k], start=1)
        ]
    else:
        assert rerank_scores is not None
        paired = sorted(
            zip(pool, rerank_scores, strict=True),
            key=lambda item: (-item[1], item[0].chunk_id),
        )
        hits = [
            _to_hit(item, rank=rank, skipped=False, score=score, rerank_score=score)
            for rank, (item, score) in enumerate(paired[: cfg.top_k], start=1)
        ]

    retrieve_finished = datetime.now(timezone.utc)
    _append_stage(
        stage_sink,
        kind="retrieve",
        started_at=retrieve_started,
        finished_at=retrieve_finished,
        status="ok",
        attributes={
            "hit_count": len(hits),
            "dense_k": cfg.dense_k,
            "lexical_k": cfg.lexical_k,
            "chunks": _chunk_pointers(hits),
        },
    )
    rerank_attrs: dict[str, Any] = {
        "rerank_skipped": rerank_skipped,
        "rerank_model": cfg.rerank_model,
        "pool_size": len(pool),
        "top_k": cfg.top_k,
        "chunks": _chunk_pointers(hits),
    }
    if rerank_error:
        rerank_attrs["error"] = rerank_error
    _append_stage(
        stage_sink,
        kind="rerank",
        started_at=rerank_started,
        finished_at=retrieve_finished,
        status=rerank_status,
        attributes=rerank_attrs,
    )
    return hits


def _chunk_pointers(hits: Sequence[ChunkHit]) -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": hit.chunk_id,
            "doc_id": hit.doc_id,
            "text_ref": f"{hit.doc_id}#{hit.chunk_id}",
            "score": hit.score,
            "rank": hit.rank,
        }
        for hit in hits
    ]


def _append_stage(
    sink: list[dict[str, Any]] | None,
    *,
    kind: str,
    started_at: datetime,
    finished_at: datetime,
    status: str,
    attributes: dict[str, Any],
) -> None:
    if sink is None:
        return
    sink.append(
        {
            "kind": kind,
            "started_at": started_at,
            "finished_at": finished_at,
            "status": status,
            "attributes": attributes,
        }
    )


def _record_empty_stages(
    sink: list[dict[str, Any]] | None,
    started: datetime,
    *,
    rerank_model: str,
) -> None:
    finished = datetime.now(timezone.utc)
    _append_stage(
        sink,
        kind="retrieve",
        started_at=started,
        finished_at=finished,
        status="ok",
        attributes={"hit_count": 0, "chunks": []},
    )
    _append_stage(
        sink,
        kind="rerank",
        started_at=finished,
        finished_at=finished,
        status="ok",
        attributes={"rerank_skipped": True, "rerank_model": rerank_model, "pool_size": 0},
    )


def _to_hit(
    item: FusedChunk,
    *,
    rank: int,
    skipped: bool,
    score: float,
    rerank_score: float | None,
) -> ChunkHit:
    return ChunkHit(
        chunk_id=item.chunk_id,
        doc_id=item.doc_id,
        score=score,
        rank=rank,
        rerank_skipped=skipped,
        text=item.text,
        vector_score=item.vector_score,
        fts_score=item.fts_score,
        fused_score=item.fused_score,
        rerank_score=rerank_score,
    )


def _require_settings(settings: Settings | None) -> Settings:
    return settings if settings is not None else load_settings()


def _default_embed(settings: Settings | None) -> EmbedQueryFn:
    resolved = _require_settings(settings)

    def _embed(query: str) -> list[float]:
        return embed_query(query, resolved)

    return _embed


def _default_vector(settings: Settings | None) -> VectorSearchFn:
    resolved = _require_settings(settings)

    def _search(query_vec: Sequence[float], k: int) -> list[ScoredChunk]:
        with connect(resolved.database_url) as conn:
            ensure_schema(conn)
            return search_vector(conn, query_vec, k)

    return _search


def _default_fts(settings: Settings | None) -> FtsSearchFn:
    resolved = _require_settings(settings)

    def _search(query: str, k: int) -> list[ScoredChunk]:
        with connect(resolved.database_url) as conn:
            ensure_schema(conn)
            return search_fts(conn, query, k)

    return _search


def search_vector(conn, query_vec: Sequence[float], k: int) -> list[ScoredChunk]:
    if k <= 0:
        return []
    literal = _vector_literal(query_vec)
    rows = conn.execute(
        """
        SELECT id, doc_id, text,
               1 - (embedding <=> %s::vector) AS vector_score
        FROM chunks
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> %s::vector, id
        LIMIT %s
        """,
        (literal, literal, k),
    ).fetchall()
    return [
        ScoredChunk(
            chunk_id=row["id"],
            doc_id=row["doc_id"],
            text=row["text"],
            score=float(row["vector_score"]) if row["vector_score"] is not None else None,
        )
        for row in rows
    ]


def search_fts(conn, query: str, k: int) -> list[ScoredChunk]:
    if k <= 0 or not query.strip():
        return []
    rows = conn.execute(
        """
        SELECT id, doc_id, text,
               ts_rank_cd(tsv, plainto_tsquery('english', %s)) AS fts_score
        FROM chunks
        WHERE tsv IS NOT NULL
          AND tsv @@ plainto_tsquery('english', %s)
        ORDER BY fts_score DESC, id
        LIMIT %s
        """,
        (query, query, k),
    ).fetchall()
    return [
        ScoredChunk(
            chunk_id=row["id"],
            doc_id=row["doc_id"],
            text=row["text"],
            score=float(row["fts_score"]) if row["fts_score"] is not None else None,
        )
        for row in rows
    ]


def _vector_literal(values: Sequence[float]) -> str:
    return "[" + ",".join(f"{float(x):.8f}" for x in values) + "]"
