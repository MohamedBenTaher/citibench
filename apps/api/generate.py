"""C4 LangGraph path: retrieve() → generate with citations XOR abstain.

Graph shape (one path, no multi-agent):

    START → retrieve → generate | abstain → END

`retrieve` is the existing C3 function (embed + hybrid + FlashRank). This module
does not reimplement retrieval.

Abstain policy (also in DECISIONS.md C4):

1. empty_retrieve — `retrieve()` returned no hits (including a blank query).
   No chat call.
2. low_confidence — FlashRank ran (`rerank_skipped` is false) and the top hit
   `score` is below `abstain_min_score` (config, default 0.12). RRF fallback
   scores are a different scale, so this gate is skipped when rerank is skipped.
3. out_of_corpus — the Groq chat model sets `abstain: true` (context does not
   support the question). Answer is normalized to "I don't know".
4. ungrounded — the model answered but left no citation_ids that are a subset
   of retrieved chunk ids. Treated as abstain, not as an uncited answer.

Citations on a generate outcome are always a subset of retrieved chunk ids.
Fabricated ids are dropped. A generate HTTP/parse failure is an error (HTTP
500), not an implicit abstain (Contract B).

CostEstimate matches Contract B. `cost_method` is `citebench.cost.v1` so the
USD formula is reproducible without Langfuse (C5).
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Literal, Protocol, TypedDict
from uuid import uuid4

import tiktoken
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from chat import ChatResult, groq_chat
from retrieve import ChunkHit, RetrieveConfig, retrieve, retrieve_config_from_settings
from settings import Settings, load_settings, require_groq_key
from trace import (
    ChunkRef,
    CostEstimate,
    RunTrace,
    Span,
    SpanKind,
    SpanStatus,
    chunk_ref_for_hit,
    emit_trace,
    new_span_id,
    refs_from_hits,
    utcnow,
)

log = logging.getLogger("citebench.generate")

_encoding_cache: dict[str, tiktoken.Encoding] = {}
_encoding_lock = threading.Lock()

ABSTAIN_ANSWER = "I don't know"
COST_METHOD_NAME = "citebench.cost.v1"

SYSTEM_PROMPT = """You are Citebench's grounded generator for a frozen public Kubernetes and Azure corpus.

Answer only from the retrieved chunks. If they do not contain the answer, abstain.

Return a JSON object with keys:
- abstain: boolean
- answer: string
- citation_ids: array of chunk_id strings

Rules:
- citation_ids MUST be a subset of the provided chunk ids. Never invent ids.
- If abstain is true, answer MUST be exactly "I don't know" and citation_ids MUST be [].
- If abstain is false, answer must be grounded in the chunks and citation_ids must be non-empty.
- Do not use prior knowledge that is not in the chunks.
"""


class GenerateResult(BaseModel):
    run_id: str
    query: str
    answer: str
    abstained: bool
    abstain_reason: str | None = None
    path: list[str] = Field(default_factory=list)
    terminal: Literal["generate", "abstain"]
    citations: list[ChunkRef] = Field(default_factory=list)
    retrieved_chunk_ids: list[str] = Field(default_factory=list)
    latency_ms: float
    cost: CostEstimate = Field(default_factory=CostEstimate)
    cost_method: str
    rerank_skipped: bool = False
    model: str
    langfuse_trace_id: str | None = None
    trace_backend: Literal["langfuse", "local"] = "local"


class ChatFn(Protocol):
    def __call__(self, messages: list[dict[str, str]]) -> ChatResult: ...


class RetrieveFn(Protocol):
    def __call__(self, query: str) -> Sequence[ChunkHit]: ...


class GraphState(TypedDict, total=False):
    query: str
    hits: list[ChunkHit]
    answer: str
    citations: list[ChunkRef]
    abstained: bool
    abstain_reason: str | None
    path: list[str]
    terminal: Literal["generate", "abstain"]
    prompt_tokens: int
    completion_tokens: int
    rerank_skipped: bool
    chat_model: str


def cost_method_string(settings: Settings) -> str:
    return (
        f"{COST_METHOD_NAME} provider=groq chat_model={settings.chat_model} "
        f"embed_model={settings.embed_model} tokenizer={settings.tokenizer} "
        f"prompt_usd_per_1m={settings.chat_prompt_usd_per_1m} "
        f"completion_usd_per_1m={settings.chat_completion_usd_per_1m} "
        f"embed_usd_per_1m={settings.embed_usd_per_1m} rerank_usd=0 "
        "formula=(prompt_tokens*prompt_usd_per_1m+"
        "completion_tokens*completion_usd_per_1m+"
        "embed_tokens*embed_usd_per_1m)/1e6"
    )


def estimate_usd(
    *,
    prompt_tokens: int,
    completion_tokens: int,
    embed_tokens: int,
    settings: Settings,
) -> float:
    usd = (
        prompt_tokens * settings.chat_prompt_usd_per_1m
        + completion_tokens * settings.chat_completion_usd_per_1m
        + embed_tokens * settings.embed_usd_per_1m
    ) / 1_000_000.0
    return round(max(usd, 0.0), 8)


def estimate_embed_tokens(query: str, settings: Settings) -> int:
    text = (query or "").strip()
    if not text:
        return 0
    return _count_tokens(settings.embed_query_prefix + text, settings.tokenizer)


def _get_encoding(tokenizer: str) -> tiktoken.Encoding:
    with _encoding_lock:
        encoding = _encoding_cache.get(tokenizer)
        if encoding is None:
            encoding = tiktoken.get_encoding(tokenizer)
            _encoding_cache[tokenizer] = encoding
        return encoding


def _count_tokens(text: str, tokenizer: str) -> int:
    encoding = _get_encoding(tokenizer)
    return len(encoding.encode(text))


def retrieve_abstain_reason(hits: Sequence[ChunkHit], min_score: float) -> str | None:
    if not hits:
        return "empty_retrieve"
    skipped = all(hit.rerank_skipped for hit in hits)
    if not skipped and hits[0].score < min_score:
        return "low_confidence"
    return None


def refs_for_ids(hits: Sequence[ChunkHit], chunk_ids: Sequence[str]) -> list[ChunkRef]:
    by_id = {hit.chunk_id: hit for hit in hits}
    refs: list[ChunkRef] = []
    seen: set[str] = set()
    for chunk_id in chunk_ids:
        if chunk_id in seen or chunk_id not in by_id:
            continue
        seen.add(chunk_id)
        hit = by_id[chunk_id]
        refs.append(
            chunk_ref_for_hit(
                chunk_id=hit.chunk_id,
                doc_id=hit.doc_id,
                score=hit.score,
                rank=hit.rank,
                title=getattr(hit, "title", None),
                source=getattr(hit, "source", None),
                product=getattr(hit, "product", None),
                doc_type=getattr(hit, "doc_type", None),
                version=getattr(hit, "version", None),
                license=getattr(hit, "license", None),
                page=getattr(hit, "page", None),
                section=getattr(hit, "section", None),
                url=getattr(hit, "url", None),
            )
        )
    return refs


def parse_model_payload(content: str) -> dict[str, Any]:
    text = content.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"generate model returned non-JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("generate model JSON must be an object")
    return payload


def _citation_ids_from_payload(payload: dict[str, Any]) -> list[str]:
    raw = payload.get("citation_ids", payload.get("citations", []))
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise RuntimeError("citation_ids must be an array")
    ids: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            ids.append(item.strip())
        elif isinstance(item, dict) and str(item.get("chunk_id") or "").strip():
            ids.append(str(item["chunk_id"]).strip())
    return ids


def generate(
    query: str,
    *,
    retrieve_fn: RetrieveFn | None = None,
    chat_fn: ChatFn | None = None,
    settings: Settings | None = None,
    config: RetrieveConfig | None = None,
) -> GenerateResult:
    resolved = settings if settings is not None else load_settings()
    if chat_fn is None:
        require_groq_key(resolved)
    cfg = config or retrieve_config_from_settings(resolved)
    query_text = query or ""
    run_id = str(uuid4())
    started_at = utcnow()
    started = time.perf_counter()
    stage_sink: list[dict[str, Any]] = []
    terminal_span: list[dict[str, Any]] = []

    do_retrieve = _wrap_retrieve(retrieve_fn, resolved, cfg, stage_sink)
    do_chat = chat_fn or _default_chat(resolved)
    graph = _compile_graph(do_retrieve, do_chat, resolved, terminal_span)

    initial: GraphState = {
        "query": query_text,
        "hits": [],
        "answer": "",
        "citations": [],
        "abstained": False,
        "abstain_reason": None,
        "path": [],
        "terminal": "abstain",
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "rerank_skipped": False,
        "chat_model": resolved.chat_model,
    }
    invoke_error: Exception | None = None
    final: GraphState = dict(initial)
    try:
        final = graph.invoke(initial)
    except Exception as exc:
        invoke_error = exc
    latency_ms = (time.perf_counter() - started) * 1000.0
    finished_at = utcnow()

    hits = list(final.get("hits") or [])
    embed_tokens = estimate_embed_tokens(query_text, resolved)
    prompt_tokens = int(final.get("prompt_tokens") or 0)
    completion_tokens = int(final.get("completion_tokens") or 0)
    billed_model = str(final.get("chat_model") or resolved.chat_model)
    if terminal_span:
        attrs = terminal_span[0].get("attributes") or {}
        if prompt_tokens == 0 and "prompt_tokens" in attrs:
            prompt_tokens = int(attrs.get("prompt_tokens") or 0)
            completion_tokens = int(attrs.get("completion_tokens") or 0)
        if attrs.get("model"):
            billed_model = str(attrs["model"])
    cost = CostEstimate(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        embed_tokens=embed_tokens,
        rerank_tokens=0,
        usd_estimate=estimate_usd(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            embed_tokens=embed_tokens,
            settings=resolved,
        ),
    )
    abstained = bool(final.get("abstained")) and invoke_error is None
    citations = [] if abstained or invoke_error is not None else list(final.get("citations") or [])
    answer = ABSTAIN_ANSWER if abstained else str(final.get("answer") or "").strip()
    terminal: Literal["generate", "abstain"] = "abstain" if abstained else "generate"
    rerank_skipped = _rerank_skipped(hits, final, stage_sink)
    trace = _build_run_trace(
        run_id=run_id,
        query=query_text,
        started_at=started_at,
        finished_at=finished_at,
        hits=hits,
        citations=citations,
        abstained=abstained,
        abstain_reason=final.get("abstain_reason") if abstained else None,
        cost=cost,
        cost_method=cost_method_string(resolved),
        model=billed_model,
        latency_ms=round(latency_ms, 3),
        rerank_skipped=rerank_skipped,
        stage_sink=stage_sink,
        terminal_span=terminal_span[0] if terminal_span else None,
        invoke_error=invoke_error,
    )
    try:
        emit_trace(trace, settings=resolved)
    except Exception as exc:
        log.warning("emit_trace failed; keeping in-memory RunTrace %s: %s", run_id, exc)
    if invoke_error is not None:
        raise invoke_error
    return GenerateResult(
        run_id=run_id,
        query=query_text,
        answer=answer,
        abstained=abstained,
        abstain_reason=final.get("abstain_reason") if abstained else None,
        path=list(final.get("path") or []),
        terminal=terminal,
        citations=citations,
        retrieved_chunk_ids=[hit.chunk_id for hit in hits],
        latency_ms=round(latency_ms, 3),
        cost=cost,
        cost_method=cost_method_string(resolved),
        rerank_skipped=rerank_skipped,
        model=billed_model,
        langfuse_trace_id=trace.langfuse_trace_id,
        trace_backend="langfuse" if trace.langfuse_trace_id else "local",
    )


def _compile_graph(
    retrieve_fn: RetrieveFn,
    chat_fn: ChatFn,
    settings: Settings,
    terminal_span: list[dict[str, Any]],
):
    def retrieve_node(state: GraphState) -> dict[str, Any]:
        hits = list(retrieve_fn(state["query"]))
        reason = retrieve_abstain_reason(hits, settings.abstain_min_score)
        skipped = bool(hits) and all(hit.rerank_skipped for hit in hits)
        return {
            "hits": hits,
            "path": [*(state.get("path") or []), "retrieve"],
            "abstain_reason": reason,
            "rerank_skipped": skipped,
        }

    def route_after_retrieve(state: GraphState) -> Literal["generate", "abstain"]:
        return "abstain" if state.get("abstain_reason") else "generate"

    def abstain_node(state: GraphState) -> dict[str, Any]:
        started = utcnow()
        reason = state.get("abstain_reason") or "empty_retrieve"
        terminal_span.append(
            {
                "kind": "abstain",
                "started_at": started,
                "finished_at": utcnow(),
                "status": "ok",
                "attributes": {"reason": reason},
            }
        )
        return {
            "answer": ABSTAIN_ANSWER,
            "citations": [],
            "abstained": True,
            "abstain_reason": reason,
            "terminal": "abstain",
            "path": [*(state.get("path") or []), "abstain"],
            "prompt_tokens": 0,
            "completion_tokens": 0,
        }

    def generate_node(state: GraphState) -> dict[str, Any]:
        started = utcnow()
        hits = list(state.get("hits") or [])
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _user_prompt(state["query"], hits)},
        ]
        chat_result = None
        try:
            chat_result = chat_fn(messages)
            payload = parse_model_payload(chat_result.content)
        except Exception as exc:
            billed_model = settings.chat_model
            attrs: dict[str, Any] = {"error": str(exc), "model": billed_model}
            if chat_result is not None:
                billed_model = chat_result.model or settings.chat_model
                attrs = {
                    "error": str(exc),
                    "model": billed_model,
                    "prompt_tokens": chat_result.prompt_tokens,
                    "completion_tokens": chat_result.completion_tokens,
                }
            terminal_span.append(
                {
                    "kind": "generate",
                    "started_at": started,
                    "finished_at": utcnow(),
                    "status": "error",
                    "attributes": attrs,
                }
            )
            raise
        billed_model = chat_result.model or settings.chat_model
        model_abstain = bool(payload.get("abstain"))
        citation_ids = _citation_ids_from_payload(payload)
        citations = refs_for_ids(hits, citation_ids)
        path = [*(state.get("path") or []), "generate"]
        token_attrs = {
            "model": billed_model,
            "prompt_tokens": chat_result.prompt_tokens,
            "completion_tokens": chat_result.completion_tokens,
        }
        if model_abstain or not citations:
            reason = "out_of_corpus" if model_abstain else "ungrounded"
            terminal_span.append(
                {
                    "kind": "abstain",
                    "started_at": started,
                    "finished_at": utcnow(),
                    "status": "ok",
                    "attributes": {**token_attrs, "reason": reason},
                }
            )
            return {
                "answer": ABSTAIN_ANSWER,
                "citations": [],
                "abstained": True,
                "abstain_reason": reason,
                "terminal": "abstain",
                "path": path,
                "prompt_tokens": chat_result.prompt_tokens,
                "completion_tokens": chat_result.completion_tokens,
                "chat_model": billed_model,
            }
        answer = str(payload.get("answer") or "").strip() or ABSTAIN_ANSWER
        if answer == ABSTAIN_ANSWER:
            terminal_span.append(
                {
                    "kind": "abstain",
                    "started_at": started,
                    "finished_at": utcnow(),
                    "status": "ok",
                    "attributes": {**token_attrs, "reason": "out_of_corpus"},
                }
            )
            return {
                "answer": ABSTAIN_ANSWER,
                "citations": [],
                "abstained": True,
                "abstain_reason": "out_of_corpus",
                "terminal": "abstain",
                "path": path,
                "prompt_tokens": chat_result.prompt_tokens,
                "completion_tokens": chat_result.completion_tokens,
                "chat_model": billed_model,
            }
        terminal_span.append(
            {
                "kind": "generate",
                "started_at": started,
                "finished_at": utcnow(),
                "status": "ok",
                "attributes": {
                    **token_attrs,
                    "citation_text_refs": [ref.text_ref for ref in citations],
                },
            }
        )
        return {
            "answer": answer,
            "citations": citations,
            "abstained": False,
            "abstain_reason": None,
            "terminal": "generate",
            "path": path,
            "prompt_tokens": chat_result.prompt_tokens,
            "completion_tokens": chat_result.completion_tokens,
            "chat_model": billed_model,
        }

    builder = StateGraph(GraphState)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("generate", generate_node)
    builder.add_node("abstain", abstain_node)
    builder.add_edge(START, "retrieve")
    builder.add_conditional_edges(
        "retrieve",
        route_after_retrieve,
        {"generate": "generate", "abstain": "abstain"},
    )
    builder.add_edge("generate", END)
    builder.add_edge("abstain", END)
    return builder.compile()


def _user_prompt(query: str, hits: Sequence[ChunkHit]) -> str:
    lines = [f"Question: {query.strip()}", "", "Retrieved chunks:"]
    for hit in hits:
        body = (hit.text or "").strip() or "(empty chunk text)"
        lines.append(f"[chunk_id={hit.chunk_id} doc_id={hit.doc_id} rank={hit.rank}]")
        lines.append(body)
        lines.append("")
    return "\n".join(lines).strip()


def _wrap_retrieve(
    retrieve_fn: RetrieveFn | None,
    settings: Settings,
    config: RetrieveConfig,
    stage_sink: list[dict[str, Any]],
) -> RetrieveFn:
    inner = retrieve_fn or _default_retrieve(settings, config, stage_sink)

    def _fn(query: str) -> list[ChunkHit]:
        started = utcnow()
        try:
            hits = list(inner(query))
        except Exception as exc:
            if not any(event.get("kind") == "retrieve" for event in stage_sink):
                _synthesize_retrieve_stages(stage_sink, started, [], error=str(exc))
            raise
        if not any(event.get("kind") == "retrieve" for event in stage_sink):
            _synthesize_retrieve_stages(stage_sink, started, hits)
        return hits

    return _fn


def _default_retrieve(
    settings: Settings,
    config: RetrieveConfig,
    stage_sink: list[dict[str, Any]],
) -> RetrieveFn:
    def _fn(query: str) -> list[ChunkHit]:
        return retrieve(query, config, settings=settings, stage_sink=stage_sink)

    return _fn


def _synthesize_retrieve_stages(
    stage_sink: list[dict[str, Any]],
    started: datetime,
    hits: Sequence[ChunkHit],
    *,
    error: str | None = None,
) -> None:
    finished = utcnow()
    skipped = (not hits) or all(hit.rerank_skipped for hit in hits)
    chunks = [
        {
            "chunk_id": hit.chunk_id,
            "doc_id": hit.doc_id,
            "text_ref": f"{hit.doc_id}#{hit.chunk_id}",
            "score": hit.score,
            "rank": hit.rank,
        }
        for hit in hits
    ]
    retrieve_attrs: dict[str, Any] = {"hit_count": len(hits), "chunks": chunks}
    rerank_attrs: dict[str, Any] = {"rerank_skipped": skipped, "chunks": chunks}
    status = "error" if error else "ok"
    if error:
        retrieve_attrs["error"] = error
        rerank_attrs["error"] = error
        rerank_attrs["rerank_skipped"] = True
    stage_sink.append(
        {
            "kind": "retrieve",
            "started_at": started,
            "finished_at": finished,
            "status": status,
            "attributes": retrieve_attrs,
        }
    )
    stage_sink.append(
        {
            "kind": "rerank",
            "started_at": started,
            "finished_at": finished,
            "status": status,
            "attributes": rerank_attrs,
        }
    )


def _rerank_skipped(
    hits: Sequence[ChunkHit],
    final: GraphState,
    stage_sink: list[dict[str, Any]],
) -> bool:
    if hits:
        return all(hit.rerank_skipped for hit in hits)
    for event in stage_sink:
        if event.get("kind") == "rerank":
            return bool((event.get("attributes") or {}).get("rerank_skipped"))
    return bool(final.get("rerank_skipped"))


def _event_span(
    event: dict[str, Any],
    *,
    span_id: str,
    parent_id: str | None,
    kind: SpanKind,
) -> Span:
    status_raw = str(event.get("status") or "ok")
    status = SpanStatus.error if status_raw == "error" else SpanStatus.ok
    started = event.get("started_at") or utcnow()
    finished = event.get("finished_at") or started
    return Span(
        span_id=span_id,
        parent_id=parent_id,
        kind=kind,
        started_at=started,
        finished_at=finished,
        status=status,
        attributes=dict(event.get("attributes") or {}),
    )


def _build_run_trace(
    *,
    run_id: str,
    query: str,
    started_at: datetime,
    finished_at: datetime,
    hits: Sequence[ChunkHit],
    citations: Sequence[ChunkRef],
    abstained: bool,
    abstain_reason: str | None,
    cost: CostEstimate,
    cost_method: str,
    model: str,
    latency_ms: float,
    rerank_skipped: bool,
    stage_sink: list[dict[str, Any]],
    terminal_span: dict[str, Any] | None,
    invoke_error: Exception | None,
) -> RunTrace:
    retrieve_id = new_span_id(SpanKind.retrieve)
    rerank_id = new_span_id(SpanKind.rerank)
    retrieve_event = next((e for e in stage_sink if e.get("kind") == "retrieve"), None)
    rerank_event = next((e for e in stage_sink if e.get("kind") == "rerank"), None)
    if retrieve_event is None:
        retrieve_event = {
            "started_at": started_at,
            "finished_at": finished_at,
            "status": "error" if invoke_error else "ok",
            "attributes": {"hit_count": len(hits), "chunks": [r.model_dump() for r in refs_from_hits(list(hits))]},
        }
    if rerank_event is None:
        rerank_event = {
            "started_at": retrieve_event.get("finished_at") or started_at,
            "finished_at": finished_at,
            "status": retrieve_event.get("status") or "ok",
            "attributes": {"rerank_skipped": rerank_skipped},
        }
    rerank_attrs = dict(rerank_event.get("attributes") or {})
    rerank_attrs["rerank_skipped"] = rerank_skipped
    rerank_event = {**rerank_event, "attributes": rerank_attrs}

    spans = [
        _event_span(retrieve_event, span_id=retrieve_id, parent_id=None, kind=SpanKind.retrieve),
        _event_span(rerank_event, span_id=rerank_id, parent_id=retrieve_id, kind=SpanKind.rerank),
    ]

    leaf = terminal_span
    if leaf is None:
        if invoke_error is not None:
            leaf = {
                "kind": "generate",
                "started_at": rerank_event.get("finished_at") or started_at,
                "finished_at": finished_at,
                "status": "error",
                "attributes": {"error": str(invoke_error), "model": model},
            }
        elif abstained:
            leaf = {
                "kind": "abstain",
                "started_at": rerank_event.get("finished_at") or started_at,
                "finished_at": finished_at,
                "status": "ok",
                "attributes": {"reason": abstain_reason or "empty_retrieve"},
            }
        else:
            leaf = {
                "kind": "generate",
                "started_at": rerank_event.get("finished_at") or started_at,
                "finished_at": finished_at,
                "status": "ok",
                "attributes": {
                    "model": model,
                    "citation_text_refs": [ref.text_ref for ref in citations],
                },
            }
    leaf_kind = SpanKind.abstain if leaf.get("kind") == "abstain" and invoke_error is None and abstained else (
        SpanKind.generate if not abstained or invoke_error is not None else SpanKind.abstain
    )
    if invoke_error is not None:
        leaf_kind = SpanKind.generate
        leaf = {**leaf, "kind": "generate", "status": "error"}
        if "error" not in (leaf.get("attributes") or {}):
            leaf["attributes"] = {**(leaf.get("attributes") or {}), "error": str(invoke_error), "model": model}
    spans.append(
        _event_span(
            leaf,
            span_id=new_span_id(leaf_kind),
            parent_id=rerank_id,
            kind=leaf_kind,
        )
    )
    return RunTrace(
        run_id=run_id,
        query=query,
        started_at=started_at,
        finished_at=finished_at,
        spans=spans,
        citations=list(citations),
        abstained=abstained,
        cost=cost,
        langfuse_trace_id=None,
        rerank_skipped=rerank_skipped,
        model=model,
        tokens_in=cost.prompt_tokens,
        tokens_out=cost.completion_tokens,
        latency_ms=latency_ms,
        cost_method=cost_method,
    )


def _default_chat(settings: Settings) -> ChatFn:
    def _fn(messages: list[dict[str, str]]) -> ChatResult:
        return groq_chat(messages, settings)

    return _fn
