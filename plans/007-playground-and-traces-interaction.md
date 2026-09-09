# Plan 007: Fix Playground, Traces, and error UX so the bench is operable

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 85d12a0..HEAD -- apps/web/src/routes/playground.tsx apps/web/src/routes/traces.tsx apps/web/src/routes/corpus.tsx apps/web/src/lib/client-api.ts apps/web/src/lib/api.ts apps/web/src/lib/errors.ts`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: LOW
- **Depends on**: none strictly; apply plan 005 tokens if present. Do not wait on 001–004.
- **Category**: bug
- **Planned at**: commit `85d12a0`, 2026-09-07

## Why this matters

The tabs are operable but several interactions fight a reviewer:

1. Playground `toast.success` fires for **abstain** as well as generate (`playground.tsx` `onAsk`).
2. Ask submits empty/whitespace queries (API will abstain) with no client check.
3. Result is a wall: six equal StatCards, full `cost_method` string, retrieved ids as a comma list; the **answer** is not clearly the focal element.
4. Traces: `runInput` is `useState(selectedId ?? "")` and **does not sync** when `?run_id=` changes (e.g. “Open in Traces” from Playground). Table rows use `onClick` only (no keyboard). Nested `Button` inside the row double-handles click.
5. FastAPI 422 `detail` is an array; `clientApiJson` does `throw new ApiError(data.detail)`, which becomes `"[object Object]"` in toasts.
6. SSR `requestApi` in `api.ts` has **no timeout** — hung API hangs Corpus/Traces/Evals loaders.
7. Corpus ingest has no confirm and no duration hint while `busy`.

## Current state

Playground ask handler (`apps/web/src/routes/playground.tsx`):

```ts
const data = await clientApiJson<GenerateResult>("/generate", { ... });
setResult(data);
toast.success(terminalLabel(data.terminal));
```

Traces search state (`apps/web/src/routes/traces.tsx`):

```ts
const [runInput, setRunInput] = useState(selectedId ?? "");
```

Client errors (`apps/web/src/lib/client-api.ts`):

```ts
throw new ApiError(data.detail || `HTTP ${response.status}`, response.status);
```

SSR (`apps/web/src/lib/api.ts` `requestApi`): `http.request` / `https.request` with no `timeout`.

**Conventions**: exhaustive `switch` on `terminal` / `SpanKind` with `never`. `ErrorAlert` for inline errors. Sonner toasts already used. `Link` to `/traces` with `search={{ run_id }}` already exists on Playground.

**Product**: still not a chat — no message history, no streaming UI requirement. AbortController on Ask is nice-to-have; if added, must not require a new library.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Typecheck | `cd apps/web && npm run typecheck` | exit 0 |

## Scope

**In scope**:

- `apps/web/src/routes/playground.tsx`
- `apps/web/src/routes/traces.tsx`
- `apps/web/src/routes/corpus.tsx` (confirm + busy copy only)
- `apps/web/src/lib/client-api.ts`
- `apps/web/src/lib/api.ts`
- `apps/web/src/lib/errors.ts` (optional `formatApiDetail` helper)
- `plans/README.md` status row

**Out of scope**:

- FastAPI response shapes
- Langfuse
- Adding Vitest/Playwright (mention cases below; implement helpers so they are testable without a new runner)
- Wipe-index button
- Chat thread / streaming tokens

## Git workflow

- Branch: `advisor/007-playground-and-traces-interaction`
- Commit message: `Fix Playground abstain toasts, trace deep links, and API error text.`
- Do NOT push unless asked.

## Steps

### Step 1: Normalize API `detail` for humans

Add `formatApiDetail(detail: unknown): string` in `errors.ts` (or `client-api.ts`):

- `string` → use as-is
- `array` of objects with `msg` / `message` → join with `"; "`
- `object` with `msg` → that string
- else → `HTTP {status}` fallback at the call site

Use it in `clientApiJson` and `apiJson` (`apps/web/src/lib/api.ts`) before `new ApiError`.

**Verify**: `npm run typecheck`. Mentally: FastAPI 422 body `{ "detail": [{ "msg": "field required" }] }` must not stringify to `[object Object]`.

### Step 2: SSR timeout

In `requestApi`, set `req.setTimeout` (e.g. 15_000 ms) and `req.destroy` on timeout, rejecting with `ApiError("api timeout", 503)` or mapping in `apiJson`/`proxyToApi` to 503 JSON `{ detail: "api timeout" }`.

**Verify**: typecheck. Do not use a hanging integration test in CI (no API in web CI).

### Step 3: Playground

- Disable submit when `busy` or `query.trim()` is empty; `aria-busy` on the form while asking.
- Toasts: `toast.success` only when `terminal === "generate"`. Use `toast.message` or `toast.warning` for `abstain`. Keep `toast.error` on throw.
- Result layout: **Answer** card first and largest (`whitespace-pre-wrap`, existing). Badge generate vs abstain. Put latency + cost on one line. Hide full `cost_method` behind `<details>` “Cost method”. Citations table stays; retrieved ids can be `<details>` if long.
- Keep example buttons; they only fill the textarea (do not auto-submit).
- Do not add a message list.

**Verify**: typecheck.

### Step 4: Traces

- Sync the run-id input to the search param:

  `useState` + `useEffect` when `selectedId` changes, **or** key the input / controlled value from `selectedId` when the user is not mid-edit. Simplest correct approach: `useEffect(() => { setRunInput(selectedId ?? ""); }, [selectedId]);`

- Table rows: keep click-to-select. Add `tabIndex={0}` and `onKeyDown` Enter/Space to `selectRun` on the row, **or** drop row `onClick` and rely on the existing link-styled Button (preferred: **one** interactive control per row — the query button — and remove row `onClick` to avoid nested handlers). If you keep row click, do not nest a second Button that calls the same function.
- Format span times for display with `toLocaleString` or slice ISO; keep machine value in `title` if useful.
- Generate/abstain span `JSON.stringify` dumps: keep for operators but put inside `<details>` “Span attributes”.

**Verify**: typecheck.

### Step 5: Corpus ingest confirm

Before `runIngest({})`, `window.confirm` with a sentence that re-index can take minutes and downloads ONNX on first run. Skip confirm for the nested “Verification” failure simulation if that lives in `<details>` (plan 006); if 006 did not land, still confirm the primary Ingest button.

Busy label already “Indexing…” — keep; disable both buttons while `busy`.

**Verify**: typecheck.

## Test plan

- No new test runner. If you add `formatApiDetail`, keep it a pure function with obvious branches for a future unit test.
- Manual: Playground empty submit blocked; abstain example → warning toast, not success; Open in Traces fills the run-id field; 422 shows a real message if you can trigger validation.

## Done criteria

- [ ] Abstain does not `toast.success`
- [ ] Empty query cannot submit
- [ ] `formatApiDetail` (or equivalent) used on both client and SSR JSON errors
- [ ] SSR HTTP helper has a timeout
- [ ] Traces `?run_id=` updates the run-id input
- [ ] Trace table is not a clickable `tr` wrapping a duplicate Button (one pattern only)
- [ ] `cd apps/web && npm run typecheck` exits 0
- [ ] `plans/README.md` row 007 is DONE

## STOP conditions

- Adding React Query / Zustand for playground state — unnecessary; `useState` is enough.
- Changing generate API to stream — out of scope.
- `window.confirm` blocked in SSR — ingest handlers are client-only (`onClick`); do not call confirm in a loader.

## Maintenance notes

- FastAPI `detail` as string (HTTP 503 Groq key) must still display.
- Nested interactive controls in tables fail a11y audits; reviewers should tab through Traces without a mouse.
