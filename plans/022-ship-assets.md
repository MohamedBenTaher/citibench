# Plan 022: Ship assets — `/evals` screenshot, resume copy, pin + site blurb

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**:
> `git diff --stat 028fa3e..HEAD -- README.md apps/web/src/routes/__root.tsx docs/`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW (screenshots must be real; claims must match measurements)
- **Depends on**: plans 015 (live numbers), 021 (public repo)
- **Category**: direction (I4 / S2, S3, S4)
- **Planned at**: commit `028fa3e`, 2026-09-10

## Why this matters

The reviewer's first impression is the `/evals` gate or a failing `/traces` row,
not a chat bubble. This plan makes that literal: a real screenshot at the top of
the README, resume-ready copy that names the actual stack and live numbers, and a
pin + one-line blurb. It must not claim InnovX scale for Citebench — the only
InnovX reference is the anti-theater known-bad password example.

## Current state

- `README.md:1-7` opens with prose; there is no screenshot.
- `/evals` (`apps/web/src/routes/evals.tsx`) renders the RAGAS gate, redteam,
  and charts from `/evals/latest` + `/evals/redteam`.
- `/traces` (`apps/web/src/routes/traces.tsx`) renders a run list + detail with
  outcome badges (`failed`/`abstain`/`generate`).
- `apps/web/src/routes/__root.tsx` has route `head()` metadata for the app title.
- `docs/` holds contracts, `mcp.md`, `decision-trail.tsv`, and plan-005's
  `.interface-design/system.md` direction (paper/ink). No positioning doc.
- Live numbers live in `evals/results/latest.json` (`mode=live`) and `/metrics`
  after plan 015.
- `.interface-design/system.md` forbids chat-homepage framing and invented scores.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Run stack | `make start` | `/evals` loads |
| Capture | OS screenshot of `/evals` at ~1280px | PNG saved |
| Web types | `cd apps/web && npm run typecheck` | exit 0 |
| Numbers | `curl -sS localhost:8000/metrics` | live values |

## Scope

**In scope**:

- `docs/screenshots/` (**create**) — `evals.png` (+ optional `failing-trace.png`).
- `README.md` — screenshot at/near the top; "What this demonstrates" copy; License tie-in from 021.
- `docs/positioning.md` (**create**) — one-paragraph blurb + resume bullets.
- `apps/web/src/routes/__root.tsx` — `<meta name="description">` + OpenGraph tags (no layout change).
- `plans/README.md` status row.

**Out of scope**:

- Redesigning the UI (plans 005–007 are done).
- Fabricating a screenshot, a demo URL, or a metric.
- Changing numbers (they come from 015).
- A marketing landing page or a second component library.

## Git workflow

- Branch: `advisor/022-ship-assets`
- Commit message: `Lead the README with the eval gate and measured claims.`
- Screenshots are committed under `docs/screenshots/` (keep them reasonably small).
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Capture the first screenshot

Start the stack and open `/evals` at ~1280px with a **live** artifact present
(from plan 015) and a non-empty trace store. Capture `docs/screenshots/evals.png`.
Optionally capture a `/traces` detail for an out-of-corpus question whose outcome
is `abstain` (shows the bench refusing) as `docs/screenshots/abstain-trace.png`.
Do not capture a chat view; do not edit the screenshot to change numbers.

**Verify**: `ls -la docs/screenshots/` shows the PNG(s); the gate number in the
image equals `evals/results/latest.json`.

### Step 2: Lead the README with it

Put the `/evals` image immediately after the one-line intro (`README.md:1-3`),
with a caption that names the gate (`faithfulness` live, threshold 0.7, judge
model + date from plan 015). Keep the existing "not a chat product" framing.

**Verify**: `grep -n "screenshots/evals.png" README.md` and the image renders in
the GitHub preview.

### Step 3: Positioning copy (S3)

Create `docs/positioning.md` with:
- A one-paragraph blurb (S4) — see Step 4.
- Resume bullets naming the **actual** stack: TanStack Start (Vite/Nitro) +
  shadcn, FastAPI + Postgres 16 + pgvector, hybrid RRF + FlashRank cross-encoder,
  local nomic-embeddings, Groq `openai/gpt-oss-20b`, RAGAS with live
  method-tagged metrics, 10-case redteam, abstain-by-policy.
- The live numbers pulled from `latest.json`/`/metrics`, each with its method tag.
- An explicit line: "Citebench is a personal bench at its own corpus scale; it
  does not reuse or claim InnovX production scale."

Scan `README.md` and `docs/` for any claim of InnovX scale and remove it; the
InnovX password must remain only as the known-bad anti-theater example.

**Verify**: `grep -rni "innovx" README.md docs/ | grep -vi "password\|known-bad\|anti-theater"` → no scale claims.

### Step 4: Pin + site blurb (S4)

- Add a `## What this demonstrates` section to `README.md` (3–5 bullets) or link
  `docs/positioning.md`.
- Write the short blurb (one sentence, < 140 chars), e.g.:
  `Citation-grounded RAG bench: frozen corpus, hybrid retrieve, live RAGAS gate, abstain by policy.`
- Add it to `apps/web/src/routes/__root.tsx` `head()` as `description` plus
  `og:title`/`og:description` (no new dependency).
- For the GitHub **pin**: provide the blurb + repo description (from plan 021's
  topics) for the operator to set; do not change profile settings yourself.

**Verify**: `cd apps/web && npm run typecheck` → exit 0; `grep -n "og:description" apps/web/src/routes/__root.tsx`.

## Test plan

- Web typecheck after the `head()` change.
- Screenshot numbers must equal the live artifact (manual eyeball).
- No invented metrics in any new copy; unmeasured stays `—`.
- Verification: `pytest apps/api` (unchanged) and `npm run typecheck` pass.

## Done criteria

- [ ] `docs/screenshots/evals.png` is the first image in `README.md`; it is a real capture.
- [ ] `docs/positioning.md` exists with resume bullets + the explicit no-InnovX-scale line.
- [ ] README "What this demonstrates" + meta description/OG tags added.
- [ ] No invented numbers or demo URL; no chat-homepage framing.
- [ ] `npm run typecheck` exits 0; `pytest apps/api` exits 0.
- [ ] `plans/README.md` row 022 is DONE.

## STOP conditions

- The stack will not start or no live artifact exists — stop; do not screenshot a
  mock/empty state as if it were the gate.
- The only honest screenshot would show invented or placeholder metrics — stop.
- A copy change would claim InnovX scale or a second LLM/embedding vendor — stop.
- OpenGraph requires a new dependency — stop; use plain `meta` tags.

## Maintenance notes

- Re-capture the screenshot whenever the UI or the live artifact changes materially.
- Any published number must be regenerated by plan 015's live run before a release.
- Reviewers: compare the screenshot's numbers with `evals/results/latest.json`.
- Deferred: a hosted OG image/social preview generator.
