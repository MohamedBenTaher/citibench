"""Index a user HTTPS URL or uploaded file without touching the eval freeze."""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from chunking import chunk_text_dynamic
from db import connect, corpus_stats, insert_chunks, replace_document, start_ingest_run, finish_ingest_run
from embed import embed_texts
from fetch_guard import UnsafeSource, assert_fetchable_https
from parse_doc import parse_snapshot
from pipeline import IngestBusy, _INGEST_LOCK, format_text_ref
from settings import Settings
from snapshot import SnapshotError, SnapshotResult, build_http_client, snapshot_url_streamed

log = logging.getLogger("citebench.user_ingest")
_PAGE_MARK = re.compile(r"\[page (\d+)\]")


class SourceRejected(RuntimeError):
    pass


def ingest_user_url(settings: Settings, url: str, title: str | None = None) -> dict:
    try:
        assert_fetchable_https(url)
    except UnsafeSource as exc:
        raise SourceRejected(str(exc)) from exc
    if not _INGEST_LOCK.acquire(blocking=False):
        raise IngestBusy("ingest already running")
    try:
        return _ingest_user_url_locked(settings, url.strip(), title)
    finally:
        _INGEST_LOCK.release()


def ingest_user_upload(
    settings: Settings,
    *,
    dest: Path,
    filename: str,
    title: str | None,
    source_label: str,
) -> dict:
    if not _INGEST_LOCK.acquire(blocking=False):
        raise IngestBusy("ingest already running")
    try:
        return _index_local_file(
            settings,
            dest=dest,
            filename=filename,
            title=title,
            source_label=source_label,
        )
    finally:
        _INGEST_LOCK.release()


def _ingest_user_url_locked(settings: Settings, url: str, title: str | None) -> dict:
    doc_id = "user-" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    host = urlparse(url).hostname or "source"
    display = (title or "").strip() or host
    raw_root = settings.corpus_dir / "raw"
    raw_root.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    with connect(settings.database_url) as conn:
        run_id = start_ingest_run(conn)
    client = build_http_client()
    try:
        snap = snapshot_url_streamed(
            doc_id=doc_id,
            source_url=url,
            raw_root=raw_root,
            client=client,
            max_bytes=settings.user_source_max_bytes,
        )
        _index_snapshot(
            settings,
            doc_id=doc_id,
            title=display,
            source_url=url,
            snap=snap,
            now=now,
        )
        status = "ok"
        error = None
    except (SnapshotError, SourceRejected, UnsafeSource, ValueError) as exc:
        status = "failed"
        error = str(exc)[:1000]
        log.warning("user ingest failed for %s: %s", url, exc)
        raise SourceRejected(error) from exc
    except Exception as exc:
        status = "failed"
        error = str(exc)[:1000]
        log.warning("user ingest failed for %s: %s", url, exc)
        raise
    finally:
        client.close()
        with connect(settings.database_url) as conn:
            stats = corpus_stats(conn)
            finish_ingest_run(
                conn,
                run_id,
                status=status if error is None else "failed",
                doc_count=stats["doc_count"],
                page_count=stats["page_count"],
                chunk_count=stats["chunk_count"],
                failure_count=len(stats["failures"]),
                error=error,
            )
            stats = corpus_stats(conn)
    stats["run_status"] = status
    stats["run_error"] = error
    stats["doc_id"] = doc_id
    return stats


def _index_local_file(
    settings: Settings,
    *,
    dest: Path,
    filename: str,
    title: str | None,
    source_label: str,
) -> dict:
    size = dest.stat().st_size
    if size > settings.user_source_max_bytes:
        dest.unlink(missing_ok=True)
        raise SourceRejected(f"source exceeds max bytes ({settings.user_source_max_bytes})")
    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    # Streaming hash would be better; cap is 64MiB in this slice.
    doc_id = "user-" + digest[:16]
    content_type = "application/pdf" if filename.lower().endswith(".pdf") else "text/html"
    snap = SnapshotResult(
        path=dest,
        sha256=digest,
        content_type=content_type,
        filename=filename,
        bytes_len=size,
    )
    now = datetime.now(timezone.utc)
    with connect(settings.database_url) as conn:
        run_id = start_ingest_run(conn)
    try:
        _index_snapshot(
            settings,
            doc_id=doc_id,
            title=(title or "").strip() or filename,
            source_url=source_label,
            snap=snap,
            now=now,
        )
        status = "ok"
        error = None
    except Exception as exc:
        status = "failed"
        error = str(exc)[:1000]
        raise
    finally:
        with connect(settings.database_url) as conn:
            stats = corpus_stats(conn)
            finish_ingest_run(
                conn,
                run_id,
                status=status if error is None else "failed",
                doc_count=stats["doc_count"],
                page_count=stats["page_count"],
                chunk_count=stats["chunk_count"],
                failure_count=len(stats["failures"]),
                error=error,
            )
            stats = corpus_stats(conn)
    stats["run_status"] = status
    stats["run_error"] = error
    stats["doc_id"] = doc_id
    return stats


def _index_snapshot(
    settings: Settings,
    *,
    doc_id: str,
    title: str,
    source_url: str,
    snap: SnapshotResult,
    now: datetime,
) -> None:
    parsed = parse_snapshot(snap.path, snap.content_type)
    chunks = chunk_text_dynamic(
        parsed.text,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        tokenizer=settings.tokenizer,
    )
    if not chunks:
        raise ValueError("snapshot parsed to zero chunks")
    vectors = embed_texts([chunk.text for chunk in chunks], settings)
    rows = []
    for chunk, vector in zip(chunks, vectors, strict=True):
        page = _page_for_chunk(chunk.text, parsed.page_count)
        rows.append(
            {
                "id": f"{doc_id}:{chunk.index}",
                "doc_id": doc_id,
                "chunk_index": chunk.index,
                "page": page,
                "text": chunk.text,
                "text_ref": format_text_ref(doc_id, f"{doc_id}:{chunk.index}"),
                "token_count": chunk.token_count,
                "embedding": vector,
            }
        )
    rel_snapshot = str(snap.path.relative_to(settings.corpus_dir))
    with connect(settings.database_url) as conn:
        replace_document(
            conn,
            doc_id=doc_id,
            title=title,
            source_url=source_url,
            version_or_snapshot=snap.sha256[:12],
            license="user-provided",
            sha256=snap.sha256,
            content_type=snap.content_type,
            snapshot_path=rel_snapshot,
            page_count=parsed.page_count,
            status="ok",
            error=None,
            indexed_at=now,
            origin="user",
        )
        insert_chunks(conn, rows)


def _page_for_chunk(text: str, page_count: int) -> int | None:
    match = _PAGE_MARK.search(text or "")
    if match:
        return int(match.group(1))
    if page_count <= 0:
        return None
    return 1
