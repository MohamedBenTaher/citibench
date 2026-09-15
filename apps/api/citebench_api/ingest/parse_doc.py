"""Turn a frozen HTML or PDF snapshot into plain text plus a page count."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup
from pypdf import PdfReader

_DROP_TAGS = (
    "script",
    "style",
    "noscript",
    "nav",
    "footer",
    "header",
    "aside",
    "form",
    "iframe",
)


@dataclass(frozen=True)
class ParsedDocument:
    text: str
    page_count: int
    content_type: str


def parse_snapshot(path: Path, content_type: str) -> ParsedDocument:
    data = path.read_bytes()
    if _is_pdf(content_type, path, data):
        return _parse_pdf(path)
    return _parse_html(data)


def _is_pdf(content_type: str, path: Path, data: bytes) -> bool:
    if "pdf" in content_type.lower() or path.suffix.lower() == ".pdf":
        return True
    return data.startswith(b"%PDF")


def _parse_pdf(path: Path) -> ParsedDocument:
    reader = PdfReader(str(path))
    pages: list[str] = []
    for i, page in enumerate(reader.pages, start=1):
        extracted = page.extract_text() or ""
        pages.append(f"[page {i}]\n{extracted.strip()}")
    text = "\n\n".join(part for part in pages if part.strip())
    if not text.strip():
        raise ValueError("PDF produced no extractable text")
    return ParsedDocument(text=text, page_count=len(reader.pages), content_type="application/pdf")


def _parse_html(data: bytes) -> ParsedDocument:
    soup = BeautifulSoup(data, "lxml")
    for tag in soup(_DROP_TAGS):
        tag.decompose()
    root = (
        soup.select_one("main")
        or soup.select_one("article")
        or soup.select_one(".td-content")
        or soup.select_one("#td-content")
        or soup.select_one(".content")
        or soup.body
        or soup
    )
    for heading in root.find_all(["h1", "h2", "h3", "h4"]):
        level = int(heading.name[1])
        marker = "#" * level + " " + heading.get_text(" ", strip=True)
        heading.clear()
        heading.append(marker)
    text = root.get_text("\n", strip=True)
    text = _collapse_blank_lines(text)
    if not text:
        raise ValueError("HTML produced no extractable text")
    # One URL snapshot is one documentation page.
    return ParsedDocument(text=text, page_count=1, content_type="text/html")


def _collapse_blank_lines(text: str) -> str:
    lines = [line.rstrip() for line in text.splitlines()]
    compact: list[str] = []
    blank = False
    for line in lines:
        if not line.strip():
            if not blank and compact:
                compact.append("")
            blank = True
            continue
        compact.append(line)
        blank = False
    return "\n".join(compact).strip()
