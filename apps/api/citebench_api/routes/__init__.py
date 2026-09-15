"""HTTP layer for the Citebench API.

Each module here owns one resource's endpoints (and their request models).
Domain logic lives in the sibling service modules (retrieve, generate, trace,
...); this package only translates HTTP to service calls. `main.py` assembles
the app via `create_app()` and stays the uvicorn entry point.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from citebench_api.persistence.db import connect, ensure_schema
from citebench_api.retrieval.embed import warmup_local_embed
from citebench_api.retrieval.rerank import warmup_ranker
from citebench_api.config import Settings, load_settings
from citebench_api.routes import ask, corpus, evals, health, ingest, observability

_WARMUP_SKIP_VALUES = frozenset({"1", "true", "yes"})

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("citebench.api")


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


def create_app() -> FastAPI:
    app = FastAPI(title="Citebench API", version="0.9.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for router in (health.router, ingest.router, ask.router, corpus.router, observability.router, evals.router):
        app.include_router(router)
    return app
