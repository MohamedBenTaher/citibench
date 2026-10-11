# Plan 024: Fast-forward `main` to the full history and tag v1.0.0

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**:
> `git rev-parse --short HEAD && git rev-parse --short main && git rev-list --count main..HEAD`
> Expected: `HEAD` is `93c3bb9`, `main` is `a932dda`, and the count is `33`
> (or higher if more commits landed since). If `main` is not an ancestor of
> `HEAD`, treat it as a STOP condition — do not attempt a merge.

## Status

- **Priority**: P1 (everything else is invisible until this lands)
- **Effort**: S
- **Risk**: LOW (local fast-forward; push/tag are operator-gated)
- **Depends on**: none
- **Category**: direction (market / presentation)
- **Planned at**: commit `93c3bb9`, 2026-10-10

## Why this matters

A reviewer (or a hiring manager) who opens the repo sees the **default branch**,
`main`. Right now `main` is 33 commits behind the real work: it is missing the
entire layered `citebench_api` package, `docs/ARCHITECTURE.md`,
`citebench/eval/retrieval.py`, and the committed qrels artifact
`evals/results/retrieval.json` — i.e. the single most impressive parts of the
project. The work exists, but it is stranded on `user/workspace-corpus`. This
plan brings `main` forward and stamps a `v1.0.0` tag so there is a stable,
citable snapshot.

## Current state

- `HEAD` (current branch `user/workspace-corpus`) = `93c3bb9` ("Adopt the
  retrieval reviewer audit where it measured true."), 83 commits total.
- `main` = `a932dda` ("Harden ingest and generate, and add a Metrics
  scoreboard."), 50 commits total. `origin/main` is 49 commits (one local
  commit `a932dda` is unpushed).
- `main` **is** a strict ancestor of `HEAD` (verified:
  `git merge-base --is-ancestor main HEAD` → exit 0). A clean fast-forward is
  possible: `git merge-base main HEAD` = `a932dda`, `HEAD..main` is empty.
- Files missing on `main` but present on `HEAD` (spot check via
  `git cat-file -e main:<path>`):
  - `docs/ARCHITECTURE.md` — MISSING
  - `apps/api/citebench_api/retrieval/retrieve.py` — MISSING
  - `citebench/eval/retrieval.py` — MISSING
  - `evals/results/retrieval.json` — MISSING
- No tags exist (`git tag` → empty).

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Confirm topology | `git merge-base --is-ancestor main HEAD` | exit 0 (no output) |
| Count ahead | `git rev-list --count main..HEAD` | `33` |
| Fast-forward | `git checkout main && git merge --ff-only user/workspace-corpus` | "Fast-forward" message, exit 0 |
| Verify content | `git merge-base --is-ancestor 6d2ac35 main` | exit 0 |
| Tag (operator) | `git tag -a v1.0.0 -m "Citebench v1.0.0: citation-grounded retrieval bench"` | exit 0 |
| Push (operator) | `git push origin main v1.0.0` | exit 0 |

## Scope

**In scope**:
- The `main` branch pointer (via `git merge --ff-only`).
- Tag `v1.0.0` (operator-gated).

**Out of scope** (do NOT touch):
- Any source file. This is a git pointer change only.
- `user/workspace-corpus` and every `advisor/*` branch — leave them exactly as
  they are.
- Repo visibility / topics / LICENSE — that is plan 021.
- The uncommitted working-tree changes (the laya spike) — that is plan 028.
- Rewriting history, squashing, or force-pushing.

## Git workflow

- Do everything on a **local** copy first.
- `git checkout main` then `git merge --ff-only user/workspace-corpus`.
- **Do NOT push or tag without operator confirmation.** Tagging and pushing are
  the only two steps that touch the remote; the executor must pause before
  them and only run them when the operator says so.

## Steps

### Step 1: Confirm the topology

```bash
git fetch origin --dry-run 2>/dev/null || true   # optional; do not mutate
git rev-parse --short HEAD main origin/main
git merge-base --is-ancestor main HEAD && echo "FF-OK" || echo "FF-IMPOSSIBLE"
```

**Verify**: output shows `HEAD` = `93c3bb9`, `main` = `a932dda`, and `FF-OK`.
If `FF-IMPOSSIBLE`, STOP.

### Step 2: Fast-forward `main` locally

```bash
git checkout main
git merge --ff-only user/workspace-corpus
```

**Verify**: `git rev-list --count main` → `83`; `git log --oneline -1 main`
shows `93c3bb9 Adopt the retrieval reviewer audit where it measured true.`.

### Step 3: Confirm the important work is now reachable from `main`

```bash
for c in ef86633 39195c0 6d2ac35 93c3bb9; do
  git merge-base --is-ancestor $c main && echo "$c IN main" || echo "$c MISSING"
done
git cat-file -e main:docs/ARCHITECTURE.md && echo "ARCHITECTURE present" || echo "ARCHITECTURE MISSING"
git cat-file -e main:evals/results/retrieval.json && echo "retrieval.json present" || echo "retrieval.json MISSING"
```

**Verify**: all four commits report `IN main`; both files report `present`.

### Step 4: Run the verification gates from `main`

```bash
.venv/bin/python -m pytest apps/api -q
(cd apps/web && npm run typecheck)
```

**Verify**: pytest exits 0 (183 passed as of this plan); typecheck exits 0.
This proves `main` builds and tests cleanly after the fast-forward. If either
fails, STOP — the branch had uncommitted state that isn't reflected here.

### Step 5 (operator): Tag and push

Only after the operator confirms. Return to the feature branch afterwards if
that is where further work happens:

```bash
git tag -a v1.0.0 -m "Citebench v1.0.0: citation-grounded retrieval bench"
git push origin main v1.0.0
git checkout user/workspace-corpus   # optional, resume work branch
```

**Verify**: `git ls-remote --tags origin | grep v1.0.0` shows the tag; `git
rev-parse origin/main` equals `93c3bb9`.

## Test plan

- No code tests. Gates are the `git` commands above plus the pytest/typecheck
  run in Step 4.

## Done criteria

- [ ] `main` points at `93c3bb9` (83 commits) after a `--ff-only` merge.
- [ ] `docs/ARCHITECTURE.md`, `citebench/eval/retrieval.py`,
      `apps/api/citebench_api/retrieval/retrieve.py`, and
      `evals/results/retrieval.json` are all reachable from `main`.
- [ ] pytest (183) and web typecheck both pass from `main`.
- [ ] Tag `v1.0.0` exists locally and (operator) on `origin`.
- [ ] `plans/README.md` status row updated.

## STOP conditions

- `git merge-base --is-ancestor main HEAD` returns non-zero (history diverged) —
  do NOT attempt a merge or rebase; report and let a human decide.
- Any `HEAD..main` commit is non-empty (there are commits on `main` not on the
  feature branch) — those would need a real merge decision, not a fast-forward.
- pytest or typecheck fails from `main` in Step 4.
- Push/tag is required but the operator has not confirmed.

## Maintenance notes

- After this lands, make `main` the base for all new `advisor/*` branches, and
  fast-forward `main` after each merged program instead of letting it lag.
- Plans 025–027 modify files that will already be on `main` after this plan, so
  their branches should be cut from the new `main`.
- Plan 021 (repo visibility) and 022 (screenshots/resume blurb) are the natural
  follow-ons that make this public.
