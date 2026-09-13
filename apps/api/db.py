"""Postgres helpers: schema ensure, freeze-safe upserts, corpus stats."""

from __future__ import annotations

import logging
import re
import socket
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime
from typing import Any
from urllib.parse import urlparse, urlunparse

import psycopg
from psycopg.rows import dict_row

log = logging.getLogger("citebench.db")

# Compose service names. A host-run API that inherited DATABASE_URL=@db
# cannot resolve these; fall back to the published Postgres port.
_DOCKER_DB_HOSTS = frozenset({"db", "postgres", "postgresql", "database"})
_FALLBACK_DB_HOSTS = ("127.0.0.1", "localhost", "host.docker.internal")

SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source_url TEXT NOT NULL,
    version_or_snapshot TEXT NOT NULL,
    license TEXT NOT NULL,
    doc_type TEXT,
    product TEXT,
    source TEXT,
    version TEXT,
    sha256 TEXT,
    content_type TEXT,
    snapshot_path TEXT,
    page_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL CHECK (status IN ('ok', 'failed')),
    error TEXT,
    indexed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    page INTEGER,
    section TEXT,
    section_path TEXT,
    url TEXT,
    text TEXT NOT NULL,
    text_ref TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    embedding vector(768),
    tsv tsvector,
    UNIQUE (doc_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS chunks_doc_id_idx ON chunks (doc_id);
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS tsv tsvector;
CREATE INDEX IF NOT EXISTS chunks_tsv_gin ON chunks USING GIN (tsv);

CREATE TABLE IF NOT EXISTS ingest_runs (
    id SERIAL PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL,
    doc_count INTEGER NOT NULL DEFAULT 0,
    page_count INTEGER NOT NULL DEFAULT 0,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    error TEXT
);

ALTER TABLE documents ADD COLUMN IF NOT EXISTS origin TEXT NOT NULL DEFAULT 'freeze';
ALTER TABLE documents ADD COLUMN IF NOT EXISTS doc_type TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS product TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS source TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS version TEXT;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS section TEXT;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS section_path TEXT;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS url TEXT;
"""


def hostname_resolves(host: str) -> bool:
    if not host:
        return False
    try:
        socket.getaddrinfo(host, None)
    except OSError:
        return False
    return True


def rewrite_database_url_host(database_url: str, host: str) -> str:
    parsed = urlparse(database_url)
    userinfo = parsed.username or ""
    if parsed.password is not None:
        userinfo = f"{userinfo}:{parsed.password}"
    if userinfo:
        userinfo = f"{userinfo}@"
    port = f":{parsed.port}" if parsed.port is not None else ""
    return urlunparse(parsed._replace(netloc=f"{userinfo}{host}{port}"))


def resolve_database_url(database_url: str) -> str:
    """Keep a resolvable host; rewrite Compose names when DNS fails.

    `db` is valid inside the Compose network. The same URL on a host-run
    API (uvicorn leftover on :8000, or DATABASE_URL copied into .env)
    raises [Errno -2] Name or service not known. Prefer 127.0.0.1 so the
    published :5432 works. host.docker.internal covers an API container
    whose embedded DNS cannot see the `db` service.
    """
    host = urlparse(database_url).hostname
    if host and hostname_resolves(host):
        return database_url
    if host not in _DOCKER_DB_HOSTS:
        return database_url
    for candidate in _FALLBACK_DB_HOSTS:
        if hostname_resolves(candidate):
            return rewrite_database_url_host(database_url, candidate)
    return database_url


def is_database_error(exc: BaseException) -> bool:
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    if "operationalerror" in name:
        return True
    return any(
        marker in text
        for marker in (
            "name or service not known",
            "nodename nor servname",
            "connection refused",
            "could not translate host",
            "connection timed out",
            "timeout expired",
            "no route to host",
            "temporary failure in name resolution",
        )
    )


def database_unavailable_detail(exc: BaseException, database_url: str) -> str:
    host = urlparse(database_url).hostname or "?"
    text = str(exc).lower()
    dns_failure = any(
        marker in text
        for marker in (
            "name or service not known",
            "nodename nor servname",
            "could not translate host",
            "temporary failure in name resolution",
        )
    )
    if dns_failure:
        return (
            f"database unavailable: could not resolve host '{host}'. "
            "Compose sets DATABASE_URL host 'db' only for the api container. "
            "A host-run API (uvicorn or a leftover process on :8000) must use "
            f"127.0.0.1 (published :5432), not '{host}'. Original error: {exc}"
        )
    return f"database unavailable: host '{host}': {exc}"


@contextmanager
def connect(database_url: str) -> Iterator[psycopg.Connection]:
    resolved = resolve_database_url(database_url)
    if resolved != database_url:
        log.info(
            "DATABASE_URL host %s did not resolve; connecting via %s",
            urlparse(database_url).hostname,
            urlparse(resolved).hostname,
        )
    conn = psycopg.connect(
        resolved,
        row_factory=dict_row,
        autocommit=False,
        connect_timeout=5,
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def backfill_chunk_tsv(conn: psycopg.Connection) -> None:
    conn.execute(
        "UPDATE chunks SET tsv = to_tsvector('english', text) WHERE tsv IS NULL"
    )


def backfill_chunk_text_ref(conn: psycopg.Connection) -> None:
    conn.execute(
        """
        UPDATE chunks
        SET text_ref = doc_id || '#' || id
        WHERE text_ref LIKE '%#chunk-%'
        """
    )


def ensure_schema(conn: psycopg.Connection) -> None:
    conn.execute(SCHEMA_SQL)
    backfill_chunk_tsv(conn)
    backfill_chunk_text_ref(conn)
    conn.commit()


def wipe_index(conn: psycopg.Connection) -> None:
    conn.execute("DELETE FROM documents WHERE origin = 'freeze'")


def delete_unknown_documents(conn: psycopg.Connection, manifest_ids: Sequence[str]) -> None:
    conn.execute(
        "DELETE FROM documents WHERE origin = 'freeze' AND NOT (id = ANY(%s))",
        (list(manifest_ids),),
    )


def mark_document_failed(
    conn: psycopg.Connection,
    *,
    doc_id: str,
    title: str,
    source_url: str,
    version_or_snapshot: str,
    license: str,
    error: str | None,
    indexed_at: datetime | None,
    origin: str = "freeze",
    doc_type: str | None = None,
    product: str | None = None,
    source: str | None = None,
) -> None:
    """Record a failed snapshot without deleting last-good chunks."""
    updated = conn.execute(
        """
        UPDATE documents
        SET status = 'failed', error = %s, indexed_at = %s, updated_at = now()
        WHERE id = %s
        """,
        (error, indexed_at, doc_id),
    )
    if updated.rowcount:
        return
    conn.execute(
        """
        INSERT INTO documents (
            id, title, source_url, version_or_snapshot, license,
            doc_type, product, source, version,
            sha256, content_type, snapshot_path, page_count, status, error, indexed_at, origin
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            NULL, NULL, NULL, 0, 'failed', %s, %s, %s
        )
        """,
        (
            doc_id,
            title,
            source_url,
            version_or_snapshot,
            license,
            doc_type,
            product,
            source,
            version_or_snapshot,
            error,
            indexed_at,
            origin,
        ),
    )


def replace_document(
    conn: psycopg.Connection,
    *,
    doc_id: str,
    title: str,
    source_url: str,
    version_or_snapshot: str,
    license: str,
    sha256: str | None,
    content_type: str | None,
    snapshot_path: str | None,
    page_count: int,
    status: str,
    error: str | None,
    indexed_at: datetime | None,
    origin: str = "freeze",
    doc_type: str | None = None,
    product: str | None = None,
    source: str | None = None,
) -> None:
    conn.execute("DELETE FROM documents WHERE id = %s", (doc_id,))
    conn.execute(
        """
        INSERT INTO documents (
            id, title, source_url, version_or_snapshot, license,
            doc_type, product, source, version,
            sha256, content_type, snapshot_path, page_count, status, error, indexed_at, origin
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        """,
        (
            doc_id,
            title,
            source_url,
            version_or_snapshot,
            license,
            doc_type,
            product,
            source,
            version_or_snapshot,
            sha256,
            content_type,
            snapshot_path,
            page_count,
            status,
            error,
            indexed_at,
            origin,
        ),
    )


def insert_chunks(
    conn: psycopg.Connection,
    rows: Sequence[dict[str, Any]],
) -> None:
    if not rows:
        return
    with conn.cursor() as cur:
        for row in rows:
            embedding = row["embedding"]
            embedding_literal = "[" + ",".join(f"{float(x):.8f}" for x in embedding) + "]"
            cur.execute(
                """
                INSERT INTO chunks (
                    id, doc_id, chunk_index, page, section, section_path, url,
                    text, text_ref, token_count, embedding, tsv
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s::vector, to_tsvector('english', %s)
                )
                """,
                (
                    row["id"],
                    row["doc_id"],
                    row["chunk_index"],
                    row["page"],
                    row.get("section"),
                    row.get("section_path"),
                    row.get("url"),
                    row["text"],
                    row["text_ref"],
                    row["token_count"],
                    embedding_literal,
                    row["text"],
                ),
            )


def start_ingest_run(conn: psycopg.Connection) -> int:
    row = conn.execute(
        "INSERT INTO ingest_runs (status) VALUES ('running') RETURNING id"
    ).fetchone()
    assert row is not None
    conn.commit()
    return int(row["id"])


def finish_ingest_run(
    conn: psycopg.Connection,
    run_id: int,
    *,
    status: str,
    doc_count: int,
    page_count: int,
    chunk_count: int,
    failure_count: int,
    error: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE ingest_runs
        SET finished_at = now(),
            status = %s,
            doc_count = %s,
            page_count = %s,
            chunk_count = %s,
            failure_count = %s,
            error = %s
        WHERE id = %s
        """,
        (status, doc_count, page_count, chunk_count, failure_count, error, run_id),
    )


_DOC_SELECT = """
SELECT d.id, d.title, d.source_url, d.product, d.doc_type, d.source, d.origin,
       d.license, d.status, d.error, d.page_count, d.indexed_at,
       COALESCE(d.version, d.version_or_snapshot) AS version,
       (SELECT COUNT(*) FROM chunks c WHERE c.doc_id = d.id) AS chunk_count
FROM documents d
"""


def list_documents(
    conn: psycopg.Connection,
    *,
    query: str | None = None,
    product: str | None = None,
    source: str | None = None,
    origin: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Browse the indexed corpus: filter/search documents, newest product order."""
    where: list[str] = []
    params: list[Any] = []
    if query:
        where.append("(d.id ILIKE %s OR d.title ILIKE %s OR d.source_url ILIKE %s)")
        like = f"%{query}%"
        params.extend([like, like, like])
    for column, value in (
        ("d.product", product),
        ("d.source", source),
        ("d.origin", origin),
        ("d.status", status),
    ):
        if value:
            where.append(f"{column} = %s")
            params.append(value)
    clause = f" WHERE {' AND '.join(where)}" if where else ""

    total_row = conn.execute(
        f"SELECT COUNT(*) AS n FROM documents d{clause}", params
    ).fetchone()
    rows = conn.execute(
        f"{_DOC_SELECT}{clause} ORDER BY d.product NULLS LAST, d.title, d.id LIMIT %s OFFSET %s",
        [*params, limit, offset],
    ).fetchall()
    return {
        "total": int(total_row["n"]) if total_row else 0,
        "limit": limit,
        "offset": offset,
        "documents": [dict(row) for row in rows],
    }


def get_document(
    conn: psycopg.Connection,
    doc_id: str,
    *,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any] | None:
    """One document plus a page of its chunks (metadata + short preview, no full body)."""
    doc = conn.execute(f"{_DOC_SELECT} WHERE d.id = %s", (doc_id,)).fetchone()
    if doc is None:
        return None
    total_row = conn.execute(
        "SELECT COUNT(*) AS n FROM chunks WHERE doc_id = %s", (doc_id,)
    ).fetchone()
    chunks = conn.execute(
        """
        SELECT id, doc_id, chunk_index, section, page, url, token_count,
               left(text, 600) AS preview
        FROM chunks
        WHERE doc_id = %s
        ORDER BY chunk_index
        LIMIT %s OFFSET %s
        """,
        (doc_id, limit, offset),
    ).fetchall()
    for row in chunks:
        row["text_ref"] = f"{row['doc_id']}#{row['id']}"
    return {
        "document": dict(doc),
        "chunk_total": int(total_row["n"]) if total_row else 0,
        "limit": limit,
        "offset": offset,
        "chunks": [dict(row) for row in chunks],
    }


def get_chunks_by_ids(
    conn: psycopg.Connection,
    chunk_ids: Sequence[str],
) -> list[dict[str, Any]]:
    """Full chunk text for citation previews (bounded by the caller)."""
    if not chunk_ids:
        return []
    rows = conn.execute(
        """
        SELECT c.id, c.doc_id, c.chunk_index, c.section, c.page, c.url,
               c.token_count, c.text,
               d.title, d.product, d.source, d.license
        FROM chunks c
        JOIN documents d ON d.id = c.doc_id
        WHERE c.id = ANY(%s)
        """,
        (list(chunk_ids),),
    ).fetchall()
    by_id = {row["id"]: row for row in rows}
    ordered = []
    for chunk_id in chunk_ids:
        row = by_id.get(chunk_id)
        if row is None:
            continue
        item = dict(row)
        item["text_ref"] = f"{item['doc_id']}#{item['id']}"
        ordered.append(item)
    return ordered


def corpus_facets(conn: psycopg.Connection) -> dict[str, list[str]]:
    """Distinct filter values for the corpus browser."""

    def distinct(column: str) -> list[str]:
        rows = conn.execute(
            f"SELECT DISTINCT {column} AS v FROM documents "
            f"WHERE {column} IS NOT NULL AND {column} <> '' ORDER BY 1"
        ).fetchall()
        return [str(row["v"]) for row in rows]

    return {
        "products": distinct("product"),
        "sources": distinct("source"),
        "doc_types": distinct("doc_type"),
        "origins": distinct("origin"),
    }


_GENERIC_TOPICS = frozenset(
    {
        "kubernetes documentation",
        "concepts",
        "kubernetes",
        "fastapi",
        "about",
        "advanced user guide",
        "reference",
        "release notes",
        "blog",
        "community",
        "search",
        "documentation",
        "overview",
        "tutorials",
    }
)

_IMPERATIVE_VERBS = frozenset(
    {
        "configure",
        "create",
        "manage",
        "deploy",
        "use",
        "set",
        "update",
        "migrate",
        "install",
        "run",
        "expose",
        "debug",
        "test",
        "access",
        "extend",
        "generate",
        "include",
        "handle",
        "rotate",
        "scale",
        "monitor",
        "troubleshoot",
        "enable",
        "add",
        "build",
        "define",
        "restrict",
        "connect",
        "assign",
    }
)


def clean_topic(product: str | None, title: str | None) -> str:
    """Turn a crawled page title into a short askable topic."""
    text = (title or "").strip()
    for separator in (" / ", " | "):
        if separator in text:
            text = text.split(separator, 1)[0].strip()
    if product == "FastAPI" and text.endswith(" - FastAPI"):
        text = text[: -len(" - FastAPI")].strip()
    if product == "Azure" and " - " in text:
        text = text.split(" - ", 1)[0].strip()
    if product == "PostgreSQL":
        text = re.sub(r"^PostgreSQL:\s*Documentation:\s*\d+:\s*", "", text)
        text = re.sub(r"^\d+(?:\.\d+)*\.\s*", "", text)
    if text.lower().startswith("about "):
        text = text[6:].strip()
    if text.endswith((" Overview", " overview")):
        text = text[: -len(" Overview")].strip()
    if text.lower().endswith(" documentation"):
        text = text[: -len(" documentation")].strip()
    return text.strip(" -–—:")


def phrase_question(product: str | None, topic: str) -> str:
    """Product-aware question stem for a corpus topic."""
    stripped = topic.rstrip("?").strip()
    if not stripped:
        return ""
    if topic.rstrip().endswith("?"):
        return topic.strip()
    lowered = stripped.lower()
    if lowered.startswith(("what is ", "what are ", "how do ", "how does ", "how to ")):
        return f"{stripped}?"
    if product == "Kubernetes":
        first = stripped.split(" ", 1)[0].lower()
        if first in _IMPERATIVE_VERBS:
            return f"How do I {stripped[0].lower()}{stripped[1:]} in Kubernetes?"
        return f"What is {stripped} in Kubernetes?"
    if product == "Azure":
        return f"What is {stripped}?"
    if product == "PostgreSQL":
        return f"What does the PostgreSQL manual say about {stripped}?"
    if product == "FastAPI":
        return f"What does the FastAPI guide say about {stripped}?"
    if product == "xv6":
        return "What does the xv6 book cover?"
    return f"What is {stripped}?"


def corpus_suggestions(conn: psycopg.Connection, limit: int = 6) -> dict[str, Any]:
    """Question suggestions derived from the corpus's own document titles.

    Deterministic: samples a spread of topics per product (concepts first, then
    references) and adds one compare question. No hand-written prompts.
    """
    limit = max(1, min(limit, 12))
    rows = conn.execute(
        """
        SELECT id, title, product, doc_type
        FROM documents
        WHERE status = 'ok' AND origin = 'freeze' AND product IS NOT NULL
        ORDER BY product, id
        """
    ).fetchall()

    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        topic = clean_topic(row["product"], row["title"])
        if not (5 <= len(topic) <= 90):
            continue
        lowered = topic.lower()
        if lowered in _GENERIC_TOPICS or lowered.endswith("documentation"):
            continue
        if re.match(r"^(postgresql|xv6|kubernetes|fastapi)\s+\d", lowered):
            continue
        if re.match(r"^(part|chapter|appendix)\b", lowered):
            continue
        grouped.setdefault(str(row["product"]), []).append(
            {"doc_id": row["id"], "topic": topic, "doc_type": row["doc_type"] or ""}
        )
    for items in grouped.values():
        items.sort(key=lambda item: (item["doc_type"] == "reference", item["doc_id"]))

    products = sorted(grouped)
    suggestions: list[dict[str, str]] = []
    seen: set[str] = set()
    target = max(1, limit - 1)
    cursors = {product: 0 for product in products}
    strides = {product: max(1, len(grouped[product]) // 4) for product in products}

    while len(suggestions) < target:
        progressed = False
        for product in products:
            if len(suggestions) >= target:
                break
            items = grouped[product]
            index = cursors[product]
            if index >= len(items):
                continue
            cursors[product] = index + strides[product]
            item = items[index]
            question = phrase_question(product, item["topic"])
            if not question or question in seen:
                continue
            seen.add(question)
            progressed = True
            suggestions.append(
                {"question": question, "product": product, "doc_id": item["doc_id"]}
            )
        if not progressed:
            break

    if limit >= 2:
        short = {
            product: [
                item["topic"] for item in grouped[product] if 8 <= len(item["topic"]) <= 45
            ]
            for product in products
        }
        candidates = [
            (product, topics) for product, topics in short.items() if len(topics) >= 2
        ]
        if candidates:
            # Prefer the core products, then the product with the most short topics.
            candidates.sort(
                key=lambda pair: (pair[0] not in ("Kubernetes", "FastAPI"), -len(pair[1]))
            )
            product, topics = candidates[0]
            question = f"Compare {topics[0]} and {topics[1]} in {product}."
            if question not in seen:
                suggestions.append(
                    {"question": question, "product": product, "doc_id": ""}
                )

    return {"suggestions": suggestions[:limit], "source": "corpus"}


def corpus_macro(conn: psycopg.Connection, per_product: int = 6) -> dict[str, Any]:
    """A compact summary of what the corpus covers, for LLM question generation."""
    rows = conn.execute(
        """
        SELECT product, title
        FROM documents
        WHERE status = 'ok' AND origin = 'freeze' AND product IS NOT NULL
        ORDER BY product, id
        """
    ).fetchall()
    grouped: dict[str, list[str]] = {}
    for row in rows:
        topic = clean_topic(row["product"], row["title"])
        lowered = topic.lower()
        if not (5 <= len(topic) <= 80) or lowered in _GENERIC_TOPICS:
            continue
        if lowered.endswith("documentation") or re.match(r"^\w+\s+\d", lowered):
            continue
        bucket = grouped.setdefault(str(row["product"]), [])
        if len(bucket) < per_product and topic not in bucket:
            bucket.append(topic)
    stats = corpus_stats(conn)
    return {
        "docs": stats["doc_count"],
        "chunks": stats["chunk_count"],
        "products": grouped,
    }


def corpus_stats(conn: psycopg.Connection) -> dict[str, Any]:
    docs_ok = conn.execute(
        "SELECT COUNT(*) AS n FROM documents WHERE status = 'ok'"
    ).fetchone()
    pages = conn.execute(
        "SELECT COALESCE(SUM(page_count), 0) AS n FROM documents WHERE status = 'ok'"
    ).fetchone()
    chunks = conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()
    user_docs = conn.execute(
        "SELECT COUNT(*) AS n FROM documents WHERE status = 'ok' AND origin = 'user'"
    ).fetchone()
    last = conn.execute(
        """
        SELECT finished_at
        FROM ingest_runs
        WHERE finished_at IS NOT NULL
        ORDER BY finished_at DESC
        LIMIT 1
        """
    ).fetchone()
    failures = conn.execute(
        """
        SELECT id, title, source_url, error, indexed_at
        FROM documents
        WHERE status = 'failed'
        ORDER BY id
        """
    ).fetchall()
    last_index_time = last["finished_at"] if last else None
    return {
        "doc_count": int(docs_ok["n"]) if docs_ok else 0,
        "page_count": int(pages["n"]) if pages else 0,
        "chunk_count": int(chunks["n"]) if chunks else 0,
        "user_doc_count": int(user_docs["n"]) if user_docs else 0,
        "last_index_time": last_index_time.isoformat() if last_index_time else None,
        "failures": [
            {
                "id": row["id"],
                "title": row["title"],
                "source_url": row["source_url"],
                "error": row["error"] or "unknown ingest failure",
                "indexed_at": row["indexed_at"].isoformat() if row["indexed_at"] else None,
            }
            for row in failures
        ],
    }
