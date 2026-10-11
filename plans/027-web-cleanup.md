# Plan 027: Frontend cleanup — dead routes, broken citation anchors, dead deps, dedupe

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**:
> `git diff --stat 93c3bb9..HEAD -- apps/web/src apps/web/package.json apps/web/components.json`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: LOW
- **Depends on**: plan 026 (run after lint so the final diff is clean)
- **Category**: tech-debt (frontend polish)
- **Planned at**: commit `93c3bb9`, 2026-10-10

## Why this matters

These are small, visible defects that a reviewer immediately trips over: inline
citation `[1]` links that do nothing, six dead JSON routes, an unused font
dependency, and four copy-pasted number formatters. They are individually
trivial but collectively they read as "LLM-generated without cleanup" — the
opposite of the polish this project otherwise shows. Removing them is cheap and
highly legible in a code review.

## Current state

### 7.1 — Dead `/api/*` proxy routes (6 files, ~71 LOC)

`apps/web/src/routes/api/` contains `metrics.ts`, `traces.ts`,
`traces/$runId.ts`, `corpus/stats.ts`, `evals/latest.ts`, `evals/redteam.ts`.
Nothing in `apps/web/src` references `/api/*` except the generated
`routeTree.gen.ts` and the route files themselves (verified by grep). The app
fetches the API directly via `VITE_API_URL` (`apps/web/src/lib/client-api.ts:14`).
This is already recorded as known debt in `plans/README.md:91`.

### 7.2 — Broken citation anchor

`apps/web/src/components/markdown.tsx:82` renders inline citation markers as
`<a href="#sources">…</a>`. No element anywhere has `id="sources"` (verified by
`grep -rn 'id="sources"' apps/web/src` → only the `href="#sources"` match). The
`Sources` list is an unlabelled `<ol>` in `apps/web/src/routes/playground.tsx:501`.
So every inline citation link is a dead link.

### 7.3 — Dead dependency and stale config

- `apps/web/package.json` lists `@fontsource-variable/geist` (never imported in
  `src/`; the app uses `@fontsource-variable/inter`). Leftover from the
  Geist→Inter switch.
- `apps/web/components.json` has `"iconLibrary": "lucide"` while the app uses
  `@hugeicons` (Huge Icons) exclusively, and `"hooks": "@/hooks"` points at a
  nonexistent `src/hooks` directory.
- `apps/web/src/components/ui/separator.tsx` and `ui/textarea.tsx` are unused
  (41 LOC) — `textarea` is superseded by the inline textarea in `playground.tsx`.

### 7.4 — Duplicated formatters

Four near-identical "format a nullable number" helpers:

- `apps/web/src/routes/evals.tsx:62` `formatScore` → `value.toFixed(3)`
- `apps/web/src/routes/playground.tsx:38` `score` → `value.toFixed(3)`
- `apps/web/src/components/retrieval-panel.tsx:15` `rate`
- `apps/web/src/routes/metrics.tsx:17` `measured(value, digits = 3)`

Plus `metricLabel` duplicated verbatim at `apps/web/src/components/eval-charts.tsx:14`
and `apps/web/src/routes/evals.tsx:32`, and near-duplicate `attackKey`
(`eval-charts.tsx:29`) vs `attackLabel` (`evals.tsx:47`).

### 7.5 — Zero-vs-unmeasured drift

`apps/web/src/routes/metrics.tsx:113-115` explicitly warns "empty store is
unmeasured, not $0", but `apps/web/src/routes/corpus.tsx` renders literal `0`
docs when its loader fails (corpus.tsx:30,72,179). A failed load should read
"unmeasured", not `0`.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Typecheck | `cd apps/web && npm run typecheck` | exit 0 |
| Lint | `cd apps/web && npm run lint` | exit 0 (after plan 026) |
| Build (sanity) | `cd apps/web && npm run build` | exit 0 |

## Scope

**In scope**:
- `apps/web/src/routes/api/*` (delete) — the 6 dead route files
- `apps/web/src/components/markdown.tsx` (fix anchor target)
- `apps/web/src/routes/playground.tsx` (label the Sources list `id="sources"`)
- `apps/web/src/lib/` (new shared `format.ts` for the number helper)
- `apps/web/src/routes/evals.tsx`, `apps/web/src/routes/playground.tsx`,
  `apps/web/src/components/retrieval-panel.tsx`, `apps/web/src/routes/metrics.tsx`,
  `apps/web/src/components/eval-charts.tsx` (dedupe call sites)
- `apps/web/src/routes/corpus.tsx` (zero-vs-unmeasured)
- `apps/web/package.json` + lockfile (remove geist)
- `apps/web/components.json` (fix `iconLibrary`, `hooks` alias)
- `apps/web/src/components/ui/separator.tsx`, `ui/textarea.tsx` (delete if still unused)

**Out of scope** (do NOT touch):
- Any Python/API file.
- `routeTree.gen.ts` — it is generated; regenerating it via the dev server is
  acceptable but do not hand-edit it. If deleting the route files leaves stale
  generated entries, regenerate (see Step 2 note) or leave them; the source
  files are what matters.
- Rebuilding the TanStack data layer (the `useEffect` fetch pattern) — a
  separate, larger refactor; only the `id="sources"` label and formatter dedupe
  are in scope here.

## Git workflow

- Branch: `advisor/027-web-cleanup` (cut from `main`, after 026 is merged).
- Commit per logical unit; message style matches the repo, e.g.
  `Remove the dead /api proxy routes and fix citation anchors.`
- Do NOT push unless the operator asks.

## Steps

### Step 1: Remove the dead `/api/*` routes

Delete the six files under `apps/web/src/routes/api/`. If `routeTree.gen.ts`
still references them, regenerate the route tree per the project's TanStack
Start workflow (or leave the generated file — confirm with `npm run typecheck`).

**Verify**: `find apps/web/src/routes/api -type f` → empty (or directory gone);
`npm run typecheck` exits 0.

### Step 2: Fix the citation anchor

1. In `apps/web/src/routes/playground.tsx`, add `id="sources"` to the Sources
   `<ol>` (the element that lists `result.citations`).
2. Confirm `apps/web/src/components/markdown.tsx:82`'s `href="#sources"` now
   resolves.

**Verify**: `grep -rn 'id="sources"' apps/web/src` returns the playground line;
`grep -rn 'href="#sources"' apps/web/src` still returns the markdown line.

### Step 3: Remove the dead dependency and fix config

1. `cd apps/web && npm uninstall @fontsource-variable/geist` (updates
   `package.json` + lockfile).
2. In `apps/web/components.json`, change `"iconLibrary": "lucide"` →
   `"iconLibrary": "hugeicons"` and `"hooks": "@/hooks"` → `"hooks": "@/lib"`.
3. Delete `apps/web/src/components/ui/separator.tsx` and `ui/textarea.tsx` only
   if `grep -rn "ui/separator\|<Separator\|ui/textarea\|<Textarea" apps/web/src`
   confirms zero imports.

**Verify**: `grep -rn "geist" apps/web/package.json apps/web/src` → no matches;
`npm run typecheck` exits 0.

### Step 4: Dedupe the formatters

Create `apps/web/src/lib/format.ts` exporting a single helper, e.g.:

```ts
export function formatNumber(value: number | null | undefined, digits = 3): string {
  if (value == null || Number.isNaN(value)) return "unmeasured";
  return value.toFixed(digits);
}
```

Then replace the four local helpers (`formatScore`, `score`, `rate`, `measured`)
with imports of `formatNumber`, and consolidate the duplicated `metricLabel`
and `attackLabel`/`attackKey` into one shared module (either `format.ts` or a
new `apps/web/src/lib/labels.ts`), updating `eval-charts.tsx` and `evals.tsx`
to import from it. Preserve the "unmeasured" vs "0" distinction where a caller
relies on it (metrics shows "unmeasured"; corpus must too — see Step 5).

**Verify**: `grep -rn "function formatScore\|function score\|function rate\|function measured" apps/web/src` → no matches; `npm run typecheck` and `npm run lint` exit 0.

### Step 5: Zero-vs-unmeasured consistency

In `apps/web/src/routes/corpus.tsx`, where a failed/empty stats load currently
renders `0` for docs/chunks, render `"unmeasured"` (or the existing unmeasured
style used by `metrics.tsx`) when the value is `null`/undefined rather than a
real zero. Keep `0` only for a genuine, successful empty corpus.

**Verify**: `npm run typecheck` and `npm run lint` exit 0; visually the Corpus
tab no longer claims `0` on a failed load.

### Step 6: Full verification

```bash
cd apps/web && npm run typecheck && npm run lint && npm run build
```

**Verify**: all exit 0.

## Test plan

- No automated unit tests exist for the web app today; the gates are
  typecheck + lint + build.
- Manual smoke (operator, optional): start the app, ask a question with
  citations, confirm `[1]` jumps to the Sources list.

## Done criteria

- [ ] `apps/web/src/routes/api/` is empty or removed; typecheck passes.
- [ ] `id="sources"` exists and the markdown `#sources` link resolves.
- [ ] `@fontsource-variable/geist` removed; `components.json` `iconLibrary` is
      `hugeicons` and `hooks` points at a real path.
- [ ] One shared number formatter replaces the four copies; no duplicate
      `metricLabel`.
- [ ] Corpus tab renders `unmeasured` (not `0`) on a failed load.
- [ ] `npm run typecheck && npm run lint && npm run build` all exit 0.
- [ ] No files outside the in-scope list are modified (`git status`).

## STOP conditions

- Deleting `/api/*` routes breaks `routeTree.gen.ts` typecheck in a way that
  cannot be fixed by regeneration — STOP and report; do not hand-edit the
  generated file.
- `ui/separator.tsx` or `ui/textarea.tsx` turns out to be imported (grep shows
  a caller) — keep them; do not delete imported code.
- Consolidating a formatter changes a value's display in a way that breaks an
  existing snapshot/expectation — revert that call site to its prior behavior.

## Maintenance notes

- Any future `shadcn` component regeneration will rewrite `components.json` and
  may re-add the `lucide`/`hooks` values — re-check after `npx shadcn@latest add`.
- Keep the shared `formatNumber`/label helpers in `apps/web/src/lib/` and route
  new code through them instead of adding a fifth copy.
- The larger data-layer cleanup (loaders vs `useEffect` fetches) is intentionally
  deferred; it is a bigger refactor than this polish pass.
