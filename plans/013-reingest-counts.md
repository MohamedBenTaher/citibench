# Plan 013: Re-ingest the big freeze and make README counts match `/corpus/stats`

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**:
> `git diff --stat 028fa3e..HEAD -- apps/api/corpus_measure.py apps/api/db.py apps/api/metrics.py README.md DECISIONS.md evals/results/corpus.json Makefile`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED (long ingest; counts that look fabricated if not measured)
- **Depends on**: plan 012 (metadata columns populated on ingest)
- **Category**: direction (I1 / C7)
- **Planned at**: commit `028fa3e`, 2026-09-10

## Why this matters

The frozen corpus and the README's Numbers table must agree. Today the README
quotes 14 docs / 14 pages / 148 chunks counted from a live HTML fetch on
2026-09-06 (`README.md:159-161`), because there was no pgvector ingest in that
environment. After plans 010–012 the corpus is ~1,000+ pages and ~10k+ chunks
with metadata. This plan re-ingests it for real and rewrites the README table
from **`GET /corpus/stats`**, so no number is hand-typed and the method tag names
the measurement.

## Current state

- `apps/api/corpus_measure.py:17-78` measures docs/pages/chunks from snapshots
  (or a live fetch) and writes an artifact. It hardcodes the freeze date:
  `"freeze_date": "2026-09-05"` (`corpus_measure.py:65`), and the
  `measured_under` tag is built at `corpus_measure.py:49-53`:
  ```python
  measured_under = (
      f"live-html-fetch-{datetime.now(timezone.utc).date().isoformat()}"
      if fetched else "local-snapshots"
  )
  ```
  `_existing_snapshot` (`:137-144`) looks for `page.html`/`document.pdf`.
- `apps/api/db.py:377-386` `corpus_stats` returns `doc_count` (status ok),
  `page_count`, `chunk_count`, `user_doc_count`, `failures`.
- `apps/api/metrics.py:248-275` prefers live DB stats (`source="database"`),
  else `evals/results/corpus.json` (`measured_under`), else the manifest count.
- `README.md:157-166` Numbers table: docs 14, pages 14, chunks 148,
  faithfulness/context precision from the **mock** artifact, p95/cost unmeasured.
- `evals/results/corpus.json:3` is tagged
  `measured-under-live-html-fetch-2026-09-06`, freeze `2026-09-05`.
- Wipe gate: `POST /ingest {"wipe": true}` raises `WipeDisabled` unless
  `CITEBENCH_ALLOW_WIPE=1` (`pipeline.py:53-56`; 403 mapping `main.py:210-211`).
- Freeze wipe deletes only `origin='freeze'` (`db.py:207-208`), so user docs
  survive; `delete_unknown_documents` also freeze-only (`db.py:211-215`).
- Ingest is one HTTP fetch per manifest row (`pipeline.py:159-164`), then local
  nomic embed; a ~1k-row ingest takes on the order of tens of minutes and needs
  the ~0.5 GB ONNX cache warm.

**Conventions**: README method tags are lowercase kebab strings (e.g.
`measured-under-live-html-fetch-2026-09-06`) and every unmeasured row is `—`.
Never write a number that was not measured this run.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| API tests | `.venv/bin/python -m pytest apps/api` | all pass |
| Start stack | `make start` | API `/health` ok |
| Full re-ingest | `curl -sS -X POST localhost:8000/ingest -H 'Content-Type: application/json' -d '{"wipe": true}'` | 200, `run_status` ok |
| Counts | `curl -sS localhost:8000/corpus/stats` | doc/page/chunk counts |
| Measure artifact | `.venv/bin/python -m corpus_measure` (from `apps/api`) | writes `evals/results/corpus.json` |

## Scope

**In scope**:

- `apps/api/corpus_measure.py` — manifest-driven freeze date + paths; explicit
  `--write` behavior if it lacks one.
- `evals/results/corpus.json` — regenerated after ingest with a real tag.
- `README.md` — Numbers table (corpus rows) + "14 docs" prose from plans 010/011.
- `DECISIONS.md` — update the C7 corpus paragraph to the measured values/tag.
- `Makefile` — a documented `reingest` target (optional but preferred).
- `plans/README.md` status row.

**Out of scope**:

- Faithfulness/p95/cost rows — plan 015 (I3) fills those with **live** numbers.
  Leave them `—` here.
- Changing chunk size/overlap or the embed model.
- Committing `corpus/raw/**`.
- Adding an ANN index (plan 018 measures first).

## Git workflow

- Branch: `advisor/013-reingest-counts`
- Commit message: `Re-ingest the big freeze and report corpus counts.`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Make `corpus_measure.py` manifest-driven

- Read the freeze date from `corpus/MANIFEST.md`'s `Freeze date:` line instead of
  hardcoding `2026-09-05`; fall back to `local-snapshots` measurement only.
- Resolve the manifest/raw dir the same way plan 009 does
  (`settings.manifest_path` / `manifest_path.parent / "raw"`); do not hardcode
  `corpus/raw`.
- Ensure it has a runnable entrypoint (`if __name__ == "__main__":`) that writes
  `evals/results/corpus.json` and accepts `--fetch-missing` (default: use local
  snapshots; fail if a snapshot is missing unless fetched).

**Verify**: `.venv/bin/python -m pytest apps/api/tests` → pass (add a small test
that the freeze date is read from a temp manifest); running it on the current
snapshots prints a doc/page/chunk count.

### Step 2: Full re-ingest

- Ensure `CITEBENCH_ALLOW_WIPE=1` is set for the API (Compose env or `.env`), and
  nomic/FlashRank caches are warm (`CITEBENCH_SKIP_MODEL_WARMUP` unset).
- Run the wipe ingest. Watch the API logs for per-doc failures; a "partial" run
  with failures is acceptable to diagnose, but the final run must be `ok`.
- Confirm DB integrity:
```
curl -sS localhost:8000/corpus/stats | python -m json.tool
# doc_count > 900; page_count >= doc_count; chunk_count > 9000 (target 10k+);
# failures == []
```

**Verify**: `/corpus/stats` shows `doc_count` > 900 and no failures. If any doc
failed, fix the snapshot/parse issue and re-run the failed subset before counting.

### Step 3: Regenerate the measured artifact

Run `corpus_measure` **against the local snapshots** so the artifact does not
depend on the live network, and confirm its `measured_under` reflects this run
(e.g. `local-snapshots` or `live-html-fetch-<today>`), and `freeze_date` matches
the manifest.

**Verify**:
```
python -c "import json;d=json.load(open('evals/results/corpus.json'));print(d['docs'],d['pages'],d['chunks'],d['measured_under'],d['freeze_date'])"
```

### Step 4: Rewrite the README Numbers table (corpus rows only)

In `README.md:157-166`, set:
- **Corpus docs** = `doc_count` from `/corpus/stats`, method
  `pinned URLs in corpus/MANIFEST.md (freeze <date>)`.
- **Corpus pages** = `page_count`, method `documents.page_count from parse_doc; HTML=1, PDF pages` .
- **Corpus chunks** = `chunk_count`, method `tiktoken cl100k_base 512/64 after ingest`,
  and add the run tag `measured-under-live-ingest-<today>`.
- Update the earlier prose that says "14 Kubernetes and Azure docs" to the new
  source list and freeze date.

Do **not** touch the faithfulness/context-precision/p95/cost rows (plan 015).

**Verify**: for each corpus row, the README value equals `/corpus/stats`:
```
api=$(curl -sS localhost:8000/corpus/stats)
python - <<PY
import json,subprocess
s=json.loads(subprocess.check_output(["curl","-sS","localhost:8000/corpus/stats"]))
print("stats", s["doc_count"], s["page_count"], s["chunk_count"])
PY
# then eyeball README rows against these three numbers
```

### Step 5: DECISIONS + trail

Update `DECISIONS.md` C7 corpus paragraph (`:236-241`) to the measured
docs/pages/chunks and the new tag. Append a `docs/decision-trail.tsv` row:
`<today>\tc7-reingest\tfull freeze ingested; README counts = /corpus/stats (<N> docs/<P> pages/<C> chunks)\tPASS`.

**Verify**: `git diff --stat README.md DECISIONS.md evals/results/corpus.json docs/decision-trail.tsv`.

## Test plan

- Unit test for the manifest freeze-date reader (temp manifest).
- No test asserts a specific corpus size (sizes change across re-freezes); the
  `test_manifest.py` floor from plan 010 covers structure.
- Verification: `.venv/bin/python -m pytest apps/api` → pass; README/stats equality
  checked by hand as above.

## Done criteria

- [ ] `corpus_measure.py` reads the freeze date from the manifest and has a
      runnable writer.
- [ ] Full ingest ran clean (`/corpus/stats` `failures == []`, `doc_count > 900`).
- [ ] `evals/results/corpus.json` regenerated with this run's tag; freeze date matches.
- [ ] README corpus rows equal `/corpus/stats` exactly; method tags present; no
      invented numbers; faithfulness/p95/cost remain `—`.
- [ ] `DECISIONS.md` + decision-trail updated.
- [ ] `pytest apps/api` exits 0.
- [ ] `plans/README.md` row 013 is DONE.

## STOP conditions

- Ingest keeps failing on a specific doc after a fix attempt — stop and report
  the doc id + error; do not drop the row from the manifest to make counts pass.
- `/corpus/stats` and `corpus_measure` disagree (e.g. page count) — stop and
  report; do not paste whichever number looks better.
- The ingest would delete `origin='user'` rows — stop; wipe must stay freeze-only.
- Embedding the full corpus exhausts RAM/disk — stop and report; a batching path
  is plan 008.2, not this plan.

## Maintenance notes

- Plan 014 grounds eval splits in exactly the rows indexed here; changing the
  manifest after 014 means re-checking the splits.
- Plan 018 measures retrieve latency on this corpus; note the `chunk_count` in
  that plan's output.
- Reviewers: verify README numbers by curling `/corpus/stats` live, not by reading
  the diff.
