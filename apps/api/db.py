"""Postgres helpers: schema ensure, freeze-safe upserts, corpus stats."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row

SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source_url TEXT NOT NULL,
    version_or_snapshot TEXT NOT NULL,
    license TEXT NOT NULL,
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
    text TEXT NOT NULL,
    text_ref TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    embedding vector(768),
    tsv tsvector,
    UNIQUE (doc_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS chunks_doc_id_idx ON chunks (doc_id);
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
"""


@contextmanager
def connect(database_url: str) -> Iterator[psycopg.Connection]:
    conn = psycopg.connect(
        database_url,
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


def ensure_schema(conn: psycopg.Connection) -> None:
    conn.execute(SCHEMA_SQL)
    conn.commit()


def wipe_index(conn: psycopg.Connection) -> None:
    conn.execute("TRUNCATE chunks, documents RESTART IDENTITY CASCADE")


def delete_unknown_documents(conn: psycopg.Connection, manifest_ids: Sequence[str]) -> None:
    conn.execute("DELETE FROM documents WHERE NOT (id = ANY(%s))", (list(manifest_ids),))


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
) -> None:
    conn.execute("DELETE FROM documents WHERE id = %s", (doc_id,))
    conn.execute(
        """
        INSERT INTO documents (
            id, title, source_url, version_or_snapshot, license,
            sha256, content_type, snapshot_path, page_count, status, error, indexed_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        """,
        (
            doc_id,
            title,
            source_url,
            version_or_snapshot,
            license,
            sha256,
            content_type,
            snapshot_path,
            page_count,
            status,
            error,
            indexed_at,
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
                    id, doc_id, chunk_index, page, text, text_ref, token_count, embedding, tsv
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s::vector, to_tsvector('english', %s)
                )
                """,
                (
                    row["id"],
                    row["doc_id"],
                    row["chunk_index"],
                    row["page"],
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


def corpus_stats(conn: psycopg.Connection) -> dict[str, Any]:
    docs_ok = conn.execute(
        "SELECT COUNT(*) AS n FROM documents WHERE status = 'ok'"
    ).fetchone()
    pages = conn.execute(
        "SELECT COALESCE(SUM(page_count), 0) AS n FROM documents WHERE status = 'ok'"
    ).fetchone()
    chunks = conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()
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
