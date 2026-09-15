"""Parse the frozen corpus/MANIFEST.md table. No documents outside that table."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_URL_RE = re.compile(r"^https?://")


@dataclass(frozen=True)
class ManifestDoc:
    id: str
    title: str
    source_url: str
    version_or_snapshot: str
    license: str
    doc_type: str | None = None
    product: str | None = None
    source: str | None = None


def parse_manifest(path: Path) -> list[ManifestDoc]:
    if not path.is_file():
        raise FileNotFoundError(f"MANIFEST not found: {path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    header_idx = next(
        (i for i, line in enumerate(lines) if line.strip().startswith("|") and "source_url" in line),
        None,
    )
    if header_idx is None:
        raise ValueError(f"{path} has no markdown table with a source_url column")

    headers = _split_row(lines[header_idx])
    required = ["id", "title", "source_url", "version_or_snapshot", "license"]
    missing = [name for name in required if name not in headers]
    if missing:
        raise ValueError(f"{path} table missing columns: {missing}")

    docs: list[ManifestDoc] = []
    seen: set[str] = set()
    for line in lines[header_idx + 1 :]:
        stripped = line.strip()
        if not stripped.startswith("|"):
            if docs:
                break
            continue
        cells = _split_row(stripped)
        if not cells or set(cells) <= {"", "---"} or all(set(cell) <= {"-"} for cell in cells):
            continue
        if len(cells) < len(headers):
            raise ValueError(f"short MANIFEST row: {stripped}")
        row = dict(zip(headers, cells, strict=False))
        doc_id = row["id"]
        if not _ID_RE.match(doc_id):
            raise ValueError(f"invalid manifest id: {doc_id!r}")
        if doc_id in seen:
            raise ValueError(f"duplicate manifest id: {doc_id}")
        if not _URL_RE.match(row["source_url"]):
            raise ValueError(f"manifest {doc_id} source_url must be http(s)")
        seen.add(doc_id)
        docs.append(
            ManifestDoc(
                id=doc_id,
                title=row["title"],
                source_url=row["source_url"],
                version_or_snapshot=row["version_or_snapshot"],
                license=row["license"],
                doc_type=_opt(row.get("doc_type")),
                product=_opt(row.get("product")),
                source=_opt(row.get("source")),
            )
        )

    if not docs:
        raise ValueError(f"{path} pinned document table is empty")
    return docs


def _opt(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]
