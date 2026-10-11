# Plan 009: Freeze today's 14 URLs as `corpus-v0` (offline smoke corpus)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**:
> `git diff --stat 028fa3e..HEAD -- apps/api/settings.py apps/api/snapshot.py apps/api/pipeline.py apps/api/main.py apps/api/tests/test_settings.py apps/api/tests/test_snapshot.py .gitignore Makefile`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: MED (touches the manifest/raw-dir resolution used by every ingest)
- **Depends on**: plan 008 branch settled/merged (008 also touches ingest)
- **Category**: direction (I1 / C1)
- **Planned at**: commit `028fa3e`, 2026-09-10

## Why this matters

Plans 010–013 grow the frozen corpus from 14 pages to ~1,000+ pages. That
makes quick iteration (parse → chunk → retrieve → eval) slow and network-bound.
This plan pins **today's 14 URLs as `corpus-v0`**: committed snapshots plus a
committed manifest, selected by env, fetched from disk (never HTTP). After this
lands, a smoke loop can re-index and eval the small corpus in seconds while the
big freeze is being built, and a bad big-freeze manifest cannot take the smoke
loop down with it.

This is not a new product surface. It is the same ingest path with a
configurable manifest + an offline snapshot mode.

## Current state

- `apps/api/settings.py:159-160` hardcodes the manifest under the corpus dir:
  ```python
  corpus_dir=corpus_dir,
  manifest_path=corpus_dir / "MANIFEST.md",
  ```
- `apps/api/pipeline.py:76-77` hardcodes the snapshot root under the corpus dir:
  ```python
  raw_root = settings.corpus_dir / "raw"
  raw_root.mkdir(parents=True, exist_ok=True)
  ```
- `apps/api/pipeline.py:196` computes the stored snapshot path relative to corpus:
  ```python
  rel_snapshot = str(snap.path.relative_to(settings.corpus_dir))
  ```
  (For `corpus/v0/raw/<id>/page.html` this yields `v0/raw/<id>/page.html`, which is fine.)
- `apps/api/snapshot.py:35-72` `snapshot_url(...)` always calls `client.get(...)`.
  There is no "use the snapshot on disk" path. `apps/api/corpus_measure.py:137-144`
  already has the read-side pattern for existing snapshots:
  ```python
  def _existing_snapshot(dest_dir: Path) -> Path | None:
      for name in ("page.html", "document.pdf"):
          candidate = dest_dir / name
          if candidate.is_file():
              return candidate
  ```
- `.gitignore` ignores snapshots: `corpus/raw/*` (line ~16) with only
  `!corpus/raw/.gitkeep`. `corpus/v0/raw/**` must be an explicit exception.
- `Makefile` has targets `setup start ingest evals test status logs stop down`
  (see README "Make target" table). There is no smoke target.
- `apps/api/tests/test_manifest.py:8-11` asserts the repo manifest has exactly 14
  docs. Plan 010 will move that claim to `corpus-v0`; do **not** change it here.
- The current `corpus/raw/<id>/` snapshots are gitignored and dated 2026-09-06.
  This plan re-fetches the 14 URLs today and commits the result under
  `corpus/v0/`.

**Conventions to match**: settings are loaded once via `load_settings()` in
`apps/api/settings.py`; env flags use `_env_flag` (`settings.py:169-170`).
Tests live in `apps/api/tests/` and use plain `def test_...()` functions with
`monkeypatch`/`tmp_path` (see `tests/test_settings.py`). Do not add a config
framework.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| API tests | `.venv/bin/python -m pytest apps/api` | all pass |
| Targeted tests | `.venv/bin/python -m pytest apps/api/tests/test_settings.py apps/api/tests/test_snapshot.py apps/api/tests/test_manifest.py` | all pass |
| Fetch v0 snapshots | `.venv/bin/python -m apps.api.snapshot_v0` (new script; see Step 3) | exit 0, writes `corpus/v0/raw/` |
| Offline smoke (manual) | `make smoke` | indexes v0 from disk, mock evals pass |

## Scope

**In scope**:

- `corpus/v0/MANIFEST.md` (**create**; 14 rows, current schema)
- `corpus/v0/raw/<id>/{page.html,document.pdf,sha256,meta.json}` (**create**; committed)
- `apps/api/settings.py` (manifest path resolver + snapshot-only flag)
- `apps/api/snapshot.py` (read-existing-snapshot helper)
- `apps/api/pipeline.py` (raw root from manifest parent; offline path)
- `apps/api/tests/test_settings.py`, `apps/api/tests/test_snapshot.py` (new cases)
- `.gitignore` (`!corpus/v0/raw/**` exception)
- `Makefile` (`smoke` target)
- `README.md` (one short "Smoke corpus" subsection)
- `scripts/snapshot-v0.sh` (**create**, optional wrapper for the fetch step)
- `plans/README.md` status row

**Out of scope**:

- `corpus/MANIFEST.md` — the big freeze is plan 010. Do not edit it here.
- New manifest columns (`doc_type`, `product`, `section`, …) — plan 012.
- `apps/api/tests/test_manifest.py` — its "exactly 14" claim is resolved in 010.
- Any change to retrieve, generate, or the web app.
- Deleting or rewriting `corpus/raw/` (leave the gitignored dev snapshots alone).

## Git workflow

- Branch: `advisor/009-corpus-v0`
- Commit per step. Message style matches `git log` (sentence case, imperative):
  e.g. `Freeze the 14-URL smoke corpus as corpus-v0.`
- The `corpus/v0/raw/**` snapshot bytes **must be committed** (that is the
  point). Do not add them to `.gitignore`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Add manifest + offline resolvers to settings

In `apps/api/settings.py`:

- Add a module function `_resolve_manifest_path(corpus_dir: Path) -> Path`:
  - read `CITEBENCH_MANIFEST` (`.strip()`); if set, return
    `Path(env)` (resolve relative to the process CWD; absolute paths are used
    as-is).
  - else return `corpus_dir / "MANIFEST.md"`.
- Add `snapshot_only: bool = False` to the `Settings` dataclass
  (`settings.py:36-69`), set from `_env_flag("CITEBENCH_SNAPSHOT_ONLY")`.
- Replace line 160 with `manifest_path=_resolve_manifest_path(corpus_dir),`.

**Verify**: `.venv/bin/python -m pytest apps/api/tests/test_settings.py` → pass,
and:
```
CITEBENCH_MANIFEST=corpus/v0/MANIFEST.md .venv/bin/python -c \
  "from settings import load_settings; print(load_settings().manifest_path)" \
  # from apps/api (PYTHONPATH) → .../corpus/v0/MANIFEST.md
```

### Step 2: Snapshot root follows the manifest

In `apps/api/pipeline.py:76`, change:
```python
raw_root = settings.corpus_dir / "raw"
```
to:
```python
raw_root = settings.manifest_path.parent / "raw"
```
This preserves today's behavior (manifest at `corpus/MANIFEST.md` → `corpus/raw/`)
and makes v0 land at `corpus/v0/raw/`.

**Verify**: `.venv/bin/python -m pytest apps/api/tests/test_pipeline.py` → pass.

### Step 3: Add the read-existing-snapshot helper + offline ingest

In `apps/api/snapshot.py`, add:
```python
def load_snapshot(*, raw_root: Path, doc_id: str) -> SnapshotResult:
    """Return the committed snapshot for doc_id, or raise SnapshotError."""
```
It reads `meta.json` (keys `sha256`, `content_type`, `filename`, `bytes`; see
`_write_meta` at `snapshot.py:152-172`) and returns a `SnapshotResult` for the
existing file. Raise `SnapshotError` with the missing path when the dir, meta,
or file is absent. Do **not** fetch.

In `apps/api/pipeline.py`, in `_ingest_one` (`pipeline.py:159-164`), branch:
```python
if settings.snapshot_only:
    snap = load_snapshot(raw_root=raw_root, doc_id=doc.id)
else:
    snap = snapshot_url(doc_id=doc.id, source_url=doc.source_url,
                        raw_root=raw_root, client=client)
```
Import `load_snapshot` alongside `snapshot_url` (line 28).

**Verify**: add a unit test (Step 6) that a `snapshot_only=True` settings ingest
of a doc with no on-disk snapshot raises `SnapshotError` and never constructs a
client. Then `.venv/bin/python -m pytest apps/api/tests/test_snapshot.py` → pass.

### Step 4: Create `corpus/v0/MANIFEST.md`

Copy the current `corpus/MANIFEST.md` table verbatim (same 14 ids, titles,
`source_url`s, `license` values) and update:
- Freeze date line to today's date.
- `version_or_snapshot` to `v0-<today>` (e.g. `v0-2026-09-10`).
- Keep the `pages` column.

Then update `.gitignore`: after `!corpus/raw/.gitkeep` add
```
!corpus/v0/raw/
!corpus/v0/raw/**
```
(Comment above it: `# corpus-v0 is a committed offline smoke corpus.`)

**Verify**: `git check-ignore -v corpus/v0/raw/k8s-pods/page.html` → exit 1
(not ignored). `git status --short corpus/v0` lists the new files.

### Step 5: Fetch and commit v0 snapshots

Add `scripts/snapshot-v0.sh` that runs a small Python entrypoint which, for each
`corpus/v0/MANIFEST.md` row, calls `snapshot_url` with
`raw_root=corpus/v0/raw`, using `build_http_client()` from `snapshot.py`. Put the
entrypoint in `apps/api/snapshot_v0.py` (a `__main__` block is fine) so it can
import `manifest`/`snapshot`. It must log each `id` → `sha256` and exit non-zero
if any doc fails.

Run it once. Confirm every dir has `page.html` or `document.pdf` plus `sha256`
and `meta.json`, and that all 14 succeeded.

**Verify**:
```
for d in corpus/v0/raw/*/; do test -f "$d/sha256" || echo "MISSING $d"; done
# no MISSING lines; 14 dirs
```

### Step 6: Tests

Add to `apps/api/tests/test_settings.py`:
- `test_manifest_env_override(monkeypatch, tmp_path)` — set
  `CITEBENCH_MANIFEST` to a known file, assert `load_settings().manifest_path`
  equals it.
- `test_snapshot_only_flag(monkeypatch)` — `CITEBENCH_SNAPSHOT_ONLY=1` →
  `load_settings().snapshot_only is True`; unset → `False`.

Add to `apps/api/tests/test_snapshot.py`:
- `test_load_snapshot_reads_meta(tmp_path)` — write a fake
  `raw/<id>/page.html` + `sha256` + `meta.json`, assert `load_snapshot` returns
  the same digest/content_type.
- `test_load_snapshot_missing_raises(tmp_path)` — `pytest.raises(SnapshotError)`.

Add to `apps/api/tests/test_manifest.py`:
- `test_corpus_v0_manifest_has_fourteen(tmp_path/REPO_V0)` — parse
  `corpus/v0/MANIFEST.md`, assert 14 unique ids and https URLs. (Keep the
  existing `corpus/MANIFEST.md` test untouched.)

**Verify**: `.venv/bin/python -m pytest apps/api` → all pass, including the new tests.

### Step 7: `make smoke` + README note

Add a `smoke` target to `Makefile` that documents and runs the offline v0 loop
against a **scratch database** so it cannot wipe the big freeze:
```
smoke:  ## Offline corpus-v0 smoke: ingest from disk + mock evals (scratch DB)
	CITEBENCH_MANIFEST=corpus/v0/MANIFEST.md \
	CITEBENCH_SNAPSHOT_ONLY=1 \
	CITEBENCH_ALLOW_WIPE=1 \
	DATABASE_URL=postgresql://citebench:citebench@127.0.0.1:5432/citebench_v0 \
	.venv/bin/python scripts/smoke.py
```
Create `scripts/smoke.py` that: calls `run_ingest(load_settings(), wipe=True)`,
prints `corpus_stats`, then shells the mock eval commands from
`scripts/local-evals.sh` (ci + redteam, `--mock`). It must fail if
`settings.snapshot_only` is false (guard against accidentally fetching).
Add one short `## Smoke corpus (corpus-v0)` subsection to `README.md` pointing
at `make smoke` and explaining it never fetches the network.

**Verify**: `.venv/bin/python -m pytest apps/api` → pass. (Running `make smoke`
end-to-end needs Docker Postgres + the v0 DB; if Docker is unavailable, report
that you could not run it and stop — do not skip the unit tests.)

## Test plan

- New unit tests: settings env override + flag; `load_snapshot` happy/missing;
  v0 manifest 14-row check. Structural pattern: `tests/test_settings.py`
  (monkeypatch env) and `tests/test_snapshot.py` (tmp_path).
- No live-network test. The fetch step is a one-time script, not CI.
- Verification: `.venv/bin/python -m pytest apps/api` → all pass.

## Done criteria

- [ ] `corpus/v0/MANIFEST.md` exists with 14 rows; freeze date is today; ids match
      the current 14.
- [ ] `corpus/v0/raw/` has 14 doc dirs, each with `sha256` + `meta.json` +
      snapshot body, and they are **tracked** (`git ls-files corpus/v0/raw | wc -l`
      `> 0`).
- [ ] `CITEBENCH_MANIFEST` + `CITEBENCH_SNAPSHOT_ONLY` are read by `settings.py`.
- [ ] `pipeline.py` derives `raw_root` from `manifest_path.parent`; offline path
      never calls `snapshot_url`.
- [ ] `.venv/bin/python -m pytest apps/api` exits 0; new tests exist and pass.
- [ ] `make smoke` target exists and points at a scratch DB (`citebench_v0`).
- [ ] No files outside the in-scope list are modified (`git status`).
- [ ] `plans/README.md` row 009 is DONE.

## STOP conditions

- `pipeline.py` or `settings.py` no longer match the excerpts (008 landed on
  top of them) — rebase the plan against live code before editing.
- Committing `corpus/v0/raw/**` fails because the bytes exceed a repo policy or
  a pre-commit hook blocks binary files — stop and report; do not force-add.
- A v0 source returns non-200 or a non-HTML/PDF body — stop and report the URL;
  do not substitute a different source (the freeze is a pinned list).
- The smoke target appears to require copying or wiping the **big-freeze** DB —
  stop; the scratch DB separation is required.

## Maintenance notes

- Plan 010 replaces `corpus/MANIFEST.md` and updates `test_manifest.py`. The v0
  manifest stays 14 rows forever; treat it as an immutable fixture.
- Any future manifest column must be added to **both** `corpus/v0/MANIFEST.md`
  (can stay at the old schema if `manifest.py` keeps them optional) and the big
  freeze.
- Reviewers: confirm no `corpus/v0/raw` file was hand-edited and every `sha256`
  matches its body (`cd corpus/v0/raw/<id> && shasum -a 256 page.html`).
- Deferred: a pure "parse-only" smoke with no DB is out of scope; if the eval
  loop needs it later, add it as a separate flag rather than degrading `make smoke`.
