"""Failing-first C3 tests: hybrid RRF merge + FlashRank order on the 5-doc fixture."""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from citebench_api.retrieval.retrieve import (
    ChunkHit,
    FusedChunk,
    RetrieveConfig,
    ScoredChunk,
    hybrid_search,
    retrieve,
    rrf_fuse,
)
from test_generate import make_settings

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


def test_rrf_sums_only_lists_that_contain_the_doc() -> None:
    dense = [ScoredChunk(chunk_id="only-dense", doc_id="d", text="x", score=0.9)]
    lexical = [ScoredChunk(chunk_id="only-fts", doc_id="f", text="y", score=0.8)]
    fused = rrf_fuse(dense, lexical, k=60)
    by_id = {hit.chunk_id: hit for hit in fused}
    assert by_id["only-dense"].fused_score == pytest.approx(1.0 / 61)
    assert by_id["only-dense"].fts_score is None
    assert by_id["only-fts"].fused_score == pytest.approx(1.0 / 61)
    assert by_id["only-fts"].vector_score is None


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


def test_retrieve_works_without_groq_key_when_embed_injected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "")
    hits = retrieve(
        "pods onto nodes",
        RetrieveConfig(),
        embed_query_fn=lambda _q: [0.0] * 768,
        vector_search_fn=lambda _vec, _k: [],
        fts_search_fn=lambda _q, _k: [],
        rerank_fn=lambda _q, _hits: [],
    )
    assert hits == []


def test_retrieve_endpoint_without_groq_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "")
    import main as main_mod

    monkeypatch.setattr("citebench_api.routes.ask.retrieve", lambda *_args, **_kwargs: [])
    response = TestClient(main_mod.app).post("/retrieve", json={"query": "pods onto nodes"})
    assert response.status_code == 200
    assert response.json()["hits"] == []
    assert "GROQ_API_KEY" not in response.text


class _FakeCursor:
    def fetchall(self) -> list:
        return []


class _FakeConn:
    def __init__(self) -> None:
        self.executes: list[tuple[str, tuple | None]] = []

    def execute(self, sql: str, params=None) -> _FakeCursor:
        self.executes.append((sql.strip(), params))
        return _FakeCursor()


def test_hybrid_search_runs_vector_then_fts_on_same_connection() -> None:
    conn = _FakeConn()
    dense, lexical = hybrid_search(
        conn,
        [0.1] * 768,
        "pods onto nodes",
        dense_k=50,
        lexical_k=50,
    )
    assert dense == []
    assert lexical == []
    assert len(conn.executes) == 2
    assert "embedding <=>" in conn.executes[0][0]
    assert "ts_rank_cd" in conn.executes[1][0]


def test_default_retrieve_opens_one_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    enter_count = 0

    class _DummyConn:
        def execute(self, *_args, **_kwargs) -> _FakeCursor:
            raise RuntimeError("search failed on dummy connection")

        def commit(self) -> None:
            return None

        def rollback(self) -> None:
            return None

        def close(self) -> None:
            return None

    @contextmanager
    def counting_connect(_database_url: str):
        nonlocal enter_count
        enter_count += 1
        yield _DummyConn()

    monkeypatch.setattr("citebench_api.retrieval.retrieve.connect", counting_connect)

    with pytest.raises(RuntimeError, match="search failed on dummy connection"):
        retrieve(
            "pods onto nodes",
            RetrieveConfig(),
            settings=make_settings(),
            embed_query_fn=stub_embed,
        )

    assert enter_count == 1


def test_retrieve_module_does_not_import_ensure_schema() -> None:
    import citebench_api.retrieval.retrieve as retrieve_mod

    assert not hasattr(retrieve_mod, "ensure_schema")


def test_scored_from_row_carries_display_metadata() -> None:
    from citebench_api.retrieval.retrieve import _scored_from_row

    row = {
        "id": "k8s-pods:0",
        "doc_id": "k8s-pods",
        "text": "A Pod is the smallest deployable unit.",
        "vector_score": 0.75,
        "title": "Pods",
        "source": "kubernetes.io",
        "product": "Kubernetes",
        "doc_type": "concept",
        "version": "v0-2026-09-10",
        "license": "CC BY 4.0",
        "page": 2,
        "section": "A > B",
        "url": "https://kubernetes.io/docs/concepts/workloads/pods/",
    }
    scored = _scored_from_row(row, "vector_score")
    assert scored.score == pytest.approx(0.75)
    assert scored.product == "Kubernetes"
    assert scored.section == "A > B"
    assert scored.page == 2
    assert scored.license == "CC BY 4.0"


def test_rerank_disabled_skips_without_calling_rerank() -> None:
    fixture = load_5doc()
    calls: list[int] = []

    def recorder(_query: str, hits: list[FusedChunk]) -> list[float]:
        calls.append(len(hits))
        return [0.0] * len(hits)

    hits = run_retrieve(
        fixture,
        config=RetrieveConfig(rerank_enabled=False, top_k=3),
        rerank_fn=recorder,
    )
    assert calls == []
    assert hits
    assert all(hit.rerank_skipped for hit in hits)
    assert all(hit.rerank_score is None for hit in hits)


def test_filter_sql_is_parameterized() -> None:
    from citebench_api.retrieval.retrieve import Filters, _filter_sql

    assert _filter_sql(None) == ("", [])
    assert _filter_sql(Filters()) == ("", [])

    clause, params = _filter_sql(Filters(product="Kubernetes", doc_type="concept"))
    assert "d.product = %s" in clause
    assert "d.doc_type = %s" in clause
    assert params == ["Kubernetes", "concept"]

    clause2, params2 = _filter_sql(Filters(doc_ids=["a", "b"], section="Pods"))
    assert "d.id = ANY(%s)" in clause2
    assert "c.section = %s" in clause2
    assert params2 == ["Pods", ["a", "b"]]

    clause3, params3 = _filter_sql(Filters(product="O'Brien"))
    assert "O'Brien" not in clause3
    assert params3 == ["O'Brien"]


def test_rerank_failure_records_error_stage() -> None:
    fixture = load_5doc()
    sink: list[dict] = []

    def boom(_query: str, _hits: list[FusedChunk]) -> list[float]:
        raise RuntimeError("FlashRank failed to load")

    hits = run_retrieve(fixture, rerank_fn=boom, stage_sink=sink)
    assert all(hit.rerank_skipped for hit in hits)
    rerank_stages = [stage for stage in sink if stage["kind"] == "rerank"]
    assert rerank_stages
    assert rerank_stages[-1]["status"] == "error"
    assert rerank_stages[-1]["attributes"]["rerank_skipped"] is True
