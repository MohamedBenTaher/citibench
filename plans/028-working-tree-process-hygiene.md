# Plan 028: Working-tree & process hygiene — resolve the laya spike and expose the planning trail

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**:
> `git status --porcelain && git diff --stat 93c3bb9..HEAD`
> Compare the untracked/modified file list below against the live state; if the
> laya files are no longer present (someone already resolved them), skip Steps
> 1–2 and go to Step 3.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: dx + docs (process visibility)
- **Planned at**: commit `93c3bb9`, 2026-10-10

## Why this matters

Two things make the repo look unfinished to anyone who clones it: (1) a large
uncommitted experiment is stranded in the working tree (the "laya" reranker
spike — a *negative result* that is actually a strong engineering story but is
currently invisible, untracked files plus modified tracked files), and (2) the
planning/decision trail that proves the process is entirely gitignored
(`plans/`), so none of the rigor ships with the repo. Resolving both turns
"messy working tree + hidden process" into "committed, legible history + public
engineering trail."

## Current state

### 8.1 — Uncommitted laya spike

`git status --porcelain` shows (as of this plan):

Untracked:
- `apps/api/citebench_api/retrieval/laya_rerank.py`
- `scripts/laya_batch_server.py`
- `evals/results/laya-spike.json`
- `evals/results/retrieval-laya-gate.json`

Modified (part of the same spike):
- `apps/api/citebench_api/{config.py,generation/generate.py,retrieval/rerank.py,retrieval/retrieve.py,routes/__init__.py}`
- `apps/api/tests/{test_generate.py,test_rerank.py,test_settings.py,test_warmup.py}`
- `apps/web/src/components/retrieval-panel.tsx`
- `citebench/eval/retrieval.py`
- `config.yaml`
- `docs/{ARCHITECTURE.md,RETRIEVAL-EVALS.md}`
- `DECISIONS.md`
- `evals/results/retrieval.json`
- `.gitignore`

The spike's outcome, per `evals/results/retrieval-laya-gate.json`: the `laya`
reranker scores **worse** than the shipped FlashRank TinyBERT (recall@8
**0.8269** vs 0.9231, MRR 0.5833 vs 0.7205, nDCG@8 0.6269 vs 0.7687) and is
~42× slower per pair (63 ms vs 1.47 ms). The uncommitted `DECISIONS.md` diff
already documents the correct conclusion: keep TinyBERT, record the per-scale
threshold learning (`score_scale`: `logit` vs `noul`; `abstain_min_score` 0.12
vs `abstain_min_score_noul` 0.65). This is a **negative result to preserve**,
not code to keep active.

### 8.2 — Hidden planning trail

- `.gitignore:21` ignores `plans/`, so all 23+ numbered plans, `PROGRAM.md`,
  `PROGRAM-v1.md`, and the README index are local-only and never reach GitHub.
- `DECISIONS.md` and `docs/decision-trail.tsv` are tracked, so the *decisions*
  ship, but the *plans* that produced them do not.

### 8.3 — Missing honest-limitations note

The eval docs state the numbers but not the limits (n=26 answerable qrels,
in-sample threshold calibration, mock faithfulness is a fixture). A one-paragraph
"Limitations" section makes the honesty legible rather than discoverable only by
audit.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Status | `git status --porcelain` | the laya files listed, nothing unexpected |
| Tests (pre-commit) | `.venv/bin/python -m pytest apps/api -q` | 183 passed |
| Web typecheck | `(cd apps/web && npm run typecheck)` | exit 0 |
| Gitignore check | `git check-ignore plans/` | prints `plans/` (before Step 3) |

## Scope

**In scope**:
- Git history operations to commit the laya spike as a **documented negative
  result** (one commit), with the code changes reverted and only the artifacts
  + decision notes kept.
- `.gitignore` (remove or narrow the `plans/` entry).
- `docs/RETRIEVAL-EVALS.md` (add a "Limitations" section).
- `plans/README.md` (status update).

**Out of scope** (do NOT touch):
- Keeping the `laya_rerank.py` code path active — it is slower and worse; it
  must not become the default reranker.
- Any change to ranking defaults in `config.yaml` beyond reverting the spike's
  edits.
- Plan 021 (LICENSE, topics, visibility) and 022 (screenshots/resume) — separate.
- Rewriting history or force-pushing.

## Git workflow

- Branch: do the spike resolution on the current branch first (it is uncommitted
  work), then commit. If the operator prefers, commit to a `advisor/028-hygiene`
  branch instead — but the spike itself should land on `main` (via the branch
  it lives on) so the negative result is in the default history.
- Commit messages match repo style, e.g.
  `Record the laya reranker spike as a rejected negative result.`
- Do NOT push unless the operator asks.

## Steps

### Step 1: Confirm the spike is coherent and the tests pass as-is

Run the gates on the *current* working tree (spike included) to confirm the
uncommitted state is not broken:

```bash
.venv/bin/python -m pytest apps/api -q
(cd apps/web && npm run typecheck)
```

**Verify**: both exit 0. If tests fail, STOP — resolve nothing until you
understand why; the spike may have been mid-flight.

### Step 2: Commit the negative result (artifacts + decision), then revert the code

1. Stage and commit the **artifacts and documentation** of the spike, not the
   active code: `evals/results/laya-spike.json`,
   `evals/results/retrieval-laya-gate.json`, and the `DECISIONS.md` /
   `docs/RETRIEVAL-EVALS.md` edits that record the outcome and the per-scale
   threshold finding.

   ```bash
   git add evals/results/laya-spike.json evals/results/retrieval-laya-gate.json DECISIONS.md docs/RETRIEVAL-EVALS.md
   git commit -m "Record the laya reranker spike as a rejected negative result."
   ```

2. Revert the remaining spike changes to code/config (they are not wanted as
   active behavior): the `laya_rerank.py`, `scripts/laya_batch_server.py`,
   `retrieve.py`, `rerank.py`, `generate.py`, `config.py`, `config.yaml`,
   `retrieval-panel.tsx`, `citebench/eval/retrieval.py`, and the test edits —
   `git checkout -- <those paths>` (keep the two artifact JSONs and the two doc
   files already committed). Do **not** revert `DECISIONS.md` or
   `docs/RETRIEVAL-EVALS.md`.

**Verify**: `git status --porcelain` shows a clean tree (nothing untracked,
nothing modified); `git log --oneline -1` shows the negative-result commit;
`.venv/bin/python -m pytest apps/api -q` still exits 0; `git show --stat HEAD`
contains the two JSON artifacts and the two docs but not `laya_rerank.py`.

### Step 3: Expose the planning trail

1. In `.gitignore`, remove the `plans/` line (or replace with an allowlist that
   keeps `plans/*.md` while still ignoring any scratch). The plans are markdown
   and are safe to ship.
2. `git add plans/` and commit, or fold `plans/` into a `docs/plans/` location
   if the operator prefers the docs directory to own narrative. Keep the
   numbering monotonic (024+ continues from here).

**Verify**: `git check-ignore plans/` no longer prints `plans/` (or, if you
folded into `docs/`, `git ls-files docs/plans` lists the files);
`git ls-files plans | head` lists the plan files.

### Step 4: Add a "Limitations" section to the retrieval eval doc

In `docs/RETRIEVAL-EVALS.md`, add a short "Limitations" section stating, in
plain language:

- The qrels split is 26 answerable + 8 unanswerable questions (34 total); 22 of
  26 have a single gold doc, so Recall@8 ≈ hit-rate@8.
- The abstain threshold was calibrated **in-sample** on those same 8
  unanswerable rows; there is no held-out calibration split.
- The CI "faithfulness" is a mock fixture (contexts are the answer itself), so
  it is a pipeline sanity check, not a measurement; the live RAGAS path is the
  real judge and runs only when `GROQ_API_KEY` is present.

**Verify**: `grep -n "Limitations" docs/RETRIEVAL-EVALS.md` returns the section;
the three bullet phrases appear.

### Step 5: Full verification and index update

```bash
.venv/bin/python -m pytest apps/api -q
(cd apps/web && npm run typecheck)
git status --porcelain   # expect clean
```

Update `plans/README.md`: mark 028 DONE, and add a note under "Findings
considered and rejected" that the laya reranker was measured and rejected
(slower and lower recall) so a future `/improve` run does not re-litigate it.

**Verify**: pytest + typecheck exit 0; `git status` clean; the index row is
DONE.

## Test plan

- No new tests (this is a history/hygiene plan). Gates are the pytest + typecheck
  runs and `git status` cleanliness.

## Done criteria

- [ ] The laya negative result is committed (2 JSON artifacts + 2 doc notes),
      and the active-code spike changes are reverted.
- [ ] `git status --porcelain` is empty after Step 5.
- [ ] `plans/` (or its folded location) is tracked and `git check-ignore plans/`
      no longer ignores it.
- [ ] `docs/RETRIEVAL-EVALS.md` has a "Limitations" section with the three points.
- [ ] pytest (183) and web typecheck exit 0.
- [ ] `plans/README.md` status row updated and the laya rejection recorded.

## STOP conditions

- The uncommitted tree contains work that is **not** the laya spike (e.g. new
  half-finished features) — do not blanket-`git checkout --`; inventory first
  and report.
- `git checkout --` on the spike files would discard something the operator
  intends to keep — confirm the discard list with the operator before Step 2.
- The `plans/` directory contains anything sensitive (keys, URLs, personal
  notes) — do not un-ignore it wholesale; filter those files out first.

## Maintenance notes

- The laya spike taught a reusable lesson (per-`score_scale` abstain thresholds);
  keep that in `DECISIONS.md` — any future reranker swap must add a new
  `score_scale` + its own threshold, never share across scales.
- After un-ignoring `plans/`, treat plan files as first-class docs: keep them
  current in the index, and mark superseded ones stale rather than deleting
  history.
- Deferred: deciding whether the mock CI faithfulness should become a real
  (corpus-grounded) check — that is data authoring and belongs to a follow-up,
  not this hygiene pass.
