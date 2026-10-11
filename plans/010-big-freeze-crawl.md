# Plan 010: Grow the freeze to K8s + Azure + Postgres + FastAPI docs

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**:
> `git diff --stat 028fa3e..HEAD -- corpus/MANIFEST.md apps/api/manifest.py apps/api/tests/test_manifest.py docs/decision-trail.tsv`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: L
- **Risk**: HIGH (network crawl volume, license accuracy, parser assumptions)
- **Depends on**: plan 009 (`corpus-v0`; manifest/raw resolution)
- **Category**: direction (I1 / C2, C3, C4)
- **Planned at**: commit `028fa3e`, 2026-09-10

## Why this matters

The bench is only credible if the frozen corpus is big enough that retrieval
and abstention mean something. Today it is 14 pages. This plan replaces
`corpus/MANIFEST.md` with ~1,000+ pinned documentation pages from four
permissively licensed sources, each row carrying a recorded license. After this
lands, plan 011 adds OSTEP PDFs, plan 012 carries the new metadata into Postgres
and traces, and plan 013 re-ingests the whole thing.

The corpus is **documentation we are permitted to redistribute/snapshot**, not
scraped product data. Every source's license must be verified and recorded; if a
source cannot be crawled within its terms, drop it (or the whole slice) rather
than guessing.

## Current state

- `corpus/MANIFEST.md:18-38` is a hand-written 14-row table with header
  `| id | title | source_url | version_or_snapshot | license | pages |` and
  footer `docs=14. pages=1 per HTML URL`.
- `apps/api/manifest.py:34` requires `["id","title","source_url","version_or_snapshot","license"]`;
  unknown columns are parsed into `row` and dropped (`manifest.py:52-69`).
  A row with **fewer** cells than headers raises (`manifest.py:50-51`); extra
  columns are safe. So new manifest columns can be added before the DB knows
  about them.
- `apps/api/tests/test_manifest.py:8-29` asserts the repo manifest has
  **exactly 14** docs and a fixed id set. This test **must change**.
- `apps/api/snapshot.py:35-72` fetches one URL to `corpus/raw/<id>/page.html|document.pdf`
  and writes `sha256` + `meta.json` (`_write_meta`, `snapshot.py:152-172`).
  `documents.sha256` stores the digest (`apps/api/pipeline.py:205`).
- `docs/decision-trail.tsv` is a tab-separated log; the re-freeze rule in
  `corpus/MANIFEST.md:12-16` requires a new freeze date, a full URL list, a
  license re-check, and a decision-trail row.
- `scripts/` currently contains only `local-evals.sh`. There is no crawler.
- Python deps already include `httpx`, `beautifulsoup4`, `lxml` (`apps/api/requirements.txt`).

**License facts to re-verify at execution time (do not trust this plan alone)**:

| Source | License to verify | Where the license text lives |
|---|---|---|
| Kubernetes docs (`kubernetes.io/docs/`) | CC BY 4.0 | footer + `https://kubernetes.io/docs/contribute/` / repo LICENSE |
| Microsoft Learn Azure docs (`learn.microsoft.com/en-us/azure/…`, `/entra/…`) | CC BY 4.0 for docs | Learn page footer + Microsoft docs license terms |
| PostgreSQL docs (`postgresql.org/docs/`) | PostgreSQL License | `https://www.postgresql.org/about/licence/` |
| FastAPI docs (`fastapi.tiangolo.com`) | MIT | site footer / repo LICENSE |
| LangGraph docs (`langchain-ai.github.io/langgraph/`) | MIT | repo LICENSE (optional source) |

The executor must open each source's license page and record the exact string
(including a version/year if present) in the manifest `license` column and the
decision-trail detail. If a source's terms forbid automated snapshotting, drop
that source and report it.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| API tests | `.venv/bin/python -m pytest apps/api` | all pass |
| Build manifest | `.venv/bin/python scripts/crawl_manifest.py --write` | exit 0, writes `corpus/MANIFEST.md` |
| Size check | `.venv/bin/python -c "from manifest import parse_manifest; ..."` | prints row count |
| Robots check | `curl -sS https://kubernetes.io/robots.txt` | shows whether `/docs/` is allowed |

## Scope

**In scope**:

- `corpus/sources.yaml` (**create**) — seed URLs, allow-prefixes, license string,
  product/doc_type defaults, per-source page cap.
- `scripts/crawl_manifest.py` (**create**) — crawler + manifest writer.
- `corpus/MANIFEST.md` (**rewrite** the pinned table; keep policy/re-freeze prose)
- `apps/api/manifest.py` — only if a new column must be validated; **prefer no
  change** (unknown columns are already ignored).
- `apps/api/tests/test_manifest.py` — replace the "exactly 14" big-freeze test
  with a v0 test + a big-freeze floor test.
- `docs/decision-trail.tsv` — one re-freeze row.
- `README.md` — update the freeze date and corpus doc/page counts once ingested
  (plan 013 owns the final number; here update the manifest fact only).
- `plans/README.md` status row.

**Out of scope**:

- OSTEP PDFs — plan 011.
- DB schema / metadata columns — plan 012 (this plan only writes manifest columns).
- Re-ingest and README counts — plan 013.
- Editing `corpus/v0/**` — treat as immutable.
- Crawling anything not listed in `corpus/sources.yaml` (no blogs, no forums, no
  Stack Overflow, no paywalled books).
- Adding a second HTTP library or crawl framework.

## Git workflow

- Branch: `advisor/010-big-freeze`
- Commit message style: `Expand the freeze to K8s and Azure docs.`
- Do NOT commit `corpus/raw/**` (still gitignored). The manifest is the artifact.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Write `corpus/sources.yaml`

One block per source. Suggested shape (adjust values after license verification):

```yaml
freeze_version: "2026-09-10"
sources:
  - key: k8s
    product: Kubernetes
    source: kubernetes.io
    doc_type: concept
    license: "CC BY 4.0"
    seeds:
      - https://kubernetes.io/docs/
    allow_prefixes:
      - https://kubernetes.io/docs/
    max_pages: 1100
  - key: azure
    product: Azure
    source: learn.microsoft.com
    doc_type: reference
    license: "CC BY 4.0"
    seeds:
      - https://learn.microsoft.com/en-us/azure/aks/
      - https://learn.microsoft.com/en-us/azure/storage/blobs/
      - https://learn.microsoft.com/en-us/azure/azure-monitor/
      - https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/
    allow_prefixes:
      - https://learn.microsoft.com/en-us/azure/aks/
      - https://learn.microsoft.com/en-us/azure/storage/blobs/
      - https://learn.microsoft.com/en-us/azure/azure-monitor/
      - https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/
    max_pages: 300
  - key: postgres
    product: PostgreSQL
    source: postgresql.org
    doc_type: manual
    license: "PostgreSQL License"
    seeds: [https://www.postgresql.org/docs/current/]
    allow_prefixes: [https://www.postgresql.org/docs/current/]
    max_pages: 250
  - key: fastapi
    product: FastAPI
    source: fastapi.tiangolo.com
    doc_type: guide
    license: "MIT"
    seeds: [https://fastapi.tiangolo.com/]
    allow_prefixes: [https://fastapi.tiangolo.com/]
    max_pages: 150
  # Optional; cut if it delays the freeze:
  - key: langgraph
    product: LangGraph
    source: langchain-ai.github.io
    doc_type: guide
    license: "MIT"
    seeds: [https://langchain-ai.github.io/langgraph/]
    allow_prefixes: [https://langchain-ai.github.io/langgraph/]
    max_pages: 200
```

**Verify**: `.venv/bin/python -c "import yaml,pathlib; yaml.safe_load(pathlib.Path('corpus/sources.yaml').read_text())"` → exit 0.

### Step 2: Write `scripts/crawl_manifest.py`

Requirements:
- Args: `--write` (default dry-run), `--source <key>` (repeatable), `--max-pages`.
- For each source: check `robots.txt` with `urllib.robotparser.RobotFileParser`;
  if the seed paths are disallowed, print a clear error and skip that source.
- BFS/queue from seeds, same-origin + `allow_prefixes` only. Normalize URLs:
  drop fragments and query strings, strip trailing index pages, resolve
  `../`, skip non-HTML extensions (`.png`, `.zip`, `.pdf` here — PDFs are plan
  011).
- Throttle: at least `0.5s` between requests to the same host; use
  `snapshot.build_http_client()` (same UA). On 429/403: sleep, retry once, then
  **stop that source** and keep what was collected (do not hammer).
- Title: `<title>` text, else first `h1`, else URL slug.
- `id`: deterministic slug from the URL path — lower-case, strip host, replace
  non-`[a-z0-9._-]` with `-`, prefix with the source key (e.g.
  `k8s-concepts-workloads-pods`), cap ~80 chars, de-duplicate with a numeric
  suffix. Must match `manifest.py`'s `_ID_RE`.
- Emit a row `{id,title,source_url,version_or_snapshot,license,pages,doc_type,product,source}`;
  `version_or_snapshot = f"{freeze_version}"`, `pages = 1`.
- Sort rows by `(source, source_url)`, enforce `max_pages` per source.
- With `--write`, rewrite the table between the existing `| id | ...` header and
  the footer in `corpus/MANIFEST.md`, regenerate the `docs=N` line, and keep the
  policy/re-freeze prose. Update the `Freeze date:` line to `freeze_version`.
- Print a per-source summary: `key: N pages, license=<string>`.

**Verify**: `.venv/bin/python scripts/crawl_manifest.py --source fastapi --max-pages 5 --write`
→ 5 rows written, `git diff corpus/MANIFEST.md` shows the table replaced, then
revert that trial (`git checkout -- corpus/MANIFEST.md`) before the full run.

### Step 3: Run the full crawl

Run all sources (or with `--source` per source so failures are isolatable),
watching for 403/429. Record the exact license string per source in
`corpus/sources.yaml` and the manifest.

**Verify**:
```
.venv/bin/python -c "import sys; sys.path.insert(0,'apps/api'); from manifest import parse_manifest; from pathlib import Path; d=parse_manifest(Path('corpus/MANIFEST.md')); print(len(d)); print(sorted({x.license for x in d}))"
# rows > 900 (target ~1000+); every license non-empty; unique ids
```
If K8s robots or the crawl yields far fewer than ~900 rows, STOP and report the
per-source counts — do not pad the manifest with off-list pages.

### Step 4: Update tests

In `apps/api/tests/test_manifest.py`:
- Keep `test_parse_manifest_reads_table`.
- Replace `test_frozen_manifest_has_exactly_fourteen_pinned_urls` with:
  - `test_corpus_v0_has_fourteen_pinned_urls` → parse `corpus/v0/MANIFEST.md`,
    assert 14 (moved from the big freeze).
  - `test_big_freeze_has_minimum_size` → parse `corpus/MANIFEST.md`, assert
    `len(docs) >= 900`, all ids unique, all `source_url.startswith("https://")`,
    every `doc.license` non-empty.

**Verify**: `.venv/bin/python -m pytest apps/api/tests/test_manifest.py` → pass.

### Step 5: Decision trail + README freeze fact

Append to `docs/decision-trail.tsv`:
```
<today>	c2-big-freeze	MANIFEST expanded to N pages: <sources+licenses>; freeze <date>; corpus-v0 preserved	PASS
```
(Replace `<today>`/`N`/`<sources+licenses>` with real values; tab-separated.)
Update the `README.md` line that says "14 Kubernetes and Azure docs" to name the
new sources and freeze date — but leave the **Numbers** table counts for plan
013 (do not invent a page/chunk number here).

**Verify**: `git diff --stat docs/decision-trail.tsv README.md` shows only those edits.

## Test plan

- `test_manifest.py`: v0 stays 14; big freeze `>= 900`, unique ids, licenses set.
- Crawler has no automated network test in CI (AGENTS.md: CI has no live DB/network).
  Add a pure unit test for the **URL → id slug** and **same-prefix filter**
  helpers by importing them from `scripts/crawl_manifest.py`
  (`sys.path`-insert `scripts`); use fixed URL strings, no network.
- Verification: `.venv/bin/python -m pytest apps/api` → all pass.

## Done criteria

- [ ] `corpus/sources.yaml` lists every crawled source with its verified license.
- [ ] `corpus/MANIFEST.md` has `>= 900` rows, unique ids, non-empty license per row,
      freeze date updated.
- [ ] `scripts/crawl_manifest.py` exists, honors robots + throttle, and is
      deterministic (re-running produces a stable table).
- [ ] `apps/api/tests/test_manifest.py` updated; `pytest apps/api` exits 0.
- [ ] `docs/decision-trail.tsv` has the re-freeze row.
- [ ] No files outside the in-scope list modified (`git status`); `corpus/raw/**`
      not committed.
- [ ] `plans/README.md` row 010 is DONE.

## STOP conditions

- A source's robots.txt disallows the seeds, or the license page contradicts the
  table above — stop and report; do not crawl that source.
- Repeated 403/429 from a host after one retry — stop that source, report counts.
- The crawler pulls in off-prefix pages (e.g. blog/marketing) — fix the prefix
  filter; if it cannot be fixed, stop.
- The big-freeze count cannot reach ~900 without adding non-documentation pages —
  stop and report; lowering the target is an operator decision, not the executor's.
- `manifest.py` rejects the new table (short rows) — fix the writer; do not hand-edit
  900 rows.

## Maintenance notes

- `corpus/sources.yaml` is the freeze's source of truth; `corpus/MANIFEST.md` is
  generated from it. Future re-freezes edit `sources.yaml` and re-run the crawler.
- Plan 012 reads the `doc_type/product/source/version` columns this plan writes.
- Reviewers: spot-check 5 random rows — URL resolves to a real docs page, license
  matches `sources.yaml`, id is unique and stable.
- Deferred: incremental crawl/diff (only re-fetch changed pages) is out of scope;
  a full crawl is acceptable at this size.
