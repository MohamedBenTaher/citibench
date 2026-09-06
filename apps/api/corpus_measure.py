"""Measure MANIFEST corpus size without embedding (no Groq)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from chunking import chunk_text
from manifest import ManifestDoc, parse_manifest
from parse_doc import parse_snapshot
from settings import Settings, load_settings
from snapshot import SnapshotError, build_http_client, snapshot_url


def measure_corpus(
    *,
    settings: Settings | None = None,
    fetch_missing: bool = False,
    raw_root: Path | None = None,
) -> dict[str, Any]:
    """Count docs/pages/chunks from local snapshots, optionally fetching HTML."""
    resolved = settings if settings is not None else load_settings()
    docs = parse_manifest(resolved.manifest_path)
    root = raw_root if raw_root is not None else resolved.corpus_dir / "raw"
    per_doc: list[dict[str, Any]] = []
    pages = 0
    chunks = 0
    fetched = 0
    missing: list[str] = []

    client = build_http_client() if fetch_missing else None
    try:
        for doc in docs:
            row = _measure_one(doc, root=root, client=client, settings=resolved)
            per_doc.append(row)
            if row.get("error"):
                missing.append(doc.id)
                continue
            pages += int(row["pages"])
            chunks += int(row["chunks"])
            if row.get("fetched"):
                fetched += 1
    finally:
        if client is not None:
            client.close()

    measured_under = (
        f"live-html-fetch-{datetime.now(timezone.utc).date().isoformat()}"
        if fetched
        else "local-snapshots"
    )
    return {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "measured_under": measured_under,
        "method": {
            "docs": "count of pinned URLs in corpus/MANIFEST.md",
            "pages": "HTML snapshot = 1 page; PDF = PdfReader page count",
            "chunks": (
                f"tiktoken {resolved.tokenizer} windows of "
                f"{resolved.chunk_size}/{resolved.chunk_overlap}"
            ),
        },
        "freeze_date": "2026-09-05",
        "docs": len(docs),
        "pages": pages if len(missing) == 0 else None,
        "chunks": chunks if len(missing) == 0 else None,
        "fetched": fetched,
        "missing": missing,
        "per_doc": per_doc,
    }


def write_corpus_artifact(payload: dict[str, Any], dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return dest


def _measure_one(
    doc: ManifestDoc,
    *,
    root: Path,
    client: Any,
    settings: Settings,
) -> dict[str, Any]:
    local = _existing_snapshot(root / doc.id)
    fetched = False
    if local is None:
        if client is None:
            return {
                "id": doc.id,
                "error": "no local snapshot",
                "pages": 0,
                "chunks": 0,
                "tokens": 0,
                "fetched": False,
            }
        try:
            snap = snapshot_url(
                doc_id=doc.id,
                source_url=doc.source_url,
                raw_root=root,
                client=client,
            )
        except SnapshotError as exc:
            return {
                "id": doc.id,
                "error": str(exc),
                "pages": 0,
                "chunks": 0,
                "tokens": 0,
                "fetched": False,
            }
        local = snap.path
        fetched = True

    parsed = parse_snapshot(local, "")
    pieces = chunk_text(
        parsed.text,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        tokenizer=settings.tokenizer,
    )
    return {
        "id": doc.id,
        "error": None,
        "pages": parsed.page_count,
        "chunks": len(pieces),
        "tokens": sum(item.token_count for item in pieces),
        "fetched": fetched,
        "content_type": parsed.content_type,
    }


def _existing_snapshot(dest_dir: Path) -> Path | None:
    if not dest_dir.is_dir():
        return None
    for name in ("page.html", "document.pdf"):
        path = dest_dir / name
        if path.is_file():
            return path
    return None
