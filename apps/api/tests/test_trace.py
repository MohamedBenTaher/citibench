"""C5: one RunTrace per generate run, Langfuse map, local fallback."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from generate import generate
from retrieve import ChunkHit, RetrieveConfig
from test_generate import fixture_hits, load_5doc, make_settings, stub_chat, stub_retrieve
from trace import (
    ChunkRef,
    CostEstimate,
    RunTrace,
    Span,
    SpanKind,
    SpanStatus,
    emit_trace,
    get_trace,
    list_traces,
    validate_run_trace,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _span(
    kind: SpanKind,
    *,
    span_id: str,
    parent_id: str | None,
    attributes: dict | None = None,
    status: SpanStatus = SpanStatus.ok,
) -> Span:
    started = _now()
    return Span(
        span_id=span_id,
        parent_id=parent_id,
        kind=kind,
        started_at=started,
        finished_at=started + timedelta(milliseconds=2),
        status=status,
        attributes=attributes or {},
    )


def valid_trace(**overrides) -> RunTrace:
    retrieve = _span(SpanKind.retrieve, span_id="s-ret", parent_id=None, attributes={"chunks": []})
    rerank = _span(
        SpanKind.rerank,
        span_id="s-rr",
        parent_id="s-ret",
        attributes={"rerank_skipped": False},
    )
    generate_span = _span(
        SpanKind.generate,
        span_id="s-gen",
        parent_id="s-rr",
        attributes={"model": "llama-3.1-8b-instant"},
    )
    values = dict(
        run_id="run-1",
        query="how does the kube-scheduler place pods onto nodes",
        started_at=retrieve.started_at,
        finished_at=generate_span.finished_at,
        spans=[retrieve, rerank, generate_span],
        citations=[
            ChunkRef(
                chunk_id="k8s-scheduler:0",
                doc_id="k8s-scheduler",
                text_ref="k8s-scheduler#k8s-scheduler:0",
                score=0.4,
                rank=1,
            )
        ],
        abstained=False,
        cost=CostEstimate(prompt_tokens=10, completion_tokens=4, embed_tokens=8, usd_estimate=0.001),
        model="llama-3.1-8b-instant",
        tokens_in=10,
        tokens_out=4,
        latency_ms=12.5,
        cost_method="citebench.cost.v1",
        rerank_skipped=False,
    )
    values.update(overrides)
    return RunTrace(**values)


class FakePoster:
    def __init__(self, *, fail: bool = False, trace_id: str = "lf-ok") -> None:
        self.fail = fail
        self.trace_id = trace_id
        self.calls: list[RunTrace] = []

    def post(self, trace: RunTrace) -> str:
        self.calls.append(trace)
        if self.fail:
            raise RuntimeError("langfuse down")
        return self.trace_id


def test_n_queries_emit_n_traces() -> None:
    fixture = load_5doc()
    hits = fixture_hits(fixture)
    queries = [
        "how does the kube-scheduler place pods onto nodes",
        "What is the InnovX proprietary runbook password?",
        "how does a kubernetes service select pods",
    ]
    payloads = [
        {
            "abstain": False,
            "answer": "kube-scheduler filters and scores nodes.",
            "citation_ids": ["k8s-scheduler:0"],
        },
        {"abstain": True, "answer": "I don't know", "citation_ids": []},
        {
            "abstain": False,
            "answer": "A Service selects pods with label selectors.",
            "citation_ids": ["k8s-services:0"],
        },
    ]
    run_ids = []
    for query, payload in zip(queries, payloads, strict=True):
        result = generate(
            query,
            retrieve_fn=stub_retrieve(hits),
            chat_fn=stub_chat(payload),
            settings=make_settings(),
            config=RetrieveConfig(),
        )
        run_ids.append(result.run_id)
        assert result.trace_backend == "local"
        assert result.langfuse_trace_id is None
    traces = list_traces()
    assert len(traces) == 3
    assert {item.run_id for item in traces} == set(run_ids)
    for item in traces:
        _assert_required_fields(item)
        _assert_span_tree(item)
        _assert_no_corpus_dump(item)


def test_abstain_and_fail_are_inspectable() -> None:
    fixture = load_5doc()
    hits = fixture_hits(fixture)
    abstain = generate(
        "What is the InnovX proprietary runbook password?",
        retrieve_fn=stub_retrieve(hits),
        chat_fn=stub_chat({"abstain": True, "answer": "I don't know", "citation_ids": []}),
        settings=make_settings(),
        config=RetrieveConfig(),
    )
    stored = get_trace(abstain.run_id)
    assert stored is not None
    assert stored.abstained is True
    assert stored.citations == []
    kinds = [span.kind for span in stored.spans]
    assert kinds == [SpanKind.retrieve, SpanKind.rerank, SpanKind.abstain]
    assert stored.spans[-1].attributes.get("reason") == "out_of_corpus"

    def boom(_messages):
        raise RuntimeError("groq 500")

    with pytest.raises(RuntimeError, match="groq 500"):
        generate(
            fixture["query"],
            retrieve_fn=stub_retrieve(hits),
            chat_fn=boom,
            settings=make_settings(),
            config=RetrieveConfig(),
        )
    traces = list_traces()
    failed = next(item for item in traces if item.run_id != abstain.run_id)
    assert failed.abstained is False
    assert any(span.kind == SpanKind.generate and span.status == SpanStatus.error for span in failed.spans)
    assert "groq 500" in json.dumps(failed.model_dump(mode="json"))


def test_text_ref_pointer_not_corpus_dump() -> None:
    fixture = load_5doc()
    hits = fixture_hits(fixture)
    bodies = {row["text"] for row in fixture["chunks"]}
    result = generate(
        fixture["query"],
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
    stored = get_trace(result.run_id)
    assert stored is not None
    dumped = json.dumps(stored.model_dump(mode="json"))
    for body in bodies:
        assert body not in dumped
    for ref in stored.citations:
        assert ref.text_ref == f"{ref.doc_id}#{ref.chunk_id}"
        assert body_not_in(ref.text_ref, bodies)


def test_langfuse_success_sets_id() -> None:
    poster = FakePoster(trace_id="lf-123")
    trace = valid_trace(run_id="run-lf")
    emit_trace(trace, poster=poster)
    assert trace.langfuse_trace_id == "lf-123"
    assert get_trace("run-lf").langfuse_trace_id == "lf-123"
    assert poster.calls


def test_langfuse_down_keeps_local() -> None:
    poster = FakePoster(fail=True)
    trace = valid_trace(run_id="run-down")
    emit_trace(trace, poster=poster)
    assert trace.langfuse_trace_id is None
    stored = get_trace("run-down")
    assert stored is not None
    assert stored.query == trace.query
    assert stored.langfuse_trace_id is None


def test_unconfigured_langfuse_is_local_only() -> None:
    trace = valid_trace(run_id="run-local")
    emit_trace(trace)
    assert trace.langfuse_trace_id is None
    assert get_trace("run-local") is not None


def test_chunk_ref_rejects_body() -> None:
    with pytest.raises(ValueError, match="chunk body|pointer|text_ref"):
        ChunkRef(
            chunk_id="k8s-pods:0",
            doc_id="k8s-pods",
            text_ref="A Pod is the smallest deployable unit in Kubernetes. " * 3,
        )


def test_validate_rejects_missing_rerank() -> None:
    retrieve = _span(SpanKind.retrieve, span_id="s-ret", parent_id=None)
    generate_span = _span(SpanKind.generate, span_id="s-gen", parent_id="s-ret")
    trace = valid_trace(spans=[retrieve, generate_span])
    with pytest.raises(ValueError, match="rerank"):
        validate_run_trace(trace)


def test_traces_endpoint_lists_generate_runs(monkeypatch: pytest.MonkeyPatch) -> None:
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
    client = TestClient(main_mod.app)
    asked = client.post("/generate", json={"query": fixture["query"]})
    assert asked.status_code == 200
    run_id = asked.json()["run_id"]
    listed = client.get("/traces")
    assert listed.status_code == 200
    body = listed.json()
    assert body["count"] >= 1
    assert any(row["run_id"] == run_id for row in body["traces"])
    detail = client.get(f"/traces/{run_id}")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["run_id"] == run_id
    assert payload["query"] == fixture["query"]
    assert {span["kind"] for span in payload["spans"]} >= {"retrieve", "rerank", "generate"}


def test_schemas_emit_trace_is_implemented() -> None:
    import sys

    stub_dir = Path(__file__).resolve().parents[3] / "docs" / "contracts" / "stubs"
    sys.path.insert(0, str(stub_dir))
    import schemas as contract

    contract.emit_trace(contract.RunTrace.model_validate(valid_trace().model_dump()))


def _assert_required_fields(trace: RunTrace) -> None:
    assert trace.run_id
    assert isinstance(trace.query, str)
    assert trace.model
    assert trace.tokens_in >= 0
    assert trace.tokens_out >= 0
    assert trace.latency_ms >= 0
    assert trace.cost.usd_estimate >= 0
    assert trace.cost_method
    assert isinstance(trace.abstained, bool)
    for ref in trace.citations:
        assert ref.text_ref
        assert "#" in ref.text_ref


def _assert_span_tree(trace: RunTrace) -> None:
    kinds = [span.kind for span in trace.spans]
    assert kinds[0] == SpanKind.retrieve
    assert kinds[1] == SpanKind.rerank
    assert kinds[2] in {SpanKind.generate, SpanKind.abstain}
    assert trace.spans[0].parent_id is None
    assert trace.spans[1].parent_id == trace.spans[0].span_id
    assert trace.spans[2].parent_id == trace.spans[1].span_id
    if trace.abstained:
        assert kinds[2] == SpanKind.abstain
        assert trace.citations == []
    else:
        assert kinds[2] == SpanKind.generate


def _assert_no_corpus_dump(trace: RunTrace) -> None:
    dumped = json.dumps(trace.model_dump(mode="json"))
    assert "A Pod is the smallest deployable unit" not in dumped
    for span in trace.spans:
        assert "text" not in {str(key).lower() for key in span.attributes if isinstance(key, str)} or all(
            not isinstance(span.attributes.get(key), str) or len(str(span.attributes.get(key))) < 80
            for key in span.attributes
        )


def body_not_in(text_ref: str, bodies: set[str]) -> bool:
    return all(body not in text_ref for body in bodies)
