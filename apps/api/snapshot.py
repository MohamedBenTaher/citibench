"""Download a URL into corpus/raw/<id>/ and record sha256."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx

from fetch_guard import UnsafeSource, assert_fetchable_https

DEFAULT_TIMEOUT = httpx.Timeout(45.0, connect=15.0)
USER_AGENT = (
    "CitebenchC2/0.2 (+https://github.com/MohamedBenTaher/citibench; frozen corpus snapshot)"
)
_STREAM_CHUNK = 64 * 1024


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
    _write_meta(
        dest_dir,
        doc_id=doc_id,
        source_url=source_url,
        digest=digest,
        content_type=content_type or _guess_type(filename),
        filename=filename,
        bytes_len=len(response.content),
    )
    return SnapshotResult(
        path=dest,
        sha256=digest,
        content_type=content_type or _guess_type(filename),
        filename=filename,
        bytes_len=len(response.content),
    )


def snapshot_url_streamed(
    *,
    doc_id: str,
    source_url: str,
    raw_root: Path,
    client: httpx.Client,
    max_bytes: int,
) -> SnapshotResult:
    try:
        assert_fetchable_https(source_url)
    except UnsafeSource as exc:
        raise SnapshotError(str(exc)) from exc

    dest_dir = raw_root / doc_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp = dest_dir / "download.bin"
    hasher = hashlib.sha256()
    written = 0
    content_type = ""
    try:
        with client.stream("GET", source_url, follow_redirects=True) as response:
            if response.status_code >= 400:
                raise SnapshotError(f"HTTP {response.status_code} fetching {source_url}")
            try:
                assert_fetchable_https(str(response.url))
            except UnsafeSource as exc:
                raise SnapshotError(str(exc)) from exc
            declared = response.headers.get("content-length")
            if declared and declared.isdigit() and int(declared) > max_bytes:
                raise SnapshotError(f"source exceeds max bytes ({max_bytes})")
            content_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
            with tmp.open("wb") as handle:
                for piece in response.iter_bytes(_STREAM_CHUNK):
                    written += len(piece)
                    if written > max_bytes:
                        raise SnapshotError(f"source exceeds max bytes ({max_bytes})")
                    handle.write(piece)
                    hasher.update(piece)
    except httpx.HTTPError as exc:
        tmp.unlink(missing_ok=True)
        raise SnapshotError(f"unreachable {source_url}: {exc}") from exc
    except SnapshotError:
        tmp.unlink(missing_ok=True)
        raise

    head = tmp.read_bytes()[:8]
    filename = _filename_for(content_type, head)
    dest = dest_dir / filename
    tmp.replace(dest)
    digest = hasher.hexdigest()
    resolved_type = content_type or _guess_type(filename)
    _write_meta(
        dest_dir,
        doc_id=doc_id,
        source_url=source_url,
        digest=digest,
        content_type=resolved_type,
        filename=filename,
        bytes_len=written,
    )
    return SnapshotResult(
        path=dest,
        sha256=digest,
        content_type=resolved_type,
        filename=filename,
        bytes_len=written,
    )


def build_http_client() -> httpx.Client:
    return httpx.Client(
        timeout=DEFAULT_TIMEOUT,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf,*/*"},
        follow_redirects=True,
    )


def _write_meta(
    dest_dir: Path,
    *,
    doc_id: str,
    source_url: str,
    digest: str,
    content_type: str,
    filename: str,
    bytes_len: int,
) -> None:
    (dest_dir / "sha256").write_text(digest + "\n", encoding="utf-8")
    meta = {
        "id": doc_id,
        "source_url": source_url,
        "sha256": digest,
        "content_type": content_type,
        "filename": filename,
        "bytes": bytes_len,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    (dest_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def _filename_for(content_type: str, body: bytes) -> str:
    if "pdf" in content_type or body.startswith(b"%PDF"):
        return "document.pdf"
    return "page.html"


def _guess_type(filename: str) -> str:
    if filename.endswith(".pdf"):
        return "application/pdf"
    return "text/html"
