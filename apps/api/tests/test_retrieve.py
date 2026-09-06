"""Failing-first C3 tests: hybrid RRF merge + FlashRank order on the 5-doc fixture."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from retrieve import (
    ChunkHit,
    FusedChunk,
    RetrieveConfig,
    ScoredChunk,
    retrieve,
    rrf_fuse,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "retrieve_5doc" / "corpus.json"

CONTRACT_HIT_FIELDS = {
    "chunk_id",
    "doc_id",
    "score",
    "rank",
    "rerank_skipped",
    "text",
}
JOB_SCORE_FIELDS = {"vector_score", "fts_score", "fused_score", "rerank_score"}
PRIVATE_POOL_KEYS = {
    "vector_pool",
    "fts_pool",
    "lexical_pool",
    "dense_pool",
    "pools",
}


def load_5doc() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def expected_rrf_order(chunks: list[dict], rrf_k: int) -> list[tuple[str, float]]:
    """Independent Cormack formula from Contract C — not imported from retrieve."""
    scores: dict[str, float] = {}
    dense = sorted(chunks, key=lambda row: row["vector_rank"])
    lexical = sorted(chunks, key=lambda row: row["fts_rank"])
    for rank, row in enumerate(dense, start=1):
        scores[row["chunk_id"]] = scores.get(row["chunk_id"], 0.0) + 1.0 / (rrf_k + rank)
    for rank, row in enumerate(lexical, start=1):
        scores[row["chunk_id"]] = scores.get(row["chunk_id"], 0.0) + 1.0 / (rrf_k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


def fixture_scored(chunks: list[dict], rank_key: str, score_key: str) -> list[ScoredChunk]:
    ordered = sorted(chunks, key=lambda row: row[rank_key])
    return [
        ScoredChunk(
            chunk_id=row["chunk_id"],
            doc_id=row["doc_id"],
            text=row["text"],
            score=row[score_key],
        )
        for row in ordered
    ]


def stub_embed(_query: str) -> list[float]:
    return [0.01] * 768


def stub_vector(chunks: list[dict]):
    pool = fixture_scored(chunks, "vector_rank", "vector_score")

    def _search(_query_vec: list[float], k: int) -> list[ScoredChunk]:
        return pool[:k]

    return _search


def stub_fts(chunks: list[dict]):
    pool = fixture_scored(chunks, "fts_rank", "fts_score")

    def _search(_query: str, k: int) -> list[ScoredChunk]:
        return pool[:k]

    return _search


def stub_rerank(chunks: list[dict]):
    by_id = {row["chunk_id"]: float(row["rerank_score"]) for row in chunks}

    def _rerank(_query: str, hits: list[FusedChunk]) -> list[float]:
        return [by_id[hit.chunk_id] for hit in hits]

    return _rerank


def run_retrieve(fixture: dict, **overrides):
    chunks = fixture["chunks"]
    config = overrides.pop("config", RetrieveConfig())
    return retrieve(
        fixture["query"],
        config,
        embed_query_fn=overrides.pop("embed_query_fn", stub_embed),
        vector_search_fn=overrides.pop("vector_search_fn", stub_vector(chunks)),
        fts_search_fn=overrides.pop("fts_search_fn", stub_fts(chunks)),
        rerank_fn=overrides.pop("rerank_fn", stub_rerank(chunks)),
        **overrides,
    )


def test_fixture_is_five_docs() -> None:
    fixture = load_5doc()
    chunks = fixture["chunks"]
    assert len(chunks) == 5
    assert len({row["doc_id"] for row in chunks}) == 5
    assert fixture["rrf_k"] == 60
    assert fixture["rerank_model"] == "ms-marco-MiniLM-L-12-v2"


def test_rrf_fuse_matches_cormack_k60_on_5doc_fixture() -> None:
    fixture = load_5doc()
    chunks = fixture["chunks"]
    fused = rrf_fuse(
        fixture_scored(chunks, "vector_rank", "vector_score"),
        fixture_scored(chunks, "fts_rank", "fts_score"),
        k=fixture["rrf_k"],
    )
    expected = expected_rrf_order(chunks, fixture["rrf_k"])
    assert [hit.chunk_id for hit in fused] == [chunk_id for chunk_id, _ in expected]
    for hit, (_, score) in zip(fused, expected, strict=True):
        assert hit.fused_score == pytest.approx(score)
    # Vector-best (scheduler) is not FTS-best (pods); RRF must put pods first.
    assert fused[0].chunk_id == "k8s-pods:0"
    assert fused[1].chunk_id == "k8s-scheduler:0"
    assert fused[2].chunk_id == "az-aks-intro:0"
    assert fused[3].chunk_id == "k8s-services:0"
    assert fused[4].chunk_id == "k8s-deployments:0"


def test_retrieve_rerank_reorders_rrf_on_5doc_fixture() -> None:
    fixture = load_5doc()
    hits = run_retrieve(fixture)
    assert [hit.chunk_id for hit in hits] == [
        "az-aks-intro:0",
        "k8s-services:0",
        "k8s-pods:0",
        "k8s-scheduler:0",
        "k8s-deployments:0",
    ]
    assert [hit.rank for hit in hits] == [1, 2, 3, 4, 5]
    assert all(hit.rerank_skipped is False for hit in hits)
    assert [hit.rerank_score for hit in hits] == pytest.approx([0.91, 0.80, 0.55, 0.40, 0.10])
    assert [hit.score for hit in hits] == pytest.approx([0.91, 0.80, 0.55, 0.40, 0.10])
    by_id = {row["chunk_id"]: row for row in fixture["chunks"]}
    expected_fused = dict(expected_rrf_order(fixture["chunks"], fixture["rrf_k"]))
    for hit in hits:
        src = by_id[hit.chunk_id]
        assert hit.text == src["text"]
        assert hit.doc_id == src["doc_id"]
        assert hit.vector_score == pytest.approx(src["vector_score"])
        assert hit.fts_score == pytest.approx(src["fts_score"])
        assert hit.fused_score == pytest.approx(expected_fused[hit.chunk_id])


def test_rerank_failure_keeps_rrf_order_and_sets_skipped() -> None:
    fixture = load_5doc()

    def boom(_query: str, _hits: list[FusedChunk]) -> list[float]:
        raise RuntimeError("FlashRank failed to load")

    hits = run_retrieve(fixture, rerank_fn=boom)
    assert [hit.chunk_id for hit in hits] == [
        "k8s-pods:0",
        "k8s-scheduler:0",
        "az-aks-intro:0",
        "k8s-services:0",
        "k8s-deployments:0",
    ]
    assert all(hit.rerank_skipped is True for hit in hits)
    assert all(hit.rerank_score is None for hit in hits)
    expected_fused = dict(expected_rrf_order(fixture["chunks"], fixture["rrf_k"]))
    for hit in hits:
        assert hit.score == pytest.approx(expected_fused[hit.chunk_id])
        assert hit.fused_score == pytest.approx(expected_fused[hit.chunk_id])


def test_empty_hits_returns_empty_list() -> None:
    fixture = load_5doc()
    hits = run_retrieve(
        fixture,
        vector_search_fn=lambda _vec, _k: [],
        fts_search_fn=lambda _q, _k: [],
        rerank_fn=lambda _q, _hits: [],
    )
    assert hits == []


def test_empty_query_returns_empty_list() -> None:
    hits = retrieve(
        "   ",
        RetrieveConfig(),
        embed_query_fn=stub_embed,
        vector_search_fn=lambda _vec, _k: [],
        fts_search_fn=lambda _q, _k: [],
        rerank_fn=lambda _q, _hits: [],
    )
    assert hits == []


def test_top_k_truncates_after_last_stage() -> None:
    fixture = load_5doc()
    hits = run_retrieve(fixture, config=RetrieveConfig(top_k=3))
    assert [hit.chunk_id for hit in hits] == [
        "az-aks-intro:0",
        "k8s-services:0",
        "k8s-pods:0",
    ]
    assert [hit.rank for hit in hits] == [1, 2, 3]


def test_chunkhit_exposes_contract_and_score_fields() -> None:
    fixture = load_5doc()
    hits = run_retrieve(fixture)
    assert hits
    payload = hits[0].model_dump()
    assert CONTRACT_HIT_FIELDS <= set(payload)
    assert JOB_SCORE_FIELDS <= set(payload)
    assert PRIVATE_POOL_KEYS.isdisjoint(payload)


def test_retrieve_does_not_return_public_pools() -> None:
    fixture = load_5doc()
    hits = run_retrieve(fixture)
    assert isinstance(hits, list)
    assert all(isinstance(hit, ChunkHit) for hit in hits)
    assert not hasattr(hits, "vector_pool")
    assert not hasattr(hits, "fts_pool")
    for hit in hits:
        assert not hasattr(hit, "vector_pool")
        assert not hasattr(hit, "lexical_pool")


def test_health_still_200() -> None:
    from main import app

    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_retrieve_endpoint_503_without_groq_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "")
    from main import app

    response = TestClient(app).post("/retrieve", json={"query": "pods onto nodes"})
    assert response.status_code == 503
    assert "GROQ_API_KEY" in response.text
