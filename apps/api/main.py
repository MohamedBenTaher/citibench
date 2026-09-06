from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from db import connect, corpus_stats, ensure_schema
from pipeline import run_ingest
from settings import GROQ_KEY_HELP, load_settings

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


app = FastAPI(title="Citebench API", version="0.2.0", lifespan=lifespan)
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
