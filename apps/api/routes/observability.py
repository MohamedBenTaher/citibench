"""Observability read side: /traces, /traces/{run_id}, /metrics."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

import metrics as metrics_service  # service module; this package has its own observability.py
from settings import load_settings
from trace import get_trace, langfuse_configured, list_traces

router = APIRouter()


@router.get("/traces")
def get_traces() -> dict[str, Any]:
    settings = load_settings()
    traces = list_traces(settings=settings)
    return {
        "langfuse_configured": langfuse_configured(settings),
        "backend": "langfuse" if langfuse_configured(settings) else "local",
        "count": len(traces),
        "traces": [
            {
                "run_id": item.run_id,
                "query": item.query,
                "started_at": item.started_at.isoformat(),
                "finished_at": item.finished_at.isoformat(),
                "abstained": item.abstained,
                "model": item.model,
                "tokens_in": item.tokens_in,
                "tokens_out": item.tokens_out,
                "latency_ms": item.latency_ms,
                "cost": item.cost.model_dump(),
                "cost_method": item.cost_method,
                "langfuse_trace_id": item.langfuse_trace_id,
                "rerank_skipped": item.rerank_skipped,
                "citation_count": len(item.citations),
                "failed": any(span.status.value == "error" for span in item.spans),
            }
            for item in traces
        ],
    }


@router.get("/traces/{run_id}")
def get_trace_detail(run_id: str) -> dict[str, Any]:
    settings = load_settings()
    item = get_trace(run_id, settings=settings)
    if item is None:
        raise HTTPException(status_code=404, detail=f"trace not found: {run_id}")
    return item.model_dump(mode="json")


@router.get("/metrics", response_model=None)
def get_metrics(
    format: str | None = Query(default=None, description="json (default) or prometheus"),
):
    snapshot = metrics_service.collect_metrics()
    fmt = (format or "json").strip().lower()
    if fmt in {"prom", "prometheus", "text"}:
        return PlainTextResponse(
            metrics_service.render_prometheus(snapshot),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )
    if fmt not in {"", "json"}:
        raise HTTPException(status_code=400, detail="format must be json or prometheus")
    return snapshot
