"""MANIFEST-only ingest: snapshot → parse → chunk → nomic embed → pgvector."""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any

from citebench_api.retrieval.chunking import chunk_text_dynamic
from citebench_api.persistence.db import (
    connect,
    corpus_stats,
    delete_unknown_documents,
    ensure_schema,
    finish_ingest_run,
    insert_chunks,
    mark_document_failed,
    replace_document,
    start_ingest_run,
    wipe_index,
)
from citebench_api.retrieval.embed import EmbedError, embed_texts
from citebench_api.ingest.manifest import ManifestDoc, parse_manifest
from citebench_api.ingest.parse_doc import parse_snapshot
from citebench_api.config import Settings
from citebench_api.ingest.snapshot import SnapshotError, build_http_client, load_snapshot, snapshot_url

log = logging.getLogger("citebench.ingest")
_PAGE_MARK = re.compile(r"\[page (\d+)\]")
_INGEST_LOCK = threading.Lock()


class IngestBusy(RuntimeError):
    pass


class WipeDisabled(PermissionError):
    pass


def format_text_ref(doc_id: str, chunk_id: str) -> str:
    return f"{doc_id}#{chunk_id}"


def run_ingest(
    settings: Settings,
    *,
    wipe: bool = False,
    simulate_failure_id: str | None = None,
    only_missing: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    if wipe and not settings.allow_wipe:
        raise WipeDisabled(
            "wipe is disabled. Set CITEBENCH_ALLOW_WIPE=1 on the API to allow a full index wipe."
        )
    if not _INGEST_LOCK.acquire(blocking=False):
        raise IngestBusy("ingest already running")
    try:
        return _run_ingest_locked(
            settings,
            wipe=wipe,
            simulate_failure_id=simulate_failure_id,
            only_missing=only_missing,
            limit=limit,
        )
    finally:
        _INGEST_LOCK.release()


def _run_ingest_locked(
    settings: Settings,
    *,
    wipe: bool,
    simulate_failure_id: str | None,
    only_missing: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    docs = parse_manifest(settings.manifest_path)
    manifest_ids = [doc.id for doc in docs]
    raw_root = settings.manifest_path.parent / "raw"
    raw_root.mkdir(parents=True, exist_ok=True)

    with connect(settings.database_url) as conn:
        ensure_schema(conn)
        if wipe:
            wipe_index(conn)
        if only_missing and not wipe:
            existing = {
                row["id"]
                for row in conn.execute(
                    "SELECT id FROM documents WHERE status = 'ok'"
                ).fetchall()
            }
            docs = [doc for doc in docs if doc.id not in existing]
        pending_total = len(docs)
        if limit is not None and limit > 0:
            docs = docs[:limit]
        run_id = start_ingest_run(conn)

    now = datetime.now(timezone.utc)
    pause = _ingest_pause()
    ok = 0
    failed = 0
    run_error: str | None = None

    try:
        with build_http_client() as client:
            for doc in docs:
                try:
                    _ingest_one(
                        settings,
                        doc,
                        raw_root=raw_root,
                        client=client,
                        now=now,
                        simulate_failure_id=simulate_failure_id,
                    )
                    ok += 1
                except Exception as exc:
                    failed += 1
                    log.warning("ingest failed for %s: %s", doc.id, exc)
                    try:
                        _record_failure(settings, doc, now, exc)
                    except Exception as record_exc:
                        log.exception(
                            "could not record ingest failure for %s: %s",
                            doc.id,
                            record_exc,
                        )
                if pause:
                    time.sleep(pause)
        with connect(settings.database_url) as conn:
            delete_unknown_documents(conn, manifest_ids)
    except Exception as exc:
        run_error = str(exc)
        log.exception("ingest run failed")

    with connect(settings.database_url) as conn:
        stats = corpus_stats(conn)
        if run_error:
            status = "failed"
        elif failed and ok:
            status = "partial"
        elif failed and not ok:
            status = "failed"
        else:
            status = "ok"
        finish_ingest_run(
            conn,
            run_id,
            status=status,
            doc_count=stats["doc_count"],
            page_count=stats["page_count"],
            chunk_count=stats["chunk_count"],
            failure_count=len(stats["failures"]),
            error=run_error,
        )
        stats = corpus_stats(conn)

    stats["run_status"] = "failed" if run_error else ("partial" if failed else "ok")
    stats["run_error"] = run_error
    stats["processed_count"] = ok + failed
    stats["failed_count"] = failed
    stats["pending_after"] = max(0, pending_total - (ok + failed))
    return stats


def _ingest_pause() -> float:
    """CITEBENCH_INGEST_PAUSE seconds between documents (default 0)."""
    raw = os.environ.get("CITEBENCH_INGEST_PAUSE", "").strip()
    if not raw:
        return 0.0
    try:
        value = float(raw)
    except ValueError:
        return 0.0
    return value if value > 0 else 0.0


def _ingest_one(
    settings: Settings,
    doc: ManifestDoc,
    *,
    raw_root,
    client,
    now: datetime,
    simulate_failure_id: str | None,
) -> None:
    if simulate_failure_id and doc.id == simulate_failure_id:
        raise SnapshotError(f"simulated unreachable snapshot for {doc.id}")

    if settings.snapshot_only:
        snap = load_snapshot(raw_root=raw_root, doc_id=doc.id)
    else:
        snap = snapshot_url(
            doc_id=doc.id,
            source_url=doc.source_url,
            raw_root=raw_root,
            client=client,
        )
    parsed = parse_snapshot(snap.path, snap.content_type)
    chunks = chunk_text_dynamic(
        parsed.text,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        tokenizer=settings.tokenizer,
    )
    if not chunks:
        raise ValueError("snapshot parsed to zero chunks")

    try:
        vectors = embed_texts([chunk.text for chunk in chunks], settings)
    except EmbedError:
        raise

    rows = []
    for chunk, vector in zip(chunks, vectors, strict=True):
        page = _page_for_chunk(chunk.text, parsed.page_count)
        rows.append(
            {
                "id": f"{doc.id}:{chunk.index}",
                "doc_id": doc.id,
                "chunk_index": chunk.index,
                "page": page,
                "section": chunk.section,
                "section_path": chunk.section,
                "url": doc.source_url,
                "text": chunk.text,
                "text_ref": format_text_ref(doc.id, f"{doc.id}:{chunk.index}"),
                "token_count": chunk.token_count,
                "embedding": vector,
            }
        )

    rel_snapshot = str(snap.path.relative_to(settings.corpus_dir))
    with connect(settings.database_url) as conn:
        replace_document(
            conn,
            doc_id=doc.id,
            title=doc.title,
            source_url=doc.source_url,
            version_or_snapshot=doc.version_or_snapshot,
            license=doc.license,
            sha256=snap.sha256,
            content_type=snap.content_type,
            snapshot_path=rel_snapshot,
            page_count=parsed.page_count,
            status="ok",
            error=None,
            indexed_at=now,
            doc_type=doc.doc_type,
            product=doc.product,
            source=doc.source,
        )
        insert_chunks(conn, rows)


def _record_failure(
    settings: Settings,
    doc: ManifestDoc,
    now: datetime,
    exc: BaseException,
) -> None:
    with connect(settings.database_url) as conn:
        mark_document_failed(
            conn,
            doc_id=doc.id,
            title=doc.title,
            source_url=doc.source_url,
            version_or_snapshot=doc.version_or_snapshot,
            license=doc.license,
            error=_error_text(exc),
            indexed_at=now,
            doc_type=doc.doc_type,
            product=doc.product,
            source=doc.source,
        )


def _error_text(exc: BaseException) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    return text[:1000]


def _page_for_chunk(text: str, fallback_pages: int) -> int:
    match = _PAGE_MARK.search(text)
    if match:
        return int(match.group(1))
    return 1 if fallback_pages >= 1 else 0
