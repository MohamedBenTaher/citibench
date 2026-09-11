CREATE EXTENSION IF NOT EXISTS vector;

-- C2 ingest + C3 retrieve schema. chunks.embedding is dense; chunks.tsv is FTS.

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
UPDATE chunks SET tsv = to_tsvector('english', text) WHERE tsv IS NULL;

ALTER TABLE documents ADD COLUMN IF NOT EXISTS origin TEXT NOT NULL DEFAULT 'freeze';
ALTER TABLE documents ADD COLUMN IF NOT EXISTS doc_type TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS product TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS source TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS version TEXT;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS section TEXT;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS section_path TEXT;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS url TEXT;

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
