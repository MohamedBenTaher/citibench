"""Download a MANIFEST URL into corpus/raw/<id>/ and record sha256."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx

DEFAULT_TIMEOUT = httpx.Timeout(45.0, connect=15.0)
USER_AGENT = (
    "CitebenchC2/0.2 (+https://github.com/MohamedBenTaher/citibench; frozen corpus snapshot)"
)


class SnapshotError(RuntimeError):
    """Unreachable or rejected snapshot. Callers must record a failure row."""


@dataclass(frozen=True)
class SnapshotResult:
    path: Path
    sha256: str
    content_type: str
    filename: str
    bytes_len: int


def snapshot_url(
    *,
    doc_id: str,
    source_url: str,
    raw_root: Path,
    client: httpx.Client,
) -> SnapshotResult:
    dest_dir = raw_root / doc_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        response = client.get(source_url, follow_redirects=True)
    except httpx.HTTPError as exc:
        raise SnapshotError(f"unreachable {source_url}: {exc}") from exc

    if response.status_code >= 400:
        raise SnapshotError(f"HTTP {response.status_code} fetching {source_url}")

    content_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
    filename = _filename_for(content_type, response.content)
    dest = dest_dir / filename
    dest.write_bytes(response.content)
    digest = hashlib.sha256(response.content).hexdigest()
    (dest_dir / "sha256").write_text(digest + "\n", encoding="utf-8")
    meta = {
        "id": doc_id,
        "source_url": source_url,
        "sha256": digest,
        "content_type": content_type or _guess_type(filename),
        "filename": filename,
        "bytes": len(response.content),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    (dest_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return SnapshotResult(
        path=dest,
        sha256=digest,
        content_type=meta["content_type"],
        filename=filename,
        bytes_len=len(response.content),
    )


def build_http_client() -> httpx.Client:
    return httpx.Client(
        timeout=DEFAULT_TIMEOUT,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf,*/*"},
        follow_redirects=True,
    )


def _filename_for(content_type: str, body: bytes) -> str:
    if "pdf" in content_type or body.startswith(b"%PDF"):
        return "document.pdf"
    return "page.html"


def _guess_type(filename: str) -> str:
    if filename.endswith(".pdf"):
        return "application/pdf"
    return "text/html"
