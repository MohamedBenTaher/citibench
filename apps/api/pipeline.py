"""MANIFEST-only ingest: snapshot → parse → chunk → nomic embed → pgvector."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from chunking import chunk_text
from db import (
    connect,
    corpus_stats,
    delete_unknown_documents,
    ensure_schema,
    finish_ingest_run,
    insert_chunks,
    replace_document,
    start_ingest_run,
    wipe_index,
)
from embed import EmbedError, embed_texts
from manifest import ManifestDoc, parse_manifest
from parse_doc import parse_snapshot
from settings import Settings
from snapshot import SnapshotError, build_http_client, snapshot_url

log = logging.getLogger("citebench.ingest")
_PAGE_MARK = re.compile(r"\[page (\d+)\]")


def run_ingest(
    settings: Settings,
    *,
    wipe: bool = False,
    simulate_failure_id: str | None = None,
) -> dict[str, Any]:
    docs = parse_manifest(settings.manifest_path)
    raw_root = settings.corpus_dir / "raw"
    raw_root.mkdir(parents=True, exist_ok=True)

    with connect(settings.database_url) as conn:
        ensure_schema(conn)
        if wipe:
            wipe_index(conn)
        run_id = start_ingest_run(conn)

    now = datetime.now(timezone.utc)
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
                    _record_failure(settings, doc, now, exc)
        with connect(settings.database_url) as conn:
            delete_unknown_documents(conn, [doc.id for doc in docs])
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
    return stats


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

    snap = snapshot_url(
        doc_id=doc.id,
        source_url=doc.source_url,
        raw_root=raw_root,
        client=client,
    )
    parsed = parse_snapshot(snap.path, snap.content_type)
    chunks = chunk_text(
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
                "text": chunk.text,
                "text_ref": f"{doc.id}#chunk-{chunk.index}",
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
        )
        insert_chunks(conn, rows)


def _record_failure(
    settings: Settings,
    doc: ManifestDoc,
    now: datetime,
    exc: BaseException,
) -> None:
    with connect(settings.database_url) as conn:
        replace_document(
            conn,
            doc_id=doc.id,
            title=doc.title,
            source_url=doc.source_url,
            version_or_snapshot=doc.version_or_snapshot,
            license=doc.license,
            sha256=None,
            content_type=None,
            snapshot_path=None,
            page_count=0,
            status="failed",
            error=_error_text(exc),
            indexed_at=now,
        )


def _error_text(exc: BaseException) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    return text[:1000]


def _page_for_chunk(text: str, fallback_pages: int) -> int:
    match = _PAGE_MARK.search(text)
    if match:
        return int(match.group(1))
    return 1 if fallback_pages >= 1 else 0
