#!/usr/bin/env python
"""Crawl corpus/sources.yaml and write the pinned table in corpus/MANIFEST.md.

Deterministic: re-running over the same content produces the same table. Honors
robots.txt and throttles per host. Caches discovered pages to disk so an
interrupted crawl resumes instead of refetching. Not run in CI.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
import yaml
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCES = ROOT / "corpus" / "sources.yaml"
DEFAULT_MANIFEST = ROOT / "corpus" / "MANIFEST.md"
DEFAULT_CACHE = Path("/tmp/citebench-crawl")
USER_AGENT = (
    "CitebenchC2/0.2 (+https://github.com/MohamedBenTaher/citibench; frozen corpus manifest)"
)
SKIP_SUFFIXES = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".css", ".js",
    ".xml", ".json", ".zip", ".gz", ".tar", ".pdf", ".mp4", ".woff", ".woff2",
    ".rss", ".txt",
)
TIMEOUT = httpx.Timeout(45.0, connect=15.0)
MAX_CONSECUTIVE_ERRORS = 5


def normalize(url: str) -> str:
    url, _ = urldefrag(url)
    parsed = urlparse(url)
    return parsed._replace(query="", fragment="", path=parsed.path or "/").geturl()


def allowed(url: str, prefixes: tuple[str, ...]) -> bool:
    return any(url == p.rstrip("/") or url.startswith(p) for p in prefixes)


def slug_for(key: str, url: str) -> str:
    path = urlparse(url).path.strip("/")
    raw = f"{key}-{path}" if path else key
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip("-").lower()
    return slug[:80] or key


def _cell(value: object) -> str:
    return str(value).replace("|", "/").replace("\n", " ").strip()


def _robots(client: httpx.Client, seed: str) -> RobotFileParser:
    robots = RobotFileParser()
    parsed = urlparse(seed)
    url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        response = client.get(url)
        if response.status_code < 400:
            robots.parse(response.text.splitlines())
    except httpx.HTTPError:
        pass
    return robots


def _fetch(client: httpx.Client, url: str, *, retries: int, backoff: float) -> str | None:
    """GET with retries on transient network errors. Returns HTML text or None."""
    for attempt in range(retries):
        try:
            response = client.get(url)
        except httpx.HTTPError as exc:
            wait = backoff * (2**attempt)
            print(f"  retry {url} ({exc}); sleeping {wait:.1f}s", file=sys.stderr)
            time.sleep(wait)
            continue
        return response.text if response.status_code < 400 else None
    return None


def _extract(page_url: str, html: str, prefixes: tuple[str, ...]) -> tuple[str, list[str]]:
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(strip=True) if soup.title else ""
    links: list[str] = []
    for anchor in soup.find_all("a", href=True):
        nxt = normalize(urljoin(page_url, anchor["href"]))
        if nxt not in links and allowed(nxt, prefixes):
            links.append(nxt)
    return title, links


def crawl_source(
    source: dict,
    client: httpx.Client,
    *,
    cache: dict,
    delay: float,
    max_pages: int | None,
    retries: int,
    cached_only: bool = False,
) -> tuple[list[dict], bool]:
    key = str(source["key"])
    prefixes = tuple(source["allow_prefixes"])
    cap = int(max_pages or source.get("max_pages", 500))
    robots = _robots(client, source["seeds"][0])

    queue = [normalize(u) for u in source["seeds"]]
    seen: set[str] = set()
    rows: list[dict] = []
    last_host = ""
    last_time = 0.0
    consecutive_errors = 0
    fetched = 0
    interrupted = False

    while queue and len(rows) < cap:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        if not allowed(url, prefixes):
            continue
        path = urlparse(url).path
        if any(path.endswith(suffix) for suffix in SKIP_SUFFIXES):
            continue
        if not robots.can_fetch(USER_AGENT, url):
            continue

        cached = cache.get(url)
        if cached is None and cached_only:
            continue
        if cached is None:
            host = urlparse(url).netloc
            if host == last_host:
                elapsed = time.monotonic() - last_time
                if elapsed < delay:
                    time.sleep(delay - elapsed)
            html = _fetch(client, url, retries=retries, backoff=1.0)
            last_host, last_time = host, time.monotonic()
            if html is None:
                consecutive_errors += 1
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    print(f"  STOP {key}: {consecutive_errors} consecutive fetch failures", file=sys.stderr)
                    interrupted = True
                    break
                continue
            consecutive_errors = 0
            title, links = _extract(url, html, prefixes)
            cached = {"title": title, "links": links}
            cache[url] = cached
            fetched += 1
            if fetched % 50 == 0:
                print(f"  {key}: fetched {fetched}, discovered {len(cache)} pages", file=sys.stderr)

        title = str(cached.get("title") or "") or slug_for(key, url)
        rows.append(
            {
                "id": slug_for(key, url),
                "title": title,
                "source_url": url,
                "license": source["license"],
                "doc_type": source.get("doc_type", ""),
                "product": source.get("product", ""),
                "source": source.get("source", urlparse(url).netloc),
            }
        )
        for link in cached.get("links", []):
            if link not in seen:
                queue.append(link)

    return rows, interrupted


def crawl_pdf_source(source: dict) -> list[dict]:
    """Explicit PDF list (no link discovery, no fetch). Titles from `titles` map or filename."""
    key = str(source["key"])
    host = str(source.get("source", "")).lower()
    titles = source.get("titles", {}) or {}
    rows: list[dict] = []
    for url in source.get("pdfs", []):
        parsed = urlparse(url)
        if host and parsed.netloc.lower() != host:
            print(f"  skip off-host pdf: {url}", file=sys.stderr)
            continue
        stem = Path(parsed.path).stem
        rows.append(
            {
                "id": slug_for(key, url),
                "title": str(titles.get(url) or stem),
                "source_url": url,
                "license": source["license"],
                "doc_type": source.get("doc_type", ""),
                "product": source.get("product", ""),
                "source": source.get("source", parsed.netloc),
                "pages": 0,
            }
        )
    return rows


def dedupe_ids(rows: list[dict]) -> list[dict]:
    seen: dict[str, int] = {}
    for row in rows:
        base = row["id"]
        if base in seen:
            seen[base] += 1
            row["id"] = f"{base}-{seen[base]}"
        else:
            seen[base] = 0
    return rows


def render_manifest(existing_text: str, rows: list[dict], freeze_version: str) -> str:
    lines = existing_text.splitlines()
    header_idx = next(
        (i for i, line in enumerate(lines) if line.strip().startswith("|") and "source_url" in line),
        None,
    )
    if header_idx is None:
        raise ValueError("MANIFEST.md has no markdown table with a source_url column")
    end = header_idx
    while end + 1 < len(lines) and lines[end + 1].strip().startswith("|"):
        end += 1

    table = [
        "| id | title | source_url | version_or_snapshot | license | pages | doc_type | product | source |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in sorted(rows, key=lambda r: (str(r["source"]), str(r["source_url"]))):
        table.append(
            "| {id} | {title} | {url} | {version} | {license} | {pages} | {doc_type} | {product} | {source} |".format(
                id=_cell(row["id"]),
                title=_cell(row["title"]),
                url=_cell(row["source_url"]),
                version=_cell(freeze_version),
                license=_cell(row["license"]),
                pages=_cell(row.get("pages", 1)),
                doc_type=_cell(row["doc_type"]),
                product=_cell(row["product"]),
                source=_cell(row["source"]),
            )
        )

    updated = lines[:header_idx] + table + lines[end + 1 :]
    text = "\n".join(updated) + "\n"
    text = re.sub(r"Freeze date: \*\*.*?\*\*", f"Freeze date: **{freeze_version}**", text)
    text = re.sub(r"docs=\d+", f"docs={len(rows)}", text)
    return text


def _load_cache(cache_dir: Path) -> dict:
    path = cache_dir / "pages.json"
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _save_cache(cache_dir: Path, cache: dict) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / "pages.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cache), encoding="utf-8")
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Crawl doc sources into corpus/MANIFEST.md.")
    parser.add_argument("--sources", default=str(DEFAULT_SOURCES))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--source", action="append", default=[], help="only this source key (repeatable)")
    parser.add_argument("--max-pages", type=int, default=None, help="override per-source cap")
    parser.add_argument("--delay", type=float, default=0.5, help="seconds between same-host requests")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE))
    parser.add_argument("--min-rows", type=int, default=0, help="refuse to write below this total")
    parser.add_argument("--cached-only", action="store_true", help="never fetch; use cached pages only")
    parser.add_argument("--write", action="store_true", help="write the manifest (default: dry run)")
    args = parser.parse_args(argv)

    config = yaml.safe_load(Path(args.sources).read_text(encoding="utf-8")) or {}
    sources = config.get("sources", [])
    selected = set(args.source)
    if selected:
        sources = [s for s in sources if s["key"] in selected]
    if not sources:
        print("no sources selected", file=sys.stderr)
        return 2

    cache_dir = Path(args.cache_dir)
    cache = _load_cache(cache_dir)
    print(f"cache: {len(cache)} pages from {cache_dir}", file=sys.stderr)

    all_rows: list[dict] = []
    interrupted: list[str] = []
    with httpx.Client(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}, follow_redirects=True) as client:
        for source in sources:
            print(f"crawl {source['key']} …", file=sys.stderr)
            if source.get("kind") == "pdf":
                rows, hit_wall = crawl_pdf_source(source), False
            else:
                rows, hit_wall = crawl_source(
                    source,
                    client,
                    cache=cache,
                    delay=args.delay,
                    max_pages=args.max_pages,
                    retries=args.retries,
                    cached_only=args.cached_only,
                )
            _save_cache(cache_dir, cache)
            print(f"  {source['key']}: {len(rows)} pages, license={source['license']}", file=sys.stderr)
            all_rows.extend(rows)
            if hit_wall:
                interrupted.append(source["key"])

    all_rows = dedupe_ids(all_rows)
    print(f"total: {len(all_rows)} rows; cache {len(cache)} pages")
    if interrupted:
        print(f"interrupted: {', '.join(interrupted)} (re-run to resume from cache)", file=sys.stderr)
    if not args.write:
        print("(dry run — pass --write to update the manifest)")
        return 0
    if len(all_rows) < args.min_rows:
        print(f"refusing to write: {len(all_rows)} rows < --min-rows {args.min_rows}", file=sys.stderr)
        return 1
    if interrupted:
        print("refusing to write an interrupted crawl; re-run to resume", file=sys.stderr)
        return 1

    manifest_path = Path(args.manifest)
    text = render_manifest(
        manifest_path.read_text(encoding="utf-8"),
        all_rows,
        str(config.get("freeze_version", "")),
    )
    manifest_path.write_text(text, encoding="utf-8")
    print(f"wrote {manifest_path} ({len(all_rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
