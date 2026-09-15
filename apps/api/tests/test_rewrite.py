from __future__ import annotations

import json
from pathlib import Path

from citebench_api.retrieval.retrieve import ChunkHit, RetrieveConfig
from test_generate import make_settings, stub_chat
from citebench_api.tracing.trace import SpanKind, emit_trace, get_trace

from citebench_api.generation import rewrite as rewrite
from citebench_api.generation.rewrite import clamp_max_words, parse_rewrite, rewrite_query


def test_parse_rejects_garbage() -> None:
    assert parse_rewrite('{"query": "  "} ') is None
    assert parse_rewrite("not json") is None
    assert parse_rewrite('{"query": 5}') is None
    assert parse_rewrite('{"query": "kubernetes scheduler"}') == "kubernetes scheduler"


def test_clamp_keeps_inside_budget() -> None:
    assert len(clamp_max_words(" ".join(["w"] * 55)).split()) == 40


def test_rewrite_returns_parsed_and_clamped_query() -> None:
    captured: list[list[dict[str, str]]] = []

    def fake_chat(messages, _settings):
        captured.append(messages)
        from citebench_api.generation.chat import ChatResult

        return ChatResult('{"query": "pods   scheduled on nodes  too"}', 5, 3, model="m")

    assert rewrite_query(
        "how are pods scheduled", make_settings(), chat_fn=fake_chat
    ) == "pods scheduled on nodes too"
    assert captured[0][1]["content"] == "how are pods scheduled"


def test_rewrite_failure_returns_original(monkeypatch) -> None:
    def boom(_messages, _settings):
        raise rewrite.ChatError("Groq chat HTTP 500")

    monkeypatch.setattr(rewrite, "groq_chat", boom)
    assert rewrite_query("what is a pod", make_settings()) == "what is a pod"


def test_missing_key_leaves_query_untouched() -> None:
    assert rewrite_query("what is a pod", make_settings(groq_api_key="")) == "what is a pod"


def _hit(chunk_id: str = "k8s-pods:0") -> ChunkHit:
    return ChunkHit(
        chunk_id=chunk_id,
        doc_id=chunk_id.split(":")[0],
        score=0.8,
        rank=1,
        rerank_skipped=False,
        text="A Pod runs containers.",
    )


def _dispatch_chat(rewrite_json: str, answer_payload: dict):
    """Chat fn that answers the rewrite prompt separately from the ask."""
    def chat_fn(messages):
        from citebench_api.generation.chat import ChatResult

        if "rewrite" in messages[0]["content"]:
            return ChatResult(rewrite_json, 5, 3, model="m")
        return ChatResult(json.dumps(answer_payload), 30, 20, model="m")

    return chat_fn


def test_generate_uses_rewritten_query_and_records_it(tmp_path) -> None:
    from citebench_api.generation.generate import generate

    settings = make_settings(query_rewrite=True, trace_store_dir=Path(tmp_path / "traces"))
    seen_queries: list[str] = []

    def retrieve_fn(query: str):
        seen_queries.append(query)
        return [_hit()]

    chat_fn = _dispatch_chat(
        '{"query": "how are kubernetes pods scheduled onto nodes"}',
        {"abstain": False, "answer": "Assigns pods.", "citation_ids": ["k8s-pods:0"]},
    )
    result = generate(
        "how are pods scheduled",
        retrieve_fn=retrieve_fn,
        chat_fn=chat_fn,
        settings=settings,
        config=RetrieveConfig(),
    )
    assert result.abstained is False
    assert seen_queries == ["how are kubernetes pods scheduled onto nodes"]

    trace = get_trace(result.run_id, settings=settings)
    assert trace is not None
    retrieve_span = next(span for span in trace.spans if span.kind == SpanKind.retrieve)
    assert retrieve_span.attributes.get("original_query") == "how are pods scheduled"
    assert (
        retrieve_span.attributes.get("rewritten_query")
        == "how are kubernetes pods scheduled onto nodes"
    )


def test_generate_skips_rewrite_when_flag_off(tmp_path) -> None:
    from citebench_api.generation.generate import generate

    settings = make_settings(trace_store_dir=Path(tmp_path / "traces"))
    seen_queries: list[str] = []

    def retrieve_fn(query: str):
        seen_queries.append(query)
        return [_hit()]

    chat_fn = _dispatch_chat(
        '{"query": "should never be used"}',
        {"abstain": False, "answer": "ok", "citation_ids": ["k8s-pods:0"]},
    )
    result = generate(
        "what is a pod",
        retrieve_fn=retrieve_fn,
        chat_fn=chat_fn,
        settings=settings,
        config=RetrieveConfig(),
    )
    assert result.abstained is False
    assert seen_queries == ["what is a pod"]


def test_rewrite_failure_flag_on_still_answers(tmp_path) -> None:
    from citebench_api.generation.generate import generate

    settings = make_settings(query_rewrite=True, trace_store_dir=Path(tmp_path / "traces"))
    seen_queries: list[str] = []

    def retrieve_fn(query: str):
        seen_queries.append(query)
        return [_hit()]

    def chat_fn(messages):
        from citebench_api.generation.chat import ChatResult

        if "rewrite" in messages[0]["content"]:
            raise rewrite.ChatError("Groq chat HTTP 500")
        payload = {"abstain": False, "answer": "ok", "citation_ids": ["k8s-pods:0"]}
        return ChatResult(json.dumps(payload), 30, 20, model="m")

    result = generate(
        "what is a pod",
        retrieve_fn=retrieve_fn,
        chat_fn=chat_fn,
        settings=settings,
        config=RetrieveConfig(),
    )
    assert result.abstained is False
    # The rewrite failed, so the original question retrieved — no fabricated terms.
    assert seen_queries == ["what is a pod"]

    trace = get_trace(result.run_id, settings=settings)
    assert trace is not None
    retrieve_span = next(span for span in trace.spans if span.kind == SpanKind.retrieve)
    assert retrieve_span.attributes.get("rewritten_query") == "what is a pod"


def test_rewrite_does_not_break_abstention(tmp_path) -> None:
    """An out-of-corpus question still abstains with the rewrite on."""
    from citebench_api.generation.generate import generate

    settings = make_settings(query_rewrite=True, trace_store_dir=Path(tmp_path / "traces"))

    def retrieve_fn(query: str):
        return [ChunkHit(chunk_id="k8s:0", doc_id="k8s", score=0.9, rank=1,
                         rerank_skipped=False, text="kubernetes text")]

    chat_fn = _dispatch_chat(
        '{"query": "how do I reset my payroll password in the HR dashboard"}',
        {"abstain": True, "answer": "I don't know", "citation_ids": []},
    )
    result = generate(
        "how do I reset my payroll password",
        retrieve_fn=retrieve_fn,
        chat_fn=chat_fn,
        settings=settings,
        config=RetrieveConfig(),
    )
    assert result.abstained is True
    assert result.abstain_reason == "out_of_corpus"
    assert result.answer == "I don't know"
