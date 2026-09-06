"""Citebench C1 contract stubs (Contracts A/B/C). Runtime is NotImplemented."""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

# Optional C5 runtime. The stub lives under docs/ and must import without apps/api.
try:
    from trace import RunTrace as RuntimeTrace
    from trace import emit_trace as runtime_emit
except ImportError:
    RuntimeTrace = None
    runtime_emit = None

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class SpanKind(str, Enum):
    retrieve = "retrieve"
    rerank = "rerank"
    generate = "generate"
    abstain = "abstain"

class SpanStatus(str, Enum):
    ok = "ok"
    error = "error"

class EvalRow(BaseModel):
    id: str
    question: str
    expected: str
    must_cite: bool
    abstain: bool
    known_bad: bool
    tags: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def id_shape(cls, value: str) -> str:
        if not _ID_RE.match(value):
            raise ValueError("id must match ^[A-Za-z0-9][A-Za-z0-9._-]*$")
        return value

    @field_validator("question", "expected")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("question and expected must be non-empty")
        return stripped

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, value: list[str]) -> list[str]:
        if any(not tag.strip() for tag in value) or len(value) != len(set(value)):
            raise ValueError("tags must be unique and non-empty")
        return value

    @model_validator(mode="after")
    def invariants(self) -> EvalRow:
        if self.known_bad and not self.abstain:
            raise ValueError("known_bad rows must abstain")
        if self.abstain and self.must_cite:
            raise ValueError("abstain rows must not require citations")
        return self

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

class Span(BaseModel):
    span_id: str
    parent_id: str | None = None
    kind: SpanKind
    started_at: datetime
    finished_at: datetime
    status: SpanStatus = SpanStatus.ok
    attributes: dict[str, Any] = Field(default_factory=dict)

class RunTrace(BaseModel):
    run_id: str
    query: str
    started_at: datetime
    finished_at: datetime
    spans: list[Span] = Field(default_factory=list)
    citations: list[ChunkRef] = Field(default_factory=list)
    abstained: bool = False
    cost: CostEstimate = Field(default_factory=CostEstimate)
    langfuse_trace_id: str | None = None
    rerank_skipped: bool = False

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

def load_eval_jsonl(path: str) -> list[EvalRow]:
    raise NotImplementedError("C1 stub: load_eval_jsonl")

def retrieve(query: str, config: RetrieveConfig | None = None) -> list[ChunkHit]:
    raise NotImplementedError("C1 stub: retrieve")

def emit_trace(trace: RunTrace) -> None:
    """C5: validate the contract tree, then persist via the runtime emitter."""
    _validate_run_trace(trace)
    if runtime_emit is None or RuntimeTrace is None:
        return
    runtime_emit(RuntimeTrace.model_validate(trace.model_dump()))


def _validate_run_trace(trace: RunTrace) -> None:
    retrieve = [span for span in trace.spans if span.kind == SpanKind.retrieve]
    rerank = [span for span in trace.spans if span.kind == SpanKind.rerank]
    generate = [span for span in trace.spans if span.kind == SpanKind.generate]
    abstain = [span for span in trace.spans if span.kind == SpanKind.abstain]
    if len(retrieve) != 1 or retrieve[0].parent_id is not None:
        raise ValueError("exactly one retrieve span with parent_id=null")
    if len(rerank) != 1 or rerank[0].parent_id != retrieve[0].span_id:
        raise ValueError("rerank must be the child of retrieve")
    if "rerank_skipped" not in rerank[0].attributes:
        raise ValueError("rerank attributes must include rerank_skipped")
    if trace.abstained:
        if generate or len(abstain) != 1 or abstain[0].parent_id != rerank[0].span_id:
            raise ValueError("abstain tree invalid")
        if trace.citations:
            raise ValueError("abstained citations must be empty")
        return
    if abstain or len(generate) != 1 or generate[0].parent_id != rerank[0].span_id:
        raise ValueError("generate tree invalid")
