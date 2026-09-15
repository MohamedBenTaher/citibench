"""Emit C5 RunTrace rows for failing eval cases."""

from __future__ import annotations

from typing import Any

import citebench.eval.paths  # noqa: F401

from citebench.eval.pipeline import EvalAnswer
from citebench_api.config import load_settings
from citebench_api.tracing.trace import (
    ChunkRef,
    CostEstimate,
    RunTrace,
    Span,
    SpanKind,
    SpanStatus,
    emit_trace,
    new_span_id,
    utcnow,
)


def emit_failing_trace(answer: EvalAnswer, *, reason: str) -> RunTrace:
    if answer.trace is not None:
        emit_trace(answer.trace, settings=_settings())
        return answer.trace
    trace = build_eval_trace(answer, reason=reason, failed=True)
    emit_trace(trace, settings=_settings())
    return trace


def emit_row_trace(answer: EvalAnswer, *, failed: bool, reason: str) -> RunTrace:
    if not failed and not answer.emit_trace:
        if answer.trace is not None:
            return answer.trace
        return build_eval_trace(answer, reason=reason, failed=False)
    if failed:
        return emit_failing_trace(answer, reason=reason)
    trace = build_eval_trace(answer, reason=reason, failed=False)
    if answer.emit_trace:
        emit_trace(trace, settings=_settings())
    return trace


def build_eval_trace(answer: EvalAnswer, *, reason: str, failed: bool) -> RunTrace:
    started = utcnow()
    finished = utcnow()
    retrieve_id = new_span_id(SpanKind.retrieve)
    rerank_id = new_span_id(SpanKind.rerank)
    leaf_kind = SpanKind.abstain if answer.abstained else SpanKind.generate
    leaf_id = new_span_id(leaf_kind)
    citations = [] if answer.abstained else [_chunk_ref(item) for item in answer.citations]
    pointers = [
        {
            "chunk_id": ref.chunk_id,
            "doc_id": ref.doc_id,
            "text_ref": ref.text_ref,
            "rank": ref.rank,
        }
        for ref in citations
    ]
    status = SpanStatus.error if failed and not answer.abstained else SpanStatus.ok
    spans = [
        Span(
            span_id=retrieve_id,
            parent_id=None,
            kind=SpanKind.retrieve,
            started_at=started,
            finished_at=finished,
            status=SpanStatus.ok,
            attributes={"hit_count": len(pointers), "chunks": pointers},
        ),
        Span(
            span_id=rerank_id,
            parent_id=retrieve_id,
            kind=SpanKind.rerank,
            started_at=started,
            finished_at=finished,
            status=SpanStatus.ok,
            attributes={"rerank_skipped": True},
        ),
        Span(
            span_id=leaf_id,
            parent_id=rerank_id,
            kind=leaf_kind,
            started_at=started,
            finished_at=finished,
            status=status,
            attributes={"reason": reason, "eval_row_id": answer.row_id},
        ),
    ]
    return RunTrace(
        run_id=answer.run_id,
        query=answer.question,
        started_at=started,
        finished_at=finished,
        spans=spans,
        citations=citations,
        abstained=answer.abstained,
        cost=CostEstimate(),
        rerank_skipped=True,
        model="citebench.eval.mock" if answer.abstained is False else "",
        cost_method="citebench.cost.v1",
    )


def _chunk_ref(item: Any) -> ChunkRef:
    if isinstance(item, ChunkRef):
        return item
    if isinstance(item, dict):
        doc_id = str(item.get("doc_id") or "eval")
        chunk_id = str(item.get("chunk_id") or "0")
        text_ref = str(item.get("text_ref") or f"{doc_id}#{chunk_id}")
        return ChunkRef(
            chunk_id=chunk_id,
            doc_id=doc_id,
            text_ref=text_ref,
            score=item.get("score"),
            rank=item.get("rank"),
        )
    doc_id = str(getattr(item, "doc_id", "eval"))
    chunk_id = str(getattr(item, "chunk_id", "0"))
    text_ref = str(getattr(item, "text_ref", f"{doc_id}#{chunk_id}"))
    return ChunkRef(chunk_id=chunk_id, doc_id=doc_id, text_ref=text_ref)


def _settings() -> Any:
    try:
        return load_settings()
    except Exception:
        return None
