# Plan 012: Carry chunk metadata (source/doc_type/product/version/section/page/url/license) into Postgres and traces

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**:
> `git diff --stat 028fa3e..HEAD -- apps/api/db.py apps/api/manifest.py apps/api/parse_doc.py apps/api/chunking.py apps/api/pipeline.py apps/api/retrieve.py apps/api/trace.py apps/api/main.py apps/api/tests infra/postgres/init.sql docs/contracts/hybrid-retrieval.md docs/contracts/trace-schema.md`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: L
- **Risk**: HIGH (schema + parser + retrieval + trace contract in one slice)
- **Depends on**: plans 010 (manifest columns) and 011 (PDFs)
- **Category**: direction (I1 / C6)
- **Planned at**: commit `028fa3e`, 2026-09-10

## Why this matters

A citation bench must be able to say *which product, version, page, and section*
a claim came from, and it must let a reviewer filter retrieval to one source.
Today chunks carry only `page` (an integer) and the citation pointer
`doc_id#chunk_id`; `product`/`doc_type`/`section`/`license` exist nowhere on
chunks or traces. This plan threads the metadata end to end: manifest → parse →
chunk → Postgres → retrieve hit → `RunTrace` span pointer → contracts. It is the
prerequisite for metadata filters (plan 017).

No chunk **text** is added to traces — Contract B's pointer-only rule stays.

## Current state

**DB** (`apps/api/db.py:23-73`, `SCHEMA_SQL`, idempotent; no migration tool):
```sql
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY, title TEXT NOT NULL, source_url TEXT NOT NULL,
    version_or_snapshot TEXT NOT NULL, license TEXT NOT NULL, sha256 TEXT,
    content_type TEXT, snapshot_path TEXT, page_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL CHECK (status IN ('ok','failed')), error TEXT,
    indexed_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY, doc_id TEXT NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL, page INTEGER, text TEXT NOT NULL, text_ref TEXT NOT NULL,
    token_count INTEGER NOT NULL, embedding vector(768), tsv tsvector,
    UNIQUE (doc_id, chunk_index)
);
```
`origin` was added late via `ALTER TABLE documents ADD COLUMN IF NOT EXISTS origin TEXT NOT NULL DEFAULT 'freeze'` (`db.py:72`). Inserts:
- `replace_document(conn, doc_id, title, source_url, version_or_snapshot, license, sha256, content_type, snapshot_path, page_count, status, error, indexed_at, origin="freeze")` (`db.py:263-305`).
- `insert_chunks(conn, rows)` writes `id, doc_id, chunk_index, page, text, text_ref, token_count, embedding, tsv` (`db.py:308-337`).
- `mark_document_failed(...)` (`db.py:218-260`).
- `infra/postgres/init.sql` duplicates the tables for first boot and is already **missing `origin`** — update it in lockstep.

**Manifest** (`apps/api/manifest.py:13-19, 34, 61-69`):
```python
@dataclass(frozen=True)
class ManifestDoc:
    id: str; title: str; source_url: str; version_or_snapshot: str; license: str
...
required = ["id", "title", "source_url", "version_or_snapshot", "license"]
...
row = dict(zip(headers, cells, strict=False))
docs.append(ManifestDoc(id=..., title=..., source_url=..., version_or_snapshot=..., license=...))
```
Plan 010 writes extra columns (`doc_type`, `product`, `source`, `pages`) which are parsed into `row` and currently dropped.

**Parse** (`apps/api/parse_doc.py:56-74`): `_parse_html` selects a root and does
`root.get_text("\n", strip=True)`. **Headings are flattened** — no `#` markers.
PDF already emits `[page N]` (`parse_doc.py:44-53`).

**Chunking** (`apps/api/chunking.py`):
```python
@dataclass(frozen=True)
class TextChunk:
    index: int; text: str; token_count: int; start_token: int
```
`chunk_text` (`:33-69`) is the flat path used by freeze ingest
(`pipeline.py:166`). `chunk_text_dynamic` (`:72-115`) splits on `_sections`
(`:118-131`): boundary when `stripped.startswith("#") or stripped.startswith("[page ")`.
It is used only by **user** ingest (`user_ingest.py:194`).

**Retrieve** (`apps/api/retrieve.py`): `ChunkHit` (`:35-45`) has `chunk_id,
doc_id, score, rank, rerank_skipped, text, vector_score, fts_score, fused_score,
rerank_score`. Pools are private. SQL:
```sql
SELECT id, doc_id, text, 1 - (embedding <=> %s::vector) AS vector_score
FROM chunks WHERE embedding IS NOT NULL ORDER BY embedding <=> %s::vector, id LIMIT %s
```
(`:378-388`); FTS is the analogous `tsv @@ plainto_tsquery(...)` (`:403-414`).
Chunk pointers for traces: `_chunk_pointers` (`retrieve.py:266-276`) builds
`{"chunk_id","doc_id","text_ref": f"{doc_id}#{chunk_id}","rank","score"}`.

**Trace** (`apps/api/trace.py`): `ChunkRef` (`:44-61`) is pointer-only —
`chunk_id, doc_id, text_ref` plus a `text_ref` regex validator. `refs_from_hits`
(`:157-168`) and `chunk_ref_for_hit` (`:141-154`). Contract B
(`docs/contracts/trace-schema.md:25-36`) enforces "no corpus dumps".

**Contracts**: `docs/contracts/hybrid-retrieval.md:53-60` lists `ChunkHit`;
`docs/contracts/trace-schema.md:25-36` lists `ChunkRef`. Both must change.

**Conventions**: SQL is parameterized `%s`; DDL is `CREATE/ALTER ... IF NOT
EXISTS` run by `ensure_schema` (`db.py:200-204`). Pydantic models live next to
their use. Tests are pure unit tests with monkeypatched DB connections.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| API tests | `.venv/bin/python -m pytest apps/api` | all pass |
| Targeted | `.venv/bin/python -m pytest apps/api/tests/test_db.py apps/api/tests/test_parse_doc.py apps/api/tests/test_chunking.py apps/api/tests/test_retrieve.py apps/api/tests/test_trace.py` | all pass |
| Web types | `cd apps/web && npm run typecheck` | exit 0 |

## Scope

**In scope**:

- `apps/api/db.py` — schema + insert signatures + stats joins.
- `infra/postgres/init.sql` — mirror the schema (add `origin` too, which is missing).
- `apps/api/manifest.py` — optional `doc_type`, `product`, `source`.
- `apps/api/parse_doc.py` — emit `#` heading markers for HTML.
- `apps/api/chunking.py` — `TextChunk.section`; section-aware freeze chunking.
- `apps/api/pipeline.py` — use `chunk_text_dynamic`, attach section/url/metadata.
- `apps/api/retrieve.py` — join documents, return metadata on `ChunkHit`, richer pointers.
- `apps/api/trace.py` — optional metadata on `ChunkRef`.
- `apps/api/main.py` — `RetrieveResponse` unchanged shape except richer hits.
- `docs/contracts/hybrid-retrieval.md`, `docs/contracts/trace-schema.md`.
- Tests listed in "Test plan".
- `docs/decision-trail.tsv`, `plans/README.md` status row.

**Out of scope**:

- User-ingest metadata parity beyond compilation (plan 020 owns user namespaces);
  if `user_ingest.py` must change to compile, make the minimal change and say so.
- Metadata **filters** (WHERE clauses / API knobs) — plan 017.
- Web UI rendering of the new fields (except keeping `npm run typecheck` green).
- ANN index, quantization, hierarchical layers (plan 008.2/008.3).
- Reprocessing `corpus/v0` snapshots differently.

## Git workflow

- Branch: `advisor/012-chunk-metadata`
- Commit in this order: (1) schema, (2) manifest+parse+chunk, (3) retrieve+trace, (4) contracts+tests.
- Message style: `Thread corpus metadata through ingest, retrieve, and traces.`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Schema

In `apps/api/db.py` `SCHEMA_SQL`, extend `documents` with
`doc_type TEXT`, `product TEXT`, `source TEXT`, and `version TEXT` (keep
`version_or_snapshot` for compatibility), and add idempotent ALTERs for existing
DBs right after the origin ALTER (`db.py:72`):
```sql
ALTER TABLE documents ADD COLUMN IF NOT EXISTS doc_type TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS product TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS source TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS version TEXT;
```
Extend `chunks` with `section TEXT`, `section_path TEXT`, `url TEXT` (and matching
`ALTER TABLE chunks ADD COLUMN IF NOT EXISTS …`).
Mirror all of this (including the missing `origin`) in `infra/postgres/init.sql`.

**Verify**: `rg -n "doc_type|section_path|ADD COLUMN IF NOT EXISTS origin" apps/api/db.py infra/postgres/init.sql` → both files show the new columns.

### Step 2: Manifest optional fields

In `apps/api/manifest.py`:
```python
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
```
Populate from `row.get("doc_type")`, `row.get("product")`, `row.get("source")`
(normalize `""` → `None`). `required` stays the same so `corpus/v0/MANIFEST.md`
(old schema) still parses.

**Verify**: `.venv/bin/python -m pytest apps/api/tests/test_manifest.py` → pass
(v0 parses with `None` metadata; big freeze parses with values).

### Step 3: HTML heading markers

Rewrite `_parse_html` (`parse_doc.py:56-74`) so headings survive as section
boundaries. Build the text by walking the chosen root in document order and
emitting `f"{'#' * level} {heading_text}"` for `h1`–`h4`, and each other text
block via `get_text`. Collapse blank lines (`_collapse_blank_lines`,
`parse_doc.py:77`) as today. `page_count` stays `1`.
Keep the existing drop-tag list and root selection.

**Verify**: add a unit test with an HTML fixture `<h1>A</h1><p>…</p><h2>B</h2><p>…</p>`
asserting the text contains `# A` and `## B`; run
`.venv/bin/python -m pytest apps/api/tests/test_parse_doc.py` → pass.

### Step 4: Section-aware chunking

In `apps/api/chunking.py`:
- Add `section: str | None = None` to `TextChunk`.
- Change `chunk_text_dynamic` so each produced chunk records the nearest heading
  path (e.g. `A > B`) as `section`. Implement by having `_sections` return
  `(heading_path, body)` and threading it through; flat `chunk_text` returns
  `section=None` (unchanged order/indices).
- Do not change `chunk_text`'s token math (`chunking.py:33-69`) or the default
  512/64.

**Verify**: `.venv/bin/python -m pytest apps/api/tests/test_chunking.py` → pass;
add a test that a `# A\n…\n## B\n…` input yields chunks whose `section` is
`"A"` then `"A > B"`.

### Step 5: Ingest writes metadata

In `apps/api/pipeline.py`:
- Swap `chunk_text(...)` (`:166`) for `chunk_text_dynamic(...)`.
- In the row builder (`:180-194`) add `section=chunk.section`,
  `section_path=chunk.section`, `url=doc.source_url` (page-level URL; anchors are
  a later enhancement).
- Pass `doc_type=doc.doc_type`, `product=doc.product`, `source=doc.source`,
  `version=doc.version_or_snapshot` to `replace_document`.
- Update `_record_failure` to pass the same optional fields.
Update `apps/api/db.py` `replace_document`, `mark_document_failed`, and
`insert_chunks` to accept/write the new columns (parameterized `%s`).

**Verify**: `.venv/bin/python -m pytest apps/api/tests/test_pipeline.py apps/api/tests/test_db.py` → pass. Add a `test_db.py` case asserting the new column
names appear in the `INSERT` SQL the function executes (capture via a fake
connection), following the existing test-double pattern in `test_db.py`.

### Step 6: Retrieve returns metadata

- Extend `ChunkHit` (`retrieve.py:35-45`) with optional fields: `title`,
  `source`, `product`, `doc_type`, `version`, `license`, `page`, `section`,
  `url` (all `str | None` except `page: int | None`).
- Change `search_vector`/`search_fts` SQL (`:378-388`, `:403-414`) to
  `JOIN documents d ON d.id = c.doc_id` and select
  `d.title, d.source, d.product, d.doc_type, d.version, d.license, c.page, c.section, c.url`.
  Keep pools private and ordering unchanged.
- Carry the fields through `ScoredChunk`/`FusedChunk` into `_to_hit`.
- `_chunk_pointers` (`:266-276`) includes `page`, `section`, `url` (no text).

**Verify**: `.venv/bin/python -m pytest apps/api/tests/test_retrieve.py` → pass;
extend the retrieve test double to return the new columns and assert one hit
carries `product`/`section`.

### Step 7: Trace refs carry metadata (pointer-only)

In `apps/api/trace.py`:
- Add optional `page: int | None`, `section: str | None`, `url: str | None`,
  `product: str | None`, `doc_type: str | None`, `license: str | None` to
  `ChunkRef` (`:44-61`). Keep the `text_ref` validator and the no-body rule.
- `refs_from_hits`/`chunk_ref_for_hit` (`:141-168`) populate them from the hit.
- `generate.py:200` builds `ChunkRef`s; update it to pass the new fields if it
  constructs refs manually (verify; `refs_for_ids` uses `chunk_ref_for_hit`).
- `validate_run_trace` (`trace.py:171-211`) must still reject any `text`/body key
  (`_BODY_KEYS`, `:24`). Confirm the new fields are not body keys.

**Verify**: `.venv/bin/python -m pytest apps/api/tests/test_trace.py apps/api/tests/test_generate.py` → pass.

### Step 8: Contracts + web types

- `docs/contracts/hybrid-retrieval.md`: add the new `ChunkHit` display fields and
  state pools remain private.
- `docs/contracts/trace-schema.md`: document the optional `ChunkRef` metadata and
  restate that `text_ref` stays pointer-only, no chunk text.
- If `apps/web/src/lib/types.ts` mirrors `ChunkHit`/`ChunkRef` and `npm run
  typecheck` breaks, add the optional fields there (types only, no UI change).

**Verify**: `cd apps/web && npm run typecheck` → exit 0.

## Test plan

- `test_parse_doc.py`: HTML heading markers; existing PDF multi-page still passes.
- `test_chunking.py`: section path propagation; flat path unchanged.
- `test_db.py`: insert SQL includes `section/url/doc_type/product/source/version`
  (fake connection pattern already in this file).
- `test_retrieve.py`: joined metadata arrives on `ChunkHit`; `rerank_skipped`
  semantics unchanged.
- `test_trace.py`: `ChunkRef` metadata round-trips; a body key still raises.
- `test_manifest.py`: optional columns parse; v0 (old schema) still parses.
- No live DB required (AGENTS.md).
- Verification: `.venv/bin/python -m pytest apps/api` → all pass; web typecheck → 0.

## Done criteria

- [ ] `documents` has `doc_type/product/source/version`; `chunks` has
      `section/section_path/url`; both in `db.py` **and** `init.sql`.
- [ ] `ManifestDoc` carries the optional columns; v0 manifest still parses.
- [ ] `_parse_html` emits `#` heading lines; freeze ingest uses
      `chunk_text_dynamic`; chunks carry `section` + `url`.
- [ ] Retrieval hits and `RunTrace` chunk pointers carry the metadata; no chunk
      text appears in traces.
- [ ] Contracts updated; `docs/contracts/stubs/schemas.py` unchanged unless a
      trace/eval stub field is genuinely required.
- [ ] `.venv/bin/python -m pytest apps/api` exits 0; `cd apps/web && npm run typecheck` exits 0.
- [ ] No files outside the in-scope list modified (`git status`).
- [ ] `plans/README.md` row 012 is DONE.

## STOP conditions

- A migration cannot be idempotent (partial DDL on an existing DB) — stop;
  Citebench has no migration tool, so every statement must be `IF NOT EXISTS`.
- Section extraction requires rewriting `ParsedDocument` (structured return) —
  stop and report; the `#`-marker approach is the intended design.
- The joined SQL changes retrieval ordering or breaks `rerank_skipped` — stop.
- Adding metadata forces chunk text into `RunTrace` to satisfy a test — stop;
  that violates Contract B.
- `apps/web` typecheck requires touching Playground behavior — stop; plan 017
  owns UI.

## Maintenance notes

- Plan 013 re-ingests so the new columns are populated; until then they are NULL
  on already-indexed rows.
- Plan 017 builds metadata filters on `documents.*` + `chunks.section`; keep the
  join shape stable.
- Plan 020 must give user-ingest the same columns or explicitly document why
  user chunks are metadata-poor.
- Reviewers: confirm `validate_run_trace` still rejects bodies and that retrieve
  latency was not materially changed by the JOIN (plan 018 measures it).
