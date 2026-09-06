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
import time
from collections.abc import Sequence
from typing import Any, Literal, Protocol, TypedDict
from uuid import uuid4

import tiktoken
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from chat import ChatResult, groq_chat
from retrieve import ChunkHit, RetrieveConfig, retrieve, retrieve_config_from_settings
from settings import Settings, load_settings

log = logging.getLogger("citebench.generate")

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


class ChunkRef(BaseModel):
    chunk_id: str
    doc_id: str
    text_ref: str
    score: float | None = None
    rank: int | None = None


class CostEstimate(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    embed_tokens: int = 0
    rerank_tokens: int = 0
    usd_estimate: float = 0.0


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


def _count_tokens(text: str, tokenizer: str) -> int:
    encoding = tiktoken.get_encoding(tokenizer)
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
            ChunkRef(
                chunk_id=hit.chunk_id,
                doc_id=hit.doc_id,
                text_ref=f"{hit.doc_id}#{hit.chunk_id}",
                score=hit.score,
                rank=hit.rank,
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
    cfg = config or retrieve_config_from_settings(resolved)
    query_text = query or ""
    started = time.perf_counter()

    do_retrieve = retrieve_fn or _default_retrieve(resolved, cfg)
    do_chat = chat_fn or _default_chat(resolved)
    graph = _compile_graph(do_retrieve, do_chat, resolved)

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
    }
    final = graph.invoke(initial)
    latency_ms = (time.perf_counter() - started) * 1000.0

    hits = list(final.get("hits") or [])
    embed_tokens = estimate_embed_tokens(query_text, resolved)
    prompt_tokens = int(final.get("prompt_tokens") or 0)
    completion_tokens = int(final.get("completion_tokens") or 0)
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
    abstained = bool(final.get("abstained"))
    citations = [] if abstained else list(final.get("citations") or [])
    answer = ABSTAIN_ANSWER if abstained else str(final.get("answer") or "").strip()
    terminal: Literal["generate", "abstain"] = "abstain" if abstained else "generate"
    return GenerateResult(
        run_id=str(uuid4()),
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
        rerank_skipped=bool(final.get("rerank_skipped")),
        model=resolved.chat_model,
    )


def _compile_graph(retrieve_fn: RetrieveFn, chat_fn: ChatFn, settings: Settings):
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
        reason = state.get("abstain_reason") or "empty_retrieve"
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
        hits = list(state.get("hits") or [])
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _user_prompt(state["query"], hits)},
        ]
        chat_result = chat_fn(messages)
        payload = parse_model_payload(chat_result.content)
        model_abstain = bool(payload.get("abstain"))
        citation_ids = _citation_ids_from_payload(payload)
        citations = refs_for_ids(hits, citation_ids)
        path = [*(state.get("path") or []), "generate"]
        if model_abstain or not citations:
            reason = "out_of_corpus" if model_abstain else "ungrounded"
            return {
                "answer": ABSTAIN_ANSWER,
                "citations": [],
                "abstained": True,
                "abstain_reason": reason,
                "terminal": "abstain",
                "path": path,
                "prompt_tokens": chat_result.prompt_tokens,
                "completion_tokens": chat_result.completion_tokens,
            }
        answer = str(payload.get("answer") or "").strip() or ABSTAIN_ANSWER
        if answer == ABSTAIN_ANSWER:
            return {
                "answer": ABSTAIN_ANSWER,
                "citations": [],
                "abstained": True,
                "abstain_reason": "out_of_corpus",
                "terminal": "abstain",
                "path": path,
                "prompt_tokens": chat_result.prompt_tokens,
                "completion_tokens": chat_result.completion_tokens,
            }
        return {
            "answer": answer,
            "citations": citations,
            "abstained": False,
            "abstain_reason": None,
            "terminal": "generate",
            "path": path,
            "prompt_tokens": chat_result.prompt_tokens,
            "completion_tokens": chat_result.completion_tokens,
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


def _default_retrieve(settings: Settings, config: RetrieveConfig) -> RetrieveFn:
    def _fn(query: str) -> list[ChunkHit]:
        return retrieve(query, config, settings=settings)

    return _fn


def _default_chat(settings: Settings) -> ChatFn:
    def _fn(messages: list[dict[str, str]]) -> ChatResult:
        return groq_chat(messages, settings)

    return _fn
