# Plan 020: Keep user uploads in a separate namespace so they cannot pollute the eval freeze

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index. **This plan is explicitly cuttable**: if it delays I3,
> stop and report.
>
> **Drift check (run first)**:
> `git diff --stat 028fa3e..HEAD -- apps/api/user_ingest.py apps/api/db.py apps/api/retrieve.py apps/api/generate.py citebench/eval/pipeline.py apps/api/tests/test_user_corpus.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P3 (builds on plan 008; cut if it delays I3)
- **Effort**: S
- **Risk**: LOW–MED (eval contamination is silent if wrong)
- **Depends on**: plan 008 (§008.1 user corpus), plan 017 (origin filter)
- **Category**: direction (I2 / R4)
- **Planned at**: commit `028fa3e`, 2026-09-10

## Why this matters

Once a user can paste a URL or upload a PDF, those chunks live in the same
`chunks` table as the freeze. If eval retrieval is not scoped, a user could
"fix" an eval by uploading the answer, or an eval could silently score against
user content — making every published number untrustworthy. Plan 008 already
namespaces user docs (`origin='user'`, ids `user-*`) and keeps the freeze wipe
off them. This plan closes the retrieval hole: eval-driven `generate` must
retrieve **freeze-only**, while Playground keeps its all-origins default.

## Current state (verify against live code after plan 008 lands)

- User ingest sets `origin="user"` (`apps/api/user_ingest.py:234`) and namespaced
  ids (`"user-" + sha256(...)[:16]`, `:65`, `:137`).
- Freeze wipe and unknown-doc cleanup are freeze-only
  (`db.py:207-208`, `:211-215`), so user rows survive.
- `retrieve()` has **no** origin predicate; pools come from all `chunks`. Plan
  017 adds `Filters.origin` applied to both SQL searches.
- `citebench/eval/pipeline.py:131-144` `live_answer` calls `generate(question)`
  with no filter; mock known-bad abstains via empty retrieve.
- `db.py` `corpus_stats` already reports `user_doc_count` separately (`:384-386`).
- Playground default is all origins (plan 008 / `DECISIONS.md`).

**Conventions**: `origin ∈ {freeze, user}`; SQL parameterized; eval must not need
a live DB in unit tests (inject search fns).

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| API tests | `.venv/bin/python -m pytest apps/api` | all pass |
| User corpus tests | `.venv/bin/python -m pytest apps/api/tests/test_user_corpus.py` | pass |
| Live eval (freeze-only) | `GROQ_API_KEY=<set> .venv/bin/python -m citebench.eval.ci --split evals/splits/ci.jsonl --known-bad evals/splits/known_bad.jsonl --threshold-faithfulness 0.7 --live --store-dir evals/results` | user chunks never cited |

## Scope

**In scope**:

- `apps/api/generate.py` — accept/forward an origin filter (once plan 017 adds `filters`).
- `citebench/eval/pipeline.py` — eval `live_answer` requests `origin="freeze"`.
- `apps/api/tests/test_user_corpus.py` (or `test_filters.py`) — isolation test.
- `DECISIONS.md` — restate the eval-isolation rule.
- `plans/README.md` status row.

**Out of scope**:

- Rebuilding plan 008 (uploads, caps, streaming) — that is 008.1.
- A UI for managing user namespaces.
- Gigabyte/hierarchy work (008.2/008.3).
- Changing Playground's all-origins default.

## Git workflow

- Branch: `advisor/020-user-namespace-isolation`
- Commit message: `Scope eval retrieval to the freeze namespace.`
- Do NOT push or open a PR unless the operator instructed it. If 008 is not
  merged, branch from 008's branch, not `main`.

## Steps

### Step 1: Confirm plan 008 state

Read `apps/api/user_ingest.py` and `apps/api/tests/test_user_corpus.py`. If user
docs are **not** namespaced with `origin='user'`/`user-` ids, STOP — 008.1 is a
prerequisite.

**Verify**: `grep -n 'origin="user"\|user-' apps/api/user_ingest.py` shows both.

### Step 2: Scope eval retrieval to freeze

- Ensure `generate()` accepts `filters` (plan 017) and forwards them to retrieve.
- In `citebench/eval/pipeline.py`, change `live_answer` to call
  `generate(question, filters=Filters(origin="freeze"))` (import from `retrieve`).
  Apply the same to any redteam live answerer in `citebench/eval/redteam.py` that
  calls `generate` directly.
- If `filters` support is not yet present, STOP and land plan 017 first.

**Verify**: `.venv/bin/python -m pytest apps/api/tests/test_eval_ci.py apps/api/tests/test_redteam.py` → pass (no network; injected answers).

### Step 3: Isolation test

Add a test that:
1. Builds a `retrieve()` call with an injected vector/fts search returning two
   chunks, one `origin="user"` and one `origin="freeze"`, with
   `Filters(origin="freeze")`.
2. Asserts the user chunk is excluded.
3. Asserts the unfiltered call returns both (Playground default).

At the SQL level, add a test asserting `_filter_sql(Filters(origin="freeze"))`
produced the `d.origin = %s` predicate (from plan 017).

**Verify**: `.venv/bin/python -m pytest apps/api/tests/test_user_corpus.py` → pass.

### Step 4: Decision note

In `DECISIONS.md`, restate: user sources live in `origin='user'`; freeze wipe and
**all eval/live retrieval** are freeze-only; Playground retrieves all origins.
Record a decision-trail row.

**Verify**: `git diff DECISIONS.md docs/decision-trail.tsv`.

## Test plan

- User-vs-freeze origin filter test (injected search fns).
- Eval `live_answer` passes the freeze filter (assert the fake `generate` receives it).
- Existing `test_user_corpus.py` wipe-survival tests still pass.
- Verification: `.venv/bin/python -m pytest apps/api` → all pass.

## Done criteria

- [ ] Eval live generation retrieves `origin="freeze"` only.
- [ ] Playground still retrieves all origins.
- [ ] Isolation test exists and passes; freeze wipe still leaves user rows.
- [ ] DECISIONS + trail updated.
- [ ] `pytest apps/api` exits 0.
- [ ] `plans/README.md` row 020 is DONE (or BLOCKED/cut with a reason).

## STOP conditions

- Plan 008's namespacing is absent — stop; do not re-implement 008 here.
- Freeze-only retrieval would silently drop all hits when the freeze row is
  missing — stop and report; do not "fix" by allowing user chunks in evals.
- This blocks I3 work — stop and report per the program note; 020 is cuttable.

## Maintenance notes

- Plan 017's default filter is `None` (all origins); evals must set it explicitly.
- Any new eval runner (future) must set `origin="freeze"`.
- Reviewers: confirm no eval path calls `generate`/`retrieve` without the freeze
  filter, and that user docs still show in Playground.
- Deferred: a per-namespace corpus selector and user-doc eval splits.
