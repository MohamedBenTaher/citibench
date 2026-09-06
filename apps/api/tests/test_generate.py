"""C4 generate: citations ⊆ retrieved ids, abstain on empty / OOD / low-confidence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from chat import ChatResult, _result_from_payload
from generate import (
    ABSTAIN_ANSWER,
    COST_METHOD_NAME,
    ChunkRef,
    CostEstimate,
    cost_method_string,
    estimate_usd,
    generate,
    parse_model_payload,
    refs_for_ids,
    retrieve_abstain_reason,
)
from retrieve import ChunkHit, RetrieveConfig
from settings import Settings

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "retrieve_5doc" / "corpus.json"
KNOWN_BAD = Path(__file__).resolve().parents[3] / "evals" / "splits" / "known_bad.jsonl"


def load_5doc() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def make_settings(**overrides) -> Settings:
    values = dict(
        provider="groq",
        embed_model="nomic-embed-text-v1.5",
        embed_dimensions=768,
        embed_api_base="https://api.groq.com/openai/v1",
        embed_document_prefix="search_document: ",
        chunk_size=512,
        chunk_overlap=64,
        tokenizer="cl100k_base",
        database_url="postgresql://citebench:citebench@127.0.0.1:5432/citebench",
        corpus_dir=Path("."),
        manifest_path=Path("MANIFEST.md"),
        groq_api_key="gsk_test",
        chat_model="llama-3.1-8b-instant",
        abstain_min_score=0.12,
        chat_prompt_usd_per_1m=0.05,
        chat_completion_usd_per_1m=0.08,
        embed_usd_per_1m=0.01,
    )
    values.update(overrides)
    return Settings(**values)


def fixture_hits(fixture: dict) -> list[ChunkHit]:
    ordered = sorted(fixture["chunks"], key=lambda row: -row["rerank_score"])
    return [
        ChunkHit(
            chunk_id=row["chunk_id"],
            doc_id=row["doc_id"],
            score=row["rerank_score"],
            rank=rank,
            rerank_skipped=False,
            text=row["text"],
            rerank_score=row["rerank_score"],
        )
        for rank, row in enumerate(ordered, start=1)
    ]


def stub_retrieve(hits: list[ChunkHit]):
    def _fn(_query: str) -> list[ChunkHit]:
        return hits

    return _fn


def stub_chat(payload: dict, *, prompt_tokens: int = 20, completion_tokens: int = 12):
    calls: list[list[dict[str, str]]] = []

    def _fn(messages: list[dict[str, str]]) -> ChatResult:
        calls.append(messages)
        return ChatResult(
            content=json.dumps(payload),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    _fn.calls = calls  # type: ignore[attr-defined]
    return _fn


def run_generate(fixture: dict | None = None, **overrides):
    fixture = fixture or load_5doc()
    hits = overrides.pop("hits", fixture_hits(fixture))
    chat_payload = overrides.pop(
        "chat_payload",
        {
            "abstain": False,
            "answer": "kube-scheduler filters and scores nodes, then binds the pod.",
            "citation_ids": ["k8s-scheduler:0", "k8s-pods:0"],
        },
    )
    return generate(
        overrides.pop("query", fixture["query"]),
        retrieve_fn=overrides.pop("retrieve_fn", stub_retrieve(hits)),
        chat_fn=overrides.pop("chat_fn", stub_chat(chat_payload)),
        settings=overrides.pop("settings", make_settings()),
        config=overrides.pop("config", RetrieveConfig()),
        **overrides,
    )


def test_cite_path_citation_ids_subset_of_retrieved() -> None:
    fixture = load_5doc()
    hits = fixture_hits(fixture)
    result = run_generate(fixture, hits=hits)
    retrieved = {hit.chunk_id for hit in hits}
    cited = {ref.chunk_id for ref in result.citations}
    assert cited
    assert cited <= retrieved
    assert result.abstained is False
    assert result.terminal == "generate"
    assert result.path == ["retrieve", "generate"]
    assert result.answer != ABSTAIN_ANSWER
    assert all(ref.text_ref == f"{ref.doc_id}#{ref.chunk_id}" for ref in result.citations)


def test_fabricated_citation_id_is_dropped() -> None:
    fixture = load_5doc()
    hits = fixture_hits(fixture)
    result = run_generate(
        fixture,
        hits=hits,
        chat_payload={
            "abstain": False,
            "answer": "Scheduler places pods using filters and scores.",
            "citation_ids": ["k8s-scheduler:0", "invented-chunk", "not-in-index"],
        },
    )
    cited = [ref.chunk_id for ref in result.citations]
    assert cited == ["k8s-scheduler:0"]
    assert "invented-chunk" not in cited
    assert set(cited) <= {hit.chunk_id for hit in hits}
    assert result.abstained is False


def test_only_fabricated_citations_abstain_ungrounded() -> None:
    result = run_generate(
        chat_payload={
            "abstain": False,
            "answer": "Something specific that looks grounded.",
            "citation_ids": ["phantom-doc:0"],
        }
    )
    assert result.abstained is True
    assert result.terminal == "abstain"
    assert result.answer == ABSTAIN_ANSWER
    assert result.citations == []
    assert result.abstain_reason == "ungrounded"
    assert result.path == ["retrieve", "generate"]


def test_empty_retrieve_abstains_without_chat() -> None:
    chat = stub_chat({"abstain": False, "answer": "should not run", "citation_ids": ["x"]})
    result = generate(
        "how does the kube-scheduler place pods onto nodes",
        retrieve_fn=lambda _q: [],
        chat_fn=chat,
        settings=make_settings(),
        config=RetrieveConfig(),
    )
    assert result.abstained is True
    assert result.answer == ABSTAIN_ANSWER
    assert result.citations == []
    assert result.abstain_reason == "empty_retrieve"
    assert result.path == ["retrieve", "abstain"]
    assert result.terminal == "abstain"
    assert chat.calls == []
    assert result.cost.prompt_tokens == 0
    assert result.cost.completion_tokens == 0


def test_low_confidence_abstains_without_chat() -> None:
    hits = [
        ChunkHit(
            chunk_id="k8s-pods:0",
            doc_id="k8s-pods",
            score=0.04,
            rank=1,
            rerank_skipped=False,
            text="A Pod is the smallest deployable unit.",
            rerank_score=0.04,
        )
    ]
    chat = stub_chat({"abstain": False, "answer": "nope", "citation_ids": ["k8s-pods:0"]})
    result = generate(
        "unrelated low-score query",
        retrieve_fn=stub_retrieve(hits),
        chat_fn=chat,
        settings=make_settings(abstain_min_score=0.12),
        config=RetrieveConfig(),
    )
    assert result.abstain_reason == "low_confidence"
    assert result.abstained is True
    assert result.answer == ABSTAIN_ANSWER
    assert result.path == ["retrieve", "abstain"]
    assert chat.calls == []


def test_rerank_skipped_does_not_use_score_gate() -> None:
    hits = [
        ChunkHit(
            chunk_id="k8s-scheduler:0",
            doc_id="k8s-scheduler",
            score=0.016,
            rank=1,
            rerank_skipped=True,
            text="kube-scheduler assigns unscheduled Pods to nodes.",
        )
    ]
    result = generate(
        "how does the kube-scheduler place pods onto nodes",
        retrieve_fn=stub_retrieve(hits),
        chat_fn=stub_chat(
            {
                "abstain": False,
                "answer": "It assigns unscheduled pods to nodes.",
                "citation_ids": ["k8s-scheduler:0"],
            }
        ),
        settings=make_settings(),
        config=RetrieveConfig(),
    )
    assert result.abstained is False
    assert result.terminal == "generate"
    assert [ref.chunk_id for ref in result.citations] == ["k8s-scheduler:0"]


def test_out_of_corpus_known_bad_abstains() -> None:
    rows = [json.loads(line) for line in KNOWN_BAD.read_text(encoding="utf-8").splitlines() if line]
    question = rows[0]["question"]
    assert "InnovX" in question
    fixture = load_5doc()
    result = run_generate(
        fixture,
        query=question,
        chat_payload={"abstain": True, "answer": "I don't know", "citation_ids": []},
    )
    assert result.abstained is True
    assert result.answer == ABSTAIN_ANSWER
    assert result.citations == []
    assert result.abstain_reason == "out_of_corpus"
    assert result.terminal == "abstain"
    assert result.path == ["retrieve", "generate"]


def test_cost_estimate_matches_v1_formula() -> None:
    settings = make_settings()
    result = run_generate(
        chat_fn=stub_chat(
            {
                "abstain": False,
                "answer": "kube-scheduler filters and scores nodes.",
                "citation_ids": ["k8s-scheduler:0"],
            },
            prompt_tokens=100,
            completion_tokens=50,
        )
    )
    expected = estimate_usd(
        prompt_tokens=100,
        completion_tokens=50,
        embed_tokens=result.cost.embed_tokens,
        settings=settings,
    )
    assert result.cost.prompt_tokens == 100
    assert result.cost.completion_tokens == 50
    assert result.cost.rerank_tokens == 0
    assert result.cost.embed_tokens > 0
    assert result.cost.usd_estimate == pytest.approx(expected)
    assert result.cost_method == cost_method_string(settings)
    assert result.cost_method.startswith(COST_METHOD_NAME)
    assert "formula=(prompt_tokens*prompt_usd_per_1m" in result.cost_method
    dumped = CostEstimate.model_validate(result.cost.model_dump())
    assert set(dumped.model_dump()) == {
        "prompt_tokens",
        "completion_tokens",
        "embed_tokens",
        "rerank_tokens",
        "usd_estimate",
    }


def test_refs_for_ids_keeps_only_retrieved() -> None:
    hits = fixture_hits(load_5doc())
    refs = refs_for_ids(hits, ["missing", "k8s-pods:0", "k8s-pods:0", "az-aks-intro:0"])
    assert [ref.chunk_id for ref in refs] == ["k8s-pods:0", "az-aks-intro:0"]
    assert all(isinstance(ref, ChunkRef) for ref in refs)


def test_retrieve_abstain_reason_policy() -> None:
    assert retrieve_abstain_reason([], 0.12) == "empty_retrieve"
    weak = [
        ChunkHit(chunk_id="a", doc_id="a", score=0.01, rank=1, rerank_skipped=False, text="x")
    ]
    assert retrieve_abstain_reason(weak, 0.12) == "low_confidence"
    skipped = [
        ChunkHit(chunk_id="a", doc_id="a", score=0.01, rank=1, rerank_skipped=True, text="x")
    ]
    assert retrieve_abstain_reason(skipped, 0.12) is None
    strong = [
        ChunkHit(chunk_id="a", doc_id="a", score=0.9, rank=1, rerank_skipped=False, text="x")
    ]
    assert retrieve_abstain_reason(strong, 0.12) is None


def test_chat_payload_reads_usage_and_content() -> None:
    result = _result_from_payload(
        {
            "choices": [{"message": {"role": "assistant", "content": '{"abstain": true}'}}],
            "usage": {"prompt_tokens": 9, "completion_tokens": 3},
        }
    )
    assert result.content == '{"abstain": true}'
    assert result.prompt_tokens == 9
    assert result.completion_tokens == 3


def test_parse_model_payload_accepts_fenced_json() -> None:
    payload = parse_model_payload("```json\n{\"abstain\": true, \"answer\": \"I don't know\"}\n```")
    assert payload["abstain"] is True


def test_generate_endpoint_503_without_groq_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "")
    from main import app

    response = TestClient(app).post("/generate", json={"query": "how are pods scheduled"})
    assert response.status_code == 503
    assert "GROQ_API_KEY" in response.text
    health = TestClient(app).get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}


def test_generate_endpoint_401_when_groq_rejects_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "gsk_bad")
    import main as main_mod

    def boom(*_args, **_kwargs):
        raise RuntimeError(
            "GROQ_API_KEY was rejected by Groq (HTTP 401). Check the key at "
            "https://console.groq.com/keys"
        )

    monkeypatch.setattr(main_mod, "generate", boom)
    response = TestClient(main_mod.app).post("/generate", json={"query": "pods"})
    assert response.status_code == 401
    assert "rejected by Groq" in response.json()["detail"]


def test_ingest_endpoint_401_when_groq_rejects_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "gsk_bad")
    import main as main_mod

    def boom(*_args, **_kwargs):
        raise RuntimeError(
            "GROQ_API_KEY was rejected by Groq (HTTP 401). Check the key at "
            "https://console.groq.com/keys"
        )

    monkeypatch.setattr(main_mod, "run_ingest", boom)
    response = TestClient(main_mod.app).post("/ingest", json={})
    assert response.status_code == 401
    assert "rejected by Groq" in response.json()["detail"]


def test_generate_endpoint_cite_path_wired(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    fixture = load_5doc()
    hits = fixture_hits(fixture)

    def fake_generate(query: str, **_kwargs):
        return generate(
            query,
            retrieve_fn=stub_retrieve(hits),
            chat_fn=stub_chat(
                {
                    "abstain": False,
                    "answer": "kube-scheduler binds pods after filtering nodes.",
                    "citation_ids": ["k8s-scheduler:0"],
                }
            ),
            settings=make_settings(),
            config=RetrieveConfig(),
        )

    import main as main_mod

    monkeypatch.setattr(main_mod, "generate", fake_generate)
    response = TestClient(main_mod.app).post("/generate", json={"query": fixture["query"]})
    assert response.status_code == 200
    body = response.json()
    retrieved = set(body["retrieved_chunk_ids"])
    cited = {row["chunk_id"] for row in body["citations"]}
    assert cited <= retrieved
    assert body["abstained"] is False
    assert body["cost_method"].startswith(COST_METHOD_NAME)
