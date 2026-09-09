# Plan 002: One DB connection per retrieve; no schema DDL on the hot path

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 85d12a0..HEAD -- apps/api/retrieve.py apps/api/db.py apps/api/main.py apps/api/metrics.py apps/api/pipeline.py apps/api/tests/test_retrieve.py apps/api/tests/test_db.py infra/postgres/init.sql`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: MED
- **Depends on**: none
- **Category**: perf
- **Planned at**: commit `85d12a0`, 2026-09-07

## Why this matters

Default `retrieve()` opens **two** Postgres connections per query: one for pgvector, one for FTS. Each calls `ensure_schema()`, which executes the full `SCHEMA_SQL` string — including `CREATE EXTENSION`, `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, and `UPDATE chunks SET tsv = to_tsvector(...) WHERE tsv IS NULL`.

That work belongs at startup and ingest, not on every Playground ask. Two TCP handshakes plus catalog/DDL-if-not-exists plus a tsv backfill scan sit on the retrieve latency budget **before** FlashRank and Groq. Corpus is small (~148 chunks), so the SQL scans are cheap; the extra connection + `ensure_schema` is still the wrong shape and will hurt if the freeze grows.

`GET /corpus/stats` and `GET /metrics` also call `ensure_schema` on every scrape. Lifespan already ensures schema once.

## Current state

- `apps/api/retrieve.py` — `_default_vector` / `_default_fts` each `with connect(...) as conn: ensure_schema(conn); search_*`.
- `apps/api/db.py` — `SCHEMA_SQL` (lines 23–72) includes the tsv `UPDATE`; `ensure_schema` is `conn.execute(SCHEMA_SQL); conn.commit()`.
- `apps/api/main.py` — lifespan `ensure_schema`; `get_corpus_stats` calls it again.
- `apps/api/metrics.py` — `ensure_schema` when collecting corpus counts.
- `apps/api/pipeline.py` — ingest correctly calls `ensure_schema` once at the start of `run_ingest`.
- `infra/postgres/init.sql` — same DDL as `SCHEMA_SQL` for Compose first boot.
- Tests: `apps/api/tests/test_retrieve.py` injects `vector_search_fn` / `fts_search_fn` and does **not** hit `_default_vector`. `apps/api/tests/test_db.py` covers URL rewrite only.

Excerpt from `apps/api/retrieve.py`:

```python
def _default_vector(settings: Settings | None) -> VectorSearchFn:
    resolved = _require_settings(settings)
    def _search(query_vec: Sequence[float], k: int) -> list[ScoredChunk]:
        with connect(resolved.database_url) as conn:
            ensure_schema(conn)
            return search_vector(conn, query_vec, k)
    return _search
```

`_default_fts` is the same pattern with `search_fts`.

**Conventions**: parameterized SQL via psycopg (`%s`), never string-interpolated queries. `connect()` commits on success and closes in `finally`. Match existing `search_vector` / `search_fts` SQL; do not change scoring formulas.

**Product constraint**: hybrid retrieve stays private pools + RRF + FlashRank (`DECISIONS.md` C3). Do not add a vector SaaS.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Retrieve + db tests | `.venv/bin/python -m pytest apps/api/tests/test_retrieve.py apps/api/tests/test_db.py -q` | all pass |
| Full API suite | `.venv/bin/python -m pytest apps/api -q` | all pass |

## Scope

**In scope**:

- `apps/api/retrieve.py`
- `apps/api/db.py`
- `apps/api/main.py` (`get_corpus_stats` only — keep lifespan `ensure_schema`)
- `apps/api/metrics.py` (drop per-scrape `ensure_schema` if present)
- `apps/api/tests/test_retrieve.py` (new tests using fakes; no live Postgres required)
- `apps/api/tests/test_db.py` (optional: split DDL vs backfill helper if you extract one)
- `plans/README.md` status row

**Out of scope**:

- `infra/postgres/init.sql` unless you **copy** a comment that schema is applied at init + lifespan, not on retrieve. Prefer not to duplicate more SQL.
- Connection pool (`psycopg_pool`) — deferred; one connection per retrieve is enough.
- Changing `search_vector` / `search_fts` ranking SQL.
- `insert_chunks` row-by-row ingest.
- pgvector HNSW indexes.

## Git workflow

- Branch: `advisor/002-retrieve-single-connection`
- Commit message: `Use one Postgres connection for hybrid retrieve and stop running schema DDL on every ask.`
- Do NOT push unless asked.

## Steps

### Step 1: Split schema ensure vs tsv backfill (optional but preferred)

In `apps/api/db.py`, split `SCHEMA_SQL` so the `UPDATE chunks SET tsv = ...` is **not** part of the string run on every `ensure_schema`.

- Keep DDL (`CREATE EXTENSION/TABLE/INDEX`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`) in `SCHEMA_SQL`.
- Move the `UPDATE ... WHERE tsv IS NULL` into `backfill_chunk_tsv(conn)` and call it from `ensure_schema` **once** (ingest + lifespan still need backfill for old rows).

`ensure_schema` may still run DDL IF NOT EXISTS at startup — that is acceptable. The win on the hot path is **not calling `ensure_schema` at all** from retrieve/stats/metrics.

If you skip the split, you must still remove `ensure_schema` from retrieve/stats/metrics (step 2–3). The split prevents a future caller from reintroducing the UPDATE on a hot path.

**Verify**: `rg -n "ensure_schema" apps/api` after later steps shows: `db.py` definition, `main.py` lifespan, `pipeline.py` ingest — not retrieve/metrics/stats.

### Step 2: Retrieve uses one connection when using default search fns

In `apps/api/retrieve.py` `retrieve()`:

After computing `query_vec` (embed), if **both** `vector_search_fn` and `fts_search_fn` are `None`, open a single `connect(_require_settings(settings).database_url)` and call `search_vector` then `search_fts` on that connection. Do **not** call `ensure_schema`.

If either search fn is injected (tests), keep today’s behavior: call the injected fns, and do **not** open a connection in `retrieve()` for search.

Refactor `_default_vector` / `_default_fts` so they are unused on the production path, **or** delete them if nothing else imports them. Grep first:

```bash
rg -n "_default_vector|_default_fts" apps/api
```

If tests never call them, remove them to avoid a second connection sneaking back.

Keep `embed_query_fn` independent (still one embed call). Keep `rerank_fn` as today.

On embed/search exceptions, keep the existing `stage_sink` error spans and re-raise.

**Verify**: `.venv/bin/python -m pytest apps/api/tests/test_retrieve.py -q` — injected-fn tests still pass (they never needed Postgres).

### Step 3: Stop `ensure_schema` on read endpoints

- `apps/api/main.py` `get_corpus_stats`: `connect` + `corpus_stats(conn)` only. Lifespan already created tables. If the DB is empty/uninitialized, `corpus_stats` will raise and the existing 503 handler remains.
- `apps/api/metrics.py`: remove `ensure_schema` next to corpus stats (read the file; it imports `ensure_schema` around the corpus lookup).

Leave `pipeline.run_ingest` and lifespan as the writers of schema.

**Verify**: `rg -n "ensure_schema" apps/api/main.py apps/api/metrics.py apps/api/retrieve.py` — no matches except lifespan in `main.py`.

### Step 4: Characterization tests (no live DB)

In `apps/api/tests/test_retrieve.py`, add tests that the production path would share one connection. Because opening real Postgres is not guaranteed in CI, do this with a fake:

Option A (preferred): extract a small helper in `retrieve.py`, e.g. `hybrid_search(conn, query_vec, query_text, cfg) -> tuple[list[ScoredChunk], list[ScoredChunk]]` that calls `search_vector` then `search_fts`. Unit-test it with a fake `conn` whose `execute` records calls — **only if** you can do that without rewriting `search_vector` SQL.

Option B: monkeypatch `retrieve.connect` to a dummy context manager that counts `__enter__` and returns an object whose `execute` raises a unique error. Call `retrieve("pods", settings=make_settings(), embed_query_fn=stub_embed)` **without** injected vector/fts fns. Assert `connect` was entered **once**. `search_vector` will then fail on the dummy — wrap in `pytest.raises` and still assert enter count == 1.

Use Option B if Option A requires a large refactor. Copy `make_settings` from `apps/api/tests/test_generate.py` or a local Settings builder. `RetrieveConfig` defaults are fine.

Also assert `ensure_schema` is **not** called: monkeypatch `retrieve.ensure_schema` to raise `AssertionError` if you still import it; after step 2 it should not be imported in `retrieve.py`.

**Verify**: new test fails before the connect-sharing change and passes after.

### Step 5: Full suite

```bash
.venv/bin/python -m pytest apps/api -q
```

Expected: all pass.

## Test plan

- Injected vector/fts fns: existing `test_retrieve.py` 5-doc fixture tests unchanged.
- New: default search path opens `connect` once (Option B).
- New: `retrieve.py` does not call `ensure_schema` (import-level grep in done criteria plus monkeypatch).
- Pattern: `apps/api/tests/test_retrieve.py` stubs (`stub_embed`, `stub_vector`).

## Done criteria

- [ ] Default `retrieve()` uses one `connect()` for dense + FTS
- [ ] `ensure_schema` is not called from `retrieve.py`, `get_corpus_stats`, or metrics corpus scrape
- [ ] Lifespan + ingest still call `ensure_schema`
- [ ] RRF / FlashRank / `ChunkHit` fields unchanged
- [ ] `.venv/bin/python -m pytest apps/api` exits 0
- [ ] No out-of-scope files modified
- [ ] `plans/README.md` row 002 is DONE

## STOP conditions

- Tests that require a live Postgres appear in CI (GitHub Actions `eval-ci.yml` has **no** Postgres service). Do not add tests that fail without Docker db.
- You need to change vector `<=>` or `ts_rank_cd` formulas to share a connection — stop; sharing a connection must be a wiring change only.
- `connect()` autocommit / transaction behavior would force holding a transaction across FlashRank CPU (do not). Search both lists, close connection, **then** rerank. Do not run FlashRank inside the `with connect` block.

## Maintenance notes

- Reviewers: confirm FlashRank still runs **after** the connection is closed so ONNX does not sit on a Postgres session.
- If a future worker starts without lifespan (bare script calling `retrieve`), it must call `ensure_schema` itself or tables will be missing — document that in a one-line comment on `retrieve()` production path.
- Follow-up (not this plan): `psycopg_pool.ConnectionPool` if concurrent asks become real.
