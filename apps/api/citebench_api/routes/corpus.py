"""Corpus browsing: frozen index plus reviewer-owned sources/uploads."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from citebench_api.persistence.db import (
    connect,
    corpus_facets,
    corpus_stats,
    database_unavailable_detail,
    get_chunks_by_ids,
    get_document,
    is_database_error,
    list_documents,
)
from citebench_api.routes.errors import runtime_http_error
from citebench_api.config import Settings, load_settings
from citebench_api.suggestions import generate_suggestions
from citebench_api.ingest.user_ingest import SourceRejected, ingest_user_upload, ingest_user_url

router = APIRouter()

_FREEZE_RE = re.compile(r"Freeze date:\s*\*\*(.+?)\*\*")


def _manifest_freeze_date(settings: Settings) -> str | None:
    try:
        text = settings.manifest_path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = _FREEZE_RE.search(text)
    return match.group(1).strip() if match else None


class SourceRequest(BaseModel):
    url: str
    title: str | None = None


def _db_unavailable(exc: Exception, settings: Settings) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=database_unavailable_detail(exc, settings.database_url),
    )


@router.get("/corpus/stats")
def get_corpus_stats() -> dict[str, Any]:
    settings = load_settings()
    try:
        with connect(settings.database_url) as conn:
            payload = corpus_stats(conn)
    except Exception as exc:
        raise _db_unavailable(exc, settings) from exc
    payload["freeze_date"] = _manifest_freeze_date(settings)
    return payload


@router.get("/corpus/facets")
def get_corpus_facets() -> dict[str, Any]:
    """Distinct product / source / doc_type / origin values for browser filters."""
    settings = load_settings()
    try:
        with connect(settings.database_url) as conn:
            return corpus_facets(conn)
    except Exception as exc:
        raise _db_unavailable(exc, settings) from exc


@router.get("/corpus/suggestions")
def get_corpus_suggestions(
    limit: int = Query(default=6, ge=1, le=12),
) -> dict[str, Any]:
    """Corpus-grounded question suggestions (LLM over corpus macro, template fallback)."""
    settings = load_settings()
    try:
        with connect(settings.database_url) as conn:
            return generate_suggestions(settings, conn, limit=limit)
    except Exception as exc:
        raise _db_unavailable(exc, settings) from exc


@router.get("/corpus/documents")
def get_corpus_documents(
    q: str | None = Query(default=None, description="search id, title, or source URL"),
    product: str | None = Query(default=None),
    source: str | None = Query(default=None),
    origin: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Browse the frozen corpus so a reviewer can see what is askable."""
    settings = load_settings()
    try:
        with connect(settings.database_url) as conn:
            return list_documents(
                conn,
                query=(q or "").strip() or None,
                product=product,
                source=source,
                origin=origin,
                status=status,
                limit=limit,
                offset=offset,
            )
    except Exception as exc:
        raise _db_unavailable(exc, settings) from exc


@router.get("/corpus/documents/{doc_id}")
def get_corpus_document(
    doc_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """One document plus a page of section/page chunk previews."""
    settings = load_settings()
    try:
        with connect(settings.database_url) as conn:
            payload = get_document(conn, doc_id, limit=limit, offset=offset)
    except Exception as exc:
        raise _db_unavailable(exc, settings) from exc
    if payload is None:
        raise HTTPException(status_code=404, detail=f"document not found: {doc_id}")
    return payload


@router.get("/corpus/chunks")
def get_corpus_chunk_text(
    ids: str = Query(..., description="comma-separated chunk ids (max 24)"),
) -> dict[str, Any]:
    """Full text for cited chunk previews (Playground sources)."""
    requested = [item.strip() for item in ids.split(",") if item.strip()][:24]
    settings = load_settings()
    try:
        with connect(settings.database_url) as conn:
            chunks = get_chunks_by_ids(conn, requested)
    except Exception as exc:
        raise _db_unavailable(exc, settings) from exc
    return {"chunks": chunks}


@router.post("/corpus/sources")
def post_corpus_source(body: SourceRequest) -> dict[str, Any]:
    settings = load_settings()
    url = (body.url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="url is required")
    try:
        return ingest_user_url(settings, url, body.title)
    except SourceRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise runtime_http_error(exc) from exc
    except Exception as exc:
        if is_database_error(exc):
            raise _db_unavailable(exc, settings) from exc
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/corpus/uploads")
def post_corpus_upload(
    file: UploadFile,
    title: str | None = Form(None),
) -> dict[str, Any]:
    settings = load_settings()
    name = Path(file.filename or "upload.bin").name
    if not name or name.startswith("."):
        raise HTTPException(status_code=400, detail="upload filename is required")
    incoming = settings.corpus_dir / "raw" / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    dest = incoming / name
    written = 0
    try:
        with dest.open("wb") as handle:
            while True:
                piece = file.file.read(64 * 1024)
                if not piece:
                    break
                written += len(piece)
                if written > settings.user_source_max_bytes:
                    dest.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"source exceeds max bytes ({settings.user_source_max_bytes})",
                    )
                handle.write(piece)
        return ingest_user_upload(
            settings,
            dest=dest,
            filename=name,
            title=title,
            source_label=f"upload:{name}",
        )
    except HTTPException:
        raise
    except SourceRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise runtime_http_error(exc) from exc
    except Exception as exc:
        if is_database_error(exc):
            raise _db_unavailable(exc, settings) from exc
        raise HTTPException(status_code=500, detail=str(exc)) from exc
