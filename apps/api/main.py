from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from db import connect, corpus_stats, ensure_schema
from generate import GenerateResult, generate
from pipeline import run_ingest
from retrieve import ChunkHit, retrieve, retrieve_config_from_settings
from settings import GROQ_KEY_HELP, load_settings
from trace import get_trace, langfuse_configured, list_traces

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("citebench.api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = load_settings()
    try:
        with connect(settings.database_url) as conn:
            ensure_schema(conn)
    except Exception as exc:
        log.warning("database schema not ready at startup: %s", exc)
    yield


app = FastAPI(title="Citebench API", version="0.5.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class IngestRequest(BaseModel):
    wipe: bool = False
    simulate_failure_id: str | None = Field(
        default=None,
        description="Optional MANIFEST id to record as an unreachable snapshot (verification).",
    )


class RetrieveRequest(BaseModel):
    query: str


class RetrieveResponse(BaseModel):
    hits: list[ChunkHit]
    rerank_skipped: bool = False


class GenerateRequest(BaseModel):
    query: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/corpus/stats")
def get_corpus_stats() -> dict[str, Any]:
    settings = load_settings()
    try:
        with connect(settings.database_url) as conn:
            ensure_schema(conn)
            return corpus_stats(conn)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"database unavailable: {exc}") from exc


@app.post("/ingest")
def post_ingest(body: IngestRequest | None = None) -> dict[str, Any]:
    req = body or IngestRequest()
    settings = load_settings()
    if not settings.groq_api_key:
        raise HTTPException(status_code=503, detail=GROQ_KEY_HELP)
    try:
        return run_ingest(
            settings,
            wipe=req.wipe,
            simulate_failure_id=req.simulate_failure_id,
        )
    except RuntimeError as exc:
        message = str(exc)
        if "GROQ_API_KEY" in message:
            raise HTTPException(status_code=503, detail=message) from exc
        raise HTTPException(status_code=500, detail=message) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/retrieve")
def post_retrieve(body: RetrieveRequest) -> RetrieveResponse:
    settings = load_settings()
    if not settings.groq_api_key:
        raise HTTPException(status_code=503, detail=GROQ_KEY_HELP)
    query = (body.query or "").strip()
    if not query:
        return RetrieveResponse(hits=[], rerank_skipped=False)
    try:
        hits = retrieve(query, retrieve_config_from_settings(settings), settings=settings)
    except RuntimeError as exc:
        message = str(exc)
        if "GROQ_API_KEY" in message:
            raise HTTPException(status_code=503, detail=message) from exc
        raise HTTPException(status_code=500, detail=message) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    skipped = bool(hits) and all(hit.rerank_skipped for hit in hits)
    return RetrieveResponse(hits=hits, rerank_skipped=skipped)


@app.post("/generate")
def post_generate(body: GenerateRequest) -> GenerateResult:
    settings = load_settings()
    if not settings.groq_api_key:
        raise HTTPException(status_code=503, detail=GROQ_KEY_HELP)
    try:
        return generate(
            body.query or "",
            settings=settings,
            config=retrieve_config_from_settings(settings),
        )
    except RuntimeError as exc:
        message = str(exc)
        if "GROQ_API_KEY" in message:
            raise HTTPException(status_code=503, detail=message) from exc
        raise HTTPException(status_code=500, detail=message) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/traces")
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


@app.get("/traces/{run_id}")
def get_trace_detail(run_id: str) -> dict[str, Any]:
    settings = load_settings()
    item = get_trace(run_id, settings=settings)
    if item is None:
        raise HTTPException(status_code=404, detail=f"trace not found: {run_id}")
    return item.model_dump(mode="json")
