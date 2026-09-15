"""POST /retrieve and POST /generate (the ask path)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from citebench_api.generation.generate import GenerateResult, generate
from citebench_api.shared.ratelimit import generate_window
from citebench_api.retrieval.retrieve import ChunkHit, Filters, retrieve, retrieve_config_from_settings
from citebench_api.routes.errors import runtime_http_error
from citebench_api.config import load_settings

router = APIRouter()


class RetrieveRequest(BaseModel):
    query: str
    filters: Filters | None = None


class RetrieveResponse(BaseModel):
    hits: list[ChunkHit]
    rerank_skipped: bool = False


class GenerateRequest(BaseModel):
    query: str
    filters: Filters | None = None


@router.post("/retrieve")
def post_retrieve(body: RetrieveRequest) -> RetrieveResponse:
    settings = load_settings()
    query = (body.query or "").strip()
    if not query:
        return RetrieveResponse(hits=[], rerank_skipped=False)
    try:
        config = retrieve_config_from_settings(settings).model_copy(
            update={"filters": body.filters}
        )
        hits = retrieve(query, config, settings=settings)
    except RuntimeError as exc:
        raise runtime_http_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    skipped = bool(hits) and all(hit.rerank_skipped for hit in hits)
    return RetrieveResponse(hits=hits, rerank_skipped=skipped)


@router.post("/generate")
def post_generate(body: GenerateRequest) -> GenerateResult:
    settings = load_settings()
    if not generate_window.allow(settings.generate_max_per_minute):
        raise HTTPException(
            status_code=429,
            detail="generate rate limit exceeded; retry shortly",
        )
    try:
        config = retrieve_config_from_settings(settings).model_copy(
            update={"filters": body.filters}
        )
        return generate(body.query or "", settings=settings, config=config)
    except RuntimeError as exc:
        raise runtime_http_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
