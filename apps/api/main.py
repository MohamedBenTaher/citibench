from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from db import (
    connect,
    corpus_stats,
    database_unavailable_detail,
    ensure_schema,
    is_database_error,
)
from embed import warmup_local_embed
from generate import GenerateResult, generate
from metrics import MetricsSnapshot, collect_metrics, render_prometheus
from pipeline import IngestBusy, WipeDisabled, run_ingest
from ratelimit import generate_window
from rerank import warmup_ranker
from retrieve import ChunkHit, retrieve, retrieve_config_from_settings
from settings import GROQ_KEY_HELP, Settings, load_settings
from trace import get_trace, langfuse_configured, list_traces

def _read_json_object(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _load_redteam_cases(path: Path) -> list[dict[str, Any]]:
    """Read Contract A redteam JSONL without requiring the citebench package."""
    rows: list[dict[str, Any]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict) or not payload.get("id"):
            raise ValueError(f"{path}:{line_no}: redteam row must be an object with id")
        rows.append(
            {
                "id": payload["id"],
                "question": payload.get("question"),
                "expected": payload.get("expected"),
                "attack_type": payload.get("attack_type"),
                "expect_block": payload.get("expect_block"),
                "tags": list(payload.get("tags") or []),
            }
        )
    return rows


def _redteam_jsonl_path() -> Path:
    env = os.environ.get("REDTEAM_JSONL", "").strip()
    if env:
        return Path(env)
    for candidate in (
        Path("/app/evals/redteam.jsonl"),
        Path(__file__).resolve().parents[2] / "evals" / "redteam.jsonl",
        Path("evals/redteam.jsonl"),
    ):
        if candidate.is_file():
            return candidate
    return Path("/app/evals/redteam.jsonl")


logging.basicConfig(level=logging.INFO)
log = logging.getLogger("citebench.api")

_WARMUP_SKIP_VALUES = frozenset({"1", "true", "yes"})


def should_skip_model_warmup() -> bool:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    raw = os.environ.get("CITEBENCH_SKIP_MODEL_WARMUP", "").strip().lower()
    return raw in _WARMUP_SKIP_VALUES


def maybe_warmup(settings: Settings) -> None:
    if should_skip_model_warmup():
        return
    try:
        warmup_local_embed()
        warmup_ranker(settings.rerank_model)
        log.info("local embed and rerank models ready")
    except Exception as exc:
        log.warning("model warmup skipped or failed: %s", exc)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = load_settings()
    try:
        with connect(settings.database_url) as conn:
            ensure_schema(conn)
    except Exception as exc:
        log.warning("database schema not ready at startup: %s", exc)
    maybe_warmup(settings)
    yield


def _cors_origins() -> list[str]:
    """Localhost UI ports plus CORS_ORIGINS extras.

    Compose sometimes leaves `${WEB_PORT:-3000}` uninterpolated inside the
    CORS_ORIGINS default. Those tokens are dropped so ingest/generate from
    the browser still get Access-Control-Allow-Origin.
    """
    ports = {3000, 3100, 4173, 5173}
    raw_port = os.environ.get("WEB_PORT", "3000").strip()
    try:
        ports.add(int(raw_port))
    except ValueError:
        pass
    origins = [f"http://localhost:{port}" for port in sorted(ports)]
    origins.extend(f"http://127.0.0.1:{port}" for port in sorted(ports))
    for item in os.environ.get("CORS_ORIGINS", "").split(","):
        origin = item.strip()
        if origin and "${" not in origin:
            origins.append(origin)
    return list(dict.fromkeys(origins))


def _runtime_http_error(exc: RuntimeError) -> HTTPException:
    message = str(exc)
    if "rejected by Groq" in message:
        return HTTPException(status_code=401, detail=message)
    if "GROQ_API_KEY" in message:
        return HTTPException(status_code=503, detail=message)
    return HTTPException(status_code=500, detail=message)


app = FastAPI(title="Citebench API", version="0.9.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
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
            return corpus_stats(conn)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=database_unavailable_detail(exc, settings.database_url),
        ) from exc


@app.post("/ingest")
def post_ingest(body: IngestRequest | None = None) -> dict[str, Any]:
    req = body or IngestRequest()
    settings = load_settings()
    try:
        return run_ingest(
            settings,
            wipe=req.wipe,
            simulate_failure_id=req.simulate_failure_id,
        )
    except WipeDisabled as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except IngestBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _runtime_http_error(exc) from exc
    except Exception as exc:
        if is_database_error(exc):
            raise HTTPException(
                status_code=503,
                detail=database_unavailable_detail(exc, settings.database_url),
            ) from exc
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/retrieve")
def post_retrieve(body: RetrieveRequest) -> RetrieveResponse:
    settings = load_settings()
    query = (body.query or "").strip()
    if not query:
        return RetrieveResponse(hits=[], rerank_skipped=False)
    try:
        hits = retrieve(query, retrieve_config_from_settings(settings), settings=settings)
    except RuntimeError as exc:
        raise _runtime_http_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    skipped = bool(hits) and all(hit.rerank_skipped for hit in hits)
    return RetrieveResponse(hits=hits, rerank_skipped=skipped)


@app.post("/generate")
def post_generate(body: GenerateRequest) -> GenerateResult:
    settings = load_settings()
    if not generate_window.allow(settings.generate_max_per_minute):
        raise HTTPException(
            status_code=429,
            detail="generate rate limit exceeded; retry shortly",
        )
    try:
        return generate(
            body.query or "",
            settings=settings,
            config=retrieve_config_from_settings(settings),
        )
    except RuntimeError as exc:
        raise _runtime_http_error(exc) from exc
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


@app.get("/metrics", response_model=None)
def get_metrics(
    format: str | None = Query(default=None, description="json (default) or prometheus"),
):
    snapshot = collect_metrics()
    fmt = (format or "json").strip().lower()
    if fmt in {"prom", "prometheus", "text"}:
        return PlainTextResponse(
            render_prometheus(snapshot),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )
    if fmt not in {"", "json"}:
        raise HTTPException(status_code=400, detail="format must be json or prometheus")
    return snapshot


@app.get("/evals/latest")
def get_evals_latest() -> dict[str, Any]:
    path = _eval_store_dir() / "latest.json"
    if not path.is_file():
        return {
            "present": False,
            "metrics": None,
            "previous": None,
            "diff": None,
            "detail": "no eval run yet",
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail=f"eval artifact unreadable: {exc}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=500, detail="eval artifact must be an object")
    payload["present"] = True
    return payload


@app.get("/evals/redteam")
def get_evals_redteam() -> dict[str, Any]:
    """Last redteam run plus the 10 committed cases. Public; no login wall."""
    store = _eval_store_dir()
    artifact = _read_json_object(store / "redteam.json")
    cases: list[dict[str, Any]] = []
    split_error: str | None = None
    path = _redteam_jsonl_path()
    split_path = str(path)
    try:
        if path.is_file():
            cases = _load_redteam_cases(path)
        else:
            split_error = f"redteam split not found: {path}"
    except Exception as exc:
        split_error = str(exc)
    by_id = {
        row["id"]: row
        for row in (artifact or {}).get("rows", [])
        if isinstance(row, dict) and row.get("id")
    }
    merged = []
    for case in cases:
        run = by_id.get(case["id"], {})
        merged.append({**case, **{k: run[k] for k in ("run_id", "blocked", "passed", "abstained") if k in run}})
    return {
        "present": artifact is not None,
        "split": split_path,
        "case_count": len(cases),
        "cases": merged,
        "run": artifact,
        "detail": split_error,
    }


def _eval_store_dir() -> Path:
    env = os.environ.get("EVAL_STORE_DIR", "").strip()
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    if len(here.parents) > 2:
        candidate = here.parents[2] / "evals" / "results"
        if candidate.is_dir() or candidate.parent.is_dir():
            return candidate
    return Path("/tmp/citebench-evals")


@app.get("/traces/{run_id}")
def get_trace_detail(run_id: str) -> dict[str, Any]:
    settings = load_settings()
    item = get_trace(run_id, settings=settings)
    if item is None:
        raise HTTPException(status_code=404, detail=f"trace not found: {run_id}")
    return item.model_dump(mode="json")
