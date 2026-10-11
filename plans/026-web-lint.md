# Plan 026: Add frontend lint/format and enforce the `fetchApiJson` rule in CI

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**:
> `git diff --stat 93c3bb9..HEAD -- apps/web/package.json apps/web/package-lock.json apps/web/src .github/workflows/eval-ci.yml`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none (independent of 024/025)
- **Category**: dx
- **Planned at**: commit `93c3bb9`, 2026-10-10

## Why this matters

The repo's single most important frontend rule — "FastAPI GET must go through
`fetchApiJson`, never TanStack `createServerFn`" — exists only as prose
(`AGENTS.md:17`, `README.md:60`, `docs/ARCHITECTURE.md:83`) and a comment
(`apps/web/src/lib/fetch-api.ts:10-13`). `tsc` cannot catch a reintroduction,
and there is no linter or formatter anywhere in the repo, so the rule is
enforced by nothing. Adding a minimal lint/format setup plus a CI grep turns
the rule from a suggestion into a failing build, and gives the whole frontend a
consistent style — directly visible "quality" to anyone who opens the code.

## Current state

- `apps/web/package.json` scripts: only `dev`, `build`, `start`, `typecheck`
  (`tsc --noEmit`). No `lint` or `format` script.
- No `eslint.config.*`, `biome.json`, `.prettierrc*`, or `.editorconfig` exists
  in the repo (verified by `find apps/web -maxdepth 2 -iname 'eslint*' -o -iname 'biome*' -o -iname '.prettierrc*'` → empty).
- CI (`.github/workflows/eval-ci.yml:40-44`) runs only `npm ci` + `npm run
  typecheck` for the web app.
- The rule lives in a comment at `apps/web/src/lib/fetch-api.ts:10-13` and the
  loaders route through `apps/web/src/lib/server.ts` (19 call sites). There are
  zero `createServerFn` call sites today (only the warning comment).
- The project uses TypeScript, React 19, TanStack Start, Tailwind v4, and
  `tsconfig.json` with `strict: true`. Keep any tooling consistent with a
  Vite/TS + React 19 setup.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Install | `cd apps/web && npm ci` | exit 0 |
| Typecheck | `cd apps/web && npm run typecheck` | exit 0 |
| Lint (after setup) | `cd apps/web && npm run lint` | exit 0, no errors |
| Format check (after setup) | `cd apps/web && npm run format:check` | exit 0 |
| Rule grep | `grep -rn "createServerFn" apps/web/src` | only the warning comment matches |

## Scope

**In scope**:
- `apps/web/package.json` (+ regenerated `apps/web/package-lock.json`)
- A new lint/format config file (`biome.json` or `eslint.config.mjs` + `.prettierrc`) in `apps/web/`
- `.github/workflows/eval-ci.yml` (add lint + rule-guard steps)
- Any mechanical formatting fixes the tool applies to `apps/web/src/**` on
  first run (bounded, review-only — see Step 4)

**Out of scope** (do NOT touch):
- `apps/api/**` and all Python (this plan is frontend-only).
- Refactoring or deleting dead routes — that is plan 027.
- `tsconfig.json` strictness flags (e.g. `noUncheckedIndexedAccess`) — out of
  scope for this plan; they risk a large diff and are a separate decision.

## Git workflow

- Branch: `advisor/026-web-lint` (cut from `main`).
- Commit message style matches the repo, e.g. `Add frontend lint and enforce
  the fetchApiJson rule in CI.`
- Do NOT push unless the operator asks.

## Steps

### Step 1: Choose and install the toolchain

Recommend **Biome** (one tool for lint + format, fast, first-class TS/React
support) to minimize config surface. If the operator prefers ESLint+Prettier,
that is acceptable but larger. Add the dev dependency:

```bash
cd apps/web
npm i -D @biomejs/biome
```

**Verify**: `node_modules/.bin/biome --version` prints a version.

### Step 2: Add a minimal config and scripts

Create `apps/web/biome.json` with a conservative starting config (enable the
recommended rules, set the formatter to match the existing 2-space style, and
set `lineWidth` generously to avoid a massive reformat). Add to
`package.json`:

```json
"lint": "biome check src",
"format": "biome check --write src",
"format:check": "biome check src"
```

**Verify**: `npm run lint` exits 0 (after Step 3).

### Step 3: Baseline — suppress, don't rewrite

Run `npm run lint`. For any pre-existing violations beyond trivial formatting,
**do not rewrite behavior**; fix only formatting automatically and leave
logical lint findings as a short `# biome-ignore` with a reason, or a TODO
recorded in `plans/README.md`. The goal is a **green baseline**, not a refactor.

**Verify**: `npm run lint` exits 0; `npm run format:check` exits 0.

### Step 4: Enforce the `fetchApiJson` rule in CI

Add a step to `.github/workflows/eval-ci.yml` (in the web job, after
typecheck):

```yaml
- name: Forbid createServerFn reads
  working-directory: apps/web
  run: |
    if grep -rn "createServerFn" src --include=*.ts --include=*.tsx | grep -v "Do not wrap GET loaders in createServerFn"; then
      echo "createServerFn usage found — reads must use fetchApiJson" >&2
      exit 1
    fi
```

Also add a `- name: Lint web` step running `npm run lint`.

**Verify**: `.github/workflows/eval-ci.yml` contains both new steps; locally
`grep -rn "createServerFn" apps/web/src` matches only the warning comment.

### Step 5: Full local verification

```bash
cd apps/web && npm run typecheck && npm run lint && npm run format:check
```

**Verify**: all three exit 0.

## Test plan

- No behavior tests. Gates: typecheck, lint, format:check, and the CI grep
  (verify the grep fails by temporarily inserting a `createServerFn` call in a
  scratch branch, then reverting).
- Verification: the three commands above all exit 0.

## Done criteria

- [ ] `apps/web/package.json` has `lint` and `format:check` scripts and the
      dev dependency installed (lockfile updated).
- [ ] `biome.json` (or equivalent) exists and `npm run lint` exits 0.
- [ ] `.github/workflows/eval-ci.yml` runs lint and the `createServerFn` guard.
- [ ] `grep -rn "createServerFn" apps/web/src` matches only the warning comment.
- [ ] `npm run typecheck` still exits 0.
- [ ] No files outside the in-scope list are modified (`git status`).

## STOP conditions

- The operator prefers a different toolchain (ESLint+Prettier) and wants it —
  switch, but do not mix both in one PR.
- `npm run lint` surfaces hundreds of pre-existing logical violations that
  cannot be fixed mechanically without behavior change — STOP, capture the
  count and categories, and report; do not mass-suppress.
- The CI guard grep trips on a legitimate server function — investigate before
  suppressing.

## Maintenance notes

- Plan 027 (frontend cleanup) should run **after** this so its deletions are
  formatted by the new tool and its final diff is lint-clean.
- New frontend work must pass `npm run lint`; keep the baseline green by
  treating lint failures as build failures.
- The `createServerFn` grep is deliberately a source-only check; keep it in the
  web job where the path is `apps/web/src`.
