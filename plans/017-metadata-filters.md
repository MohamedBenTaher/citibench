# Plan 017: Optional metadata filters in the API and light Playground controls

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**:
> `git diff --stat 028fa3e..HEAD -- apps/api/retrieve.py apps/api/main.py apps/api/generate.py apps/api/tests/test_retrieve.py apps/web/src/routes/playground.tsx apps/web/src/lib/types.ts apps/web/src/lib/server.ts docs/contracts/hybrid-retrieval.md`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED (SQL predicate injection if built wrong; big pool reductions)
- **Depends on**: plans 012 (metadata columns), 013 (populated corpus)
- **Category**: direction (I2 / R1)
- **Planned at**: commit `028fa3e`, 2026-09-10

## Why this matters

After C6 the corpus carries `product`, `doc_type`, `source`, `version`,
`section`, and `license`, but retrieval ignores all of it. A reviewer cannot ask
"only across Azure docs" or "only FastAPI guides". This plan adds optional,
parameterized filters to retrieve/generate and two light controls in Playground.
The hybrid pipeline (RRF → FlashRank) is unchanged; filters only narrow the
candidate pools.

## Current state

- `retrieve()` signature (`apps/api/retrieve.py:136-146`) takes `query, config,
  *, embed_query_fn, vector_search_fn, fts_search_fn, rerank_fn, settings, stage_sink`.
- `RetrieveConfig` (`retrieve.py:23-32`): `chunk_size, chunk_overlap, embed_model,
  rerank_model, rrf_k, rerank_pool, top_k, lexical_k, dense_k`. No filters.
- Injected function protocols (`retrieve.py:64-77`):
  ```python
  class VectorSearchFn(Protocol):
      def __call__(self, query_vec: list[float], k: int) -> Sequence[ScoredChunk]: ...
  class FtsSearchFn(Protocol):
      def __call__(self, query: str, k: int) -> Sequence[ScoredChunk]: ...
  ```
- SQL (`retrieve.py:374-423`) has no metadata predicate:
  ```sql
  SELECT id, doc_id, text, 1 - (embedding <=> %s::vector) AS vector_score
  FROM chunks WHERE embedding IS NOT NULL ORDER BY embedding <=> %s::vector, id LIMIT %s
  ```
- API request models (`apps/api/main.py:169-179`):
  ```python
  class RetrieveRequest(BaseModel): query: str
  class GenerateRequest(BaseModel): query: str
  ```
- Playground (`apps/web/src/routes/playground.tsx`) sends only `{ query }` (`:58-62`);
  no controls; `GenerateResult` includes citations (`src/lib/types.ts`).
- Plan 012 adds join metadata to `ChunkHit` and `ChunkRef`; plan 013 populates it.

**Conventions**: SQL is parameterized `%s`; never string-interpolate values. The
web app uses shadcn/base-ui primitives and `clientApiJson` for POSTs; do **not**
add a new component library or a dark-mode toggle (`.interface-design/system.md`).

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| API tests | `.venv/bin/python -m pytest apps/api` | all pass |
| Retrieval smoke | `curl -sS -X POST localhost:8000/retrieve -H 'Content-Type: application/json' -d '{"query":"pods","filters":{"product":"Kubernetes"}}'` | hits only from Kubernetes |
| Facets | `curl -sS localhost:8000/corpus/facets` | JSON lists |
| Web types | `cd apps/web && npm run typecheck` | exit 0 |

## Scope

**In scope**:

- `apps/api/retrieve.py` — `Filters` model, config field, parameterized WHERE, protocols.
- `apps/api/main.py` — `filters` on requests + new `GET /corpus/facets`.
- `apps/api/generate.py` — pass filters from the request into `retrieve`.
- `apps/api/db.py` — a `corpus_facets(conn)` helper (parameterized).
- `apps/api/tests/test_retrieve.py`, `apps/api/tests/test_cors.py` (or a new
  `test_filters.py`).
- `apps/web/src/routes/playground.tsx`, `apps/web/src/lib/types.ts`,
  `apps/web/src/lib/server.ts` — two light controls + facets fetch + metadata in citations.
- `docs/contracts/hybrid-retrieval.md` — document filters.
- `plans/README.md` status row.

**Out of scope**:

- Rewriting RRF/FlashRank or the abstain policy.
- A full faceted-search UI (no sliders, no saved filters).
- User-origin isolation for evals (plan 020).
- Adding a shadcn `select` if a native `<select>` styled with tokens works.
- Query rewriting (plan 019).

## Git workflow

- Branch: `advisor/017-metadata-filters`
- Commit message: `Add optional metadata filters to retrieve and Playground.`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: `Filters` model + config

In `apps/api/retrieve.py`:
```python
class Filters(BaseModel):
    product: str | None = None
    doc_type: str | None = None
    source: str | None = None
    version: str | None = None
    license: str | None = None
    origin: str | None = None
    section: str | None = None
    doc_ids: list[str] | None = None
```
Add `filters: Filters | None = None` to `RetrieveConfig` and to
`retrieve_config_from_settings` (pass `None` by default).

**Verify**: `.venv/bin/python -c "from retrieve import Filters, RetrieveConfig; print(RetrieveConfig(filters=Filters(product='Kubernetes')).filters.product)"`.

### Step 2: Parameterized WHERE in both searches

- Add `filters: Filters | None = None` to `search_vector`, `search_fts`, and the
  `VectorSearchFn`/`FtsSearchFn` protocols (default keeps existing callers/tests valid).
- Build a shared helper:
```python
def _filter_sql(filters: Filters | None) -> tuple[str, list[Any]]:
    """Return (AND clauses joined, params) against documents d / chunks c."""
```
Rules: exact match on `d.product`, `d.doc_type`, `d.source`, `d.version`,
`d.license`, `d.origin`, `c.section`; `doc_ids` → `d.id = ANY(%s)`. Every value
is a bound param; **no f-string interpolation of values**. Return `("", [])` when
no filters.
- Update both SQL strings to `JOIN documents d ON d.id = c.doc_id` and include
  the clause + params. `search_vector` params become
  `[embedding_literal, *filter_params, embedding_literal, k]` in the right order.

**Verify**: add a unit test asserting `_filter_sql(Filters(product="Kubernetes"))`
returns a clause containing `d.product = %s` and params `["Kubernetes"]`, and that
a value containing `'` is passed as a param (never in the SQL string).

### Step 3: Thread filters through `retrieve`

`retrieve()` already takes `config`; use `config.filters` when calling the search
functions. Keep the empty-query path returning `[]`. Record the active filters on
the retrieve span attributes (`stage_sink`) so a trace shows filter → hybrid →
rerank.

**Verify**: `.venv/bin/python -m pytest apps/api/tests/test_retrieve.py` → pass;
add a test where the injected search fns receive the filters and the resulting
hits are filtered.

### Step 4: API request models + facets

In `apps/api/main.py`:
- `RetrieveRequest` and `GenerateRequest` gain `filters: Filters | None = None`.
- `post_retrieve` passes `RetrieveConfig(filters=request.filters)` into
  `retrieve(...)`; `post_generate` passes filters into the graph (via a settings-
  parallel config or a `filters` argument on `generate`).
- Add `GET /corpus/facets` → `corpus_facets(conn)` returning
  `{"products": [...], "doc_types": [...], "sources": [...], "licenses": [...]}`
  (distinct, non-null, sorted; freeze origin by default).
In `apps/api/generate.py`, accept and forward `filters` to `retrieve_fn` (the
default retrieve is called with the config).

**Verify**: `curl` Step "Retrieval smoke" returns only Kubernetes hits;
`/corpus/facets` returns lists. `.venv/bin/python -m pytest apps/api` → pass.

### Step 5: Playground controls

In `apps/web/src/routes/playground.tsx`:
- Fetch facets once (or in the loader) via `getFacets()` (`src/lib/server.ts`).
- Add two native `<select>` controls (Product, Doc type) styled with existing
  tokens (`bg-background border-border text-foreground`), placed in the form
  between the `Textarea` and the button row (`playground.tsx:106-137`). Include an
  "All" option.
- Include `filters` in the `/generate` body only when a non-"All" value is set.
- Show returned metadata in the citations table: add `product`/`section` columns
  (values may be `—` for older rows), using `font-mono tabular-nums` for ids.
- Add the needed optional fields to `apps/web/src/lib/types.ts`.

**Verify**: `cd apps/web && npm run typecheck` → exit 0; manual: ask a query with
Product=FastAPI and confirm citations are FastAPI-only and the trace shows the filter.

### Step 6: Contract update

In `docs/contracts/hybrid-retrieval.md`, document `Filters` and that filters are
applied to both pools before RRF; note `rerank_skipped` semantics are unchanged.

**Verify**: `git diff docs/contracts/hybrid-retrieval.md` shows the addition.

## Test plan

- `test_retrieve.py`: `_filter_sql` clauses/params; filters reach both search fns;
  no-filter path unchanged; a quote-bearing value is parameterized.
- `test_filters.py` (or `test_cors.py`): `/retrieve` and `/generate` accept
  `filters`; `/corpus/facets` shape.
- Web: typecheck only.
- Verification: `.venv/bin/python -m pytest apps/api` → pass; web typecheck → 0.

## Done criteria

- [ ] `Filters` exists; `RetrieveConfig`/requests accept it; both SQL searches
      apply parameterized predicates; protocols updated with defaults.
- [ ] Retrieval span shows the active filters; RRF+FlashRank unchanged.
- [ ] `/corpus/facets` returns non-null distinct values.
- [ ] Playground has Product/Doc-type controls that actually filter, and shows
      `product`/`section` in citations.
- [ ] Contracts updated; `pytest apps/api` and web typecheck pass.
- [ ] `plans/README.md` row 017 is DONE.

## STOP conditions

- A filter value would have to be concatenated into SQL — stop; parameterize.
- Applying filters makes ordinary queries return zero hits because the pre-filter
  pool is too small (e.g. `LIMIT k` before filtering) — stop and report; the
  filter belongs in SQL, not post-hoc truncation.
- The UI needs a new component library or a theme toggle — stop (forbidden).
- `GenerateResult`/`ChunkRef` lacks the fields and plan 012 is not present — stop
  and land 012 first.

## Maintenance notes

- Plan 019 (query rewrite) must preserve filters through the rewrite.
- Plan 020 will default eval retrieval to `origin="freeze"`; keep that separate
  from Playground's all-origins default.
- Reviewers: confirm no SQL string interpolation and that `/traces` shows the
  filter in the retrieve span.
- Deferred: saved filter presets, multi-select facets, and anchor-level sections.
