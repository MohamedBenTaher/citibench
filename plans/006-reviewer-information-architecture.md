# Plan 006: Make `/` and `/evals` a reviewer index, not a placeholder shell

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 85d12a0..HEAD -- apps/web/src/routes/index.tsx apps/web/src/routes/evals.tsx apps/web/src/routes/about.tsx apps/web/src/routes/corpus.tsx apps/web/src/routes/__root.tsx apps/web/src/lib/server.ts apps/web/src/components/page-header.tsx`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: LOW
- **Depends on**: plans/005-bench-visual-direction.md (tokens/system.md). If 005 is not done, still ship copy/IA, but do not invent a second palette.
- **Category**: direction
- **Planned at**: commit `85d12a0`, 2026-09-07

## Why this matters

README: the homepage is an **index**; the interesting surfaces are Corpus, Playground, Traces, Evals; first screenshot is `/evals` or a failing `/traces` row, not a chat bubble.

Today `/` says **“Index of placeholder surfaces”** and includes a Metrics card with an **empty `CardContent`** and no link. `/evals` leads with a long CLI recap (`python -m citebench.eval.redteam …`) before the gate number a reviewer came for. `/corpus` puts operator notes (`VITE_API_URL`, wipe JSON, ONNX 0.5 GB) in the same voice as the freeze counts. `/about` already explains the product well — `/` should match that honesty without the “placeholder” framing.

This plan is information architecture and copy. It does not add a chat thread.

## Current state

- `apps/web/src/routes/index.tsx` — `PageHeader` title Citebench, description “placeholder surfaces… does not run retrieval.” Grid of link-cards + dead Metrics card.
- `apps/web/src/lib/server.ts` — `getCorpusStats`, `getEvalLatest`, `getRedteamLatest`, `getTraces` already exist for SSR via `fetchApiJson`.
- `apps/web/src/routes/evals.tsx` — Redteam card first, then RAGAS; `StatCards` for three metrics after charts; Refresh button; CLI in `CardDescription`.
- `apps/web/src/routes/corpus.tsx` — stats, ingest buttons including **“Re-index with one failure”** (dev simulate), paragraph about wipe/ONNX.
- `apps/web/src/routes/__root.tsx` — nav order Corpus, Playground, Traces, Evals, About.

**Conventions**: loaders catch errors and pass `loadError` rather than crashing (`corpus.tsx`, `evals.tsx`). Use `ErrorAlert`. Exhaustive `switch` on unions with `never` default (see `evals.tsx` `metricLabel`). Links: `preload="intent"`, `buttonVariants({ variant: "link" })` pattern on About.

**Product**: `/` stays an index and **must not** run generate. Empty evals/traces **must not** invent scores (existing empty-copy is correct; keep it).

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Typecheck | `cd apps/web && npm run typecheck` | exit 0 |

## Scope

**In scope**:

- `apps/web/src/routes/index.tsx`
- `apps/web/src/routes/evals.tsx`
- `apps/web/src/routes/corpus.tsx` (copy + empty/zero-corpus CTA; do not change ingest API)
- `apps/web/src/routes/about.tsx` only if a sentence contradicts the new index
- `apps/web/src/routes/__root.tsx` only if you add a document title per-route via `head` — optional
- `apps/web/src/lib/server.ts` only if index loader needs a helper (prefer existing functions)
- `plans/README.md` status row

**Out of scope**:

- Playground form behavior, traces table keyboard — plan 007
- Token palette — plan 005
- New `/metrics` React dashboard (README: scrape is JSON; a **link** to `GET /metrics` is enough)
- Hiding Evals behind login
- Removing “Re-index with one failure” entirely without a replacement: move it to a `<details>` labeled “Verification” so demo reviewers are not invited to fail ingest by default

## Git workflow

- Branch: `advisor/006-reviewer-information-architecture`
- Commit message: `Make the index and Evals tab lead with bench status, not placeholder copy.`
- Do NOT push unless asked.

## Steps

### Step 1: Homepage loader + focal status

Give `/` a `loader` that `Promise.all`s `getCorpusStats()` and `getEvalLatest()` (and optionally `getRedteamLatest()`). On failure, return zeros/`present: false` plus `loadError` (copy `evals.tsx` / `corpus.tsx` pattern). Do **not** call `/generate`.

Layout (focal first):

1. `PageHeader`: title **Citebench**. Description must **not** contain “placeholder”. Example direction: “Citation-grounded retrieve over a frozen 14-doc Kubernetes + Azure corpus. Abstain when the freeze cannot support the question.”
2. One **status strip** (Card or compact StatCards): corpus `doc_count` / `chunk_count`, last eval **faithfulness** or “unmeasured”, `mode` if present (`mock` vs `live`), gate 0.7 as labeled threshold — never fill p95/cost with zeros; use em dash / “unmeasured” like the README.
3. Primary actions: Button/Link to **`/evals`** (screenshot destination) and **`/playground`** (single ask). Secondary: Corpus, Traces, About.
4. Metrics: replace empty card with a short note + link. If the UI can reach the API origin, link to `{publicApiBase()}/metrics` in a new tab (`apps/web/src/lib/client-api.ts` `publicApiBase`). Say it is a scrape, not a dashboard.

Keep the five surface explanations, but as a compact list under the status strip — not six equal cards including a hollow Metrics tile.

**Verify**: `npm run typecheck`. Empty API: page still renders with unmeasured/error, no fake 1.000 faithfulness.

### Step 2: Evals tab — gate first

Reorder `/evals`:

1. Short `PageHeader` (keep “no login wall”; drop “not on a Playground chat bubble” to one clause max).
2. **RAGAS gate card first**: hero faithfulness (`text-3xl` / StatCards value), `mode`, `gate_passed` / `gate_reason`, threshold 0.7 labeled as **CI gate, not a published product score**.
3. Charts + companion metrics (precision, relevancy) as secondary.
4. **Redteam second**: blocked/leaked table; keep empty honest.
5. CLI commands: move into `<details>` “How this was run” so a screenshot is scores, not a terminal cheatsheet.
6. Keep Refresh, empty artifact copy, no invented charts.

**Verify**: typecheck. `evals.tsx` still uses exhaustive switches.

### Step 3: Corpus copy for humans vs operators

- Zero docs/chunks: one sentence **“Index is empty — ingest the freeze”** next to the primary Ingest button (focal).
- Move `VITE_API_URL`, wipe JSON, ONNX size into `<details>` “Operator notes”.
- Wrap **“Re-index with one failure”** in `<details>` “Verification” so it is not peer to Ingest.

Do not add `wipe: true` as a button.

**Verify**: typecheck.

### Step 4: Document titles (optional but small)

If TanStack Start `head` on child routes is already used only on root (`title: Citebench`), set per-route titles like `Evals · Citebench` via each route’s `head` if the version supports it. If unsure, skip — do not break `__root.tsx` `HeadContent`.

**Verify**: typecheck.

## Test plan

- No web unit tests in repo; do not add a framework in this plan.
- Manual: `/` with API up and API down; `/evals` with committed `evals/results/latest.json` (mock artifact exists in repo).
- Pattern: `evals.tsx` loader error handling.

## Done criteria

- [ ] `/` description has no word “placeholder”
- [ ] `/` has no empty Metrics `CardContent`
- [ ] `/` does not call generate
- [ ] `/evals` presents RAGAS gate before redteam CLI
- [ ] Empty evals/corpus do not invent numeric scores
- [ ] `cd apps/web && npm run typecheck` exits 0
- [ ] `plans/README.md` row 006 is DONE

## STOP conditions

- Loader would need a new BFF `createServerFn` GET — **forbidden** (README: those 401/500 on client nav). Use `getCorpusStats` / `fetchApiJson` only.
- You want a chat-style welcome or suggested-prompts carousel as the homepage focal — stop; that violates DECISIONS.
- Faithfulness from missing artifact shown as `0` or `1.000` without `latest.present` — stop and use unmeasured.

## Maintenance notes

- Plan 007 will add Playground → Traces deep links (already exist) and ingest confirmations.
- Reviewers: first paint of `/` and `/evals` should be usable as a demo screenshot without reading the Makefile.
