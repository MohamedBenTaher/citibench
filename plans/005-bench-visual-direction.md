# Plan 005: Give the web UI a bench visual direction (paper, ink, citation brackets)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 85d12a0..HEAD -- apps/web/src/styles.css apps/web/src/routes/__root.tsx apps/web/src/components/citebench-mark.tsx apps/web/src/components/page-header.tsx apps/web/src/components/ui/button.tsx apps/web/src/components/ui/card.tsx apps/web/components.json`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: LOW
- **Depends on**: none (web-only; independent of plans 001–004)
- **Category**: direction
- **Planned at**: commit `85d12a0`, 2026-09-07

## Why this matters

The UI is shadcn **Nova / neutral** defaults: pure white, `oklch` gray scale, Geist, `max-w-5xl` card stack, grayscale `--chart-*`. Dark tokens exist in `styles.css` but nothing sets `class="dark"` on `<html>`. The only product-specific visual is `CitebenchMark` (ink square + citation brackets). Everything else could be any admin template.

Citebench’s job is a **frozen, inspectable citation bench**. Reviewers screenshot `/evals` or a failing `/traces` row. The chrome should read as paper + ink + brackets, not as a chat product. This plan retokens and tightens hierarchy; it does not add a theme toggle, a chat homepage, or a second component library.

## Current state

- `apps/web/src/styles.css` — `:root` uses `oklch(1 0 0)` background, `oklch(0.145 0 0)` foreground, `--radius: 0.625rem`, charts 1–5 are gray ramps. `--font-heading` aliases `--font-sans` (both Geist Variable).
- `apps/web/src/routes/__root.tsx` — sticky header, ghost/secondary nav buttons, `max-w-5xl`, pulse bar while navigating.
- `apps/web/src/components/citebench-mark.tsx` — 32×32 rounded square `fill-foreground`, bracket strokes `stroke-background`.
- `apps/web/src/components/page-header.tsx` — `h1` `text-2xl font-medium`.
- `apps/web/components.json` — `"style": "base-nova"`, `"baseColor": "neutral"`.
- No `.interface-design/system.md` in the repo.

**Product constraints** (from `DECISIONS.md` / README): `/` is an index, not a chat homepage; Playground/Evals stay public; shadcn on TanStack Start stays (no second library); do not invent demo metrics.

**Conventions**: Tailwind v4 `@theme inline` + CSS variables in `styles.css`. Bind to semantic tokens (`bg-background`, `text-muted-foreground`, `border-border`), not raw `gray-200`. Reuse `Button` / `Card` / `Badge` / `Separator` from `apps/web/src/components/ui/`. Prefer `@/lib/utils` `cn` (today some UI files import `from "cn"` — do **not** mass-rewrite those imports in this plan).

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Typecheck | `cd apps/web && npm run typecheck` | exit 0 |
| Dev (manual) | `cd apps/web && npm run dev` | Vite on :3000 (API may be separate) |

## Scope

**In scope**:

- `apps/web/src/styles.css`
- `apps/web/src/routes/__root.tsx` (header/main classes only; keep tab list and routing)
- `apps/web/src/components/page-header.tsx`
- `apps/web/src/components/citebench-mark.tsx` (optional: align radius/stroke with new tokens)
- `apps/web/src/components/stat-cards.tsx` (type hierarchy only: label muted/small, value ink/tabular)
- `.interface-design/system.md` (**create**) so later UI work does not re-default
- `plans/README.md` status row

**Out of scope**:

- Rewriting route bodies (homepage copy, Playground form) — plans 006 and 007
- Adding `next-themes` / a dark-mode toggle (`.dark` tokens may stay unused)
- Replacing shadcn / Geist / TanStack Router
- Changing FastAPI or chart library
- Mass-converting `from "cn"` imports
- Chat bubbles, message threads, landing-page hero marketing

## Git workflow

- Branch: `advisor/005-bench-visual-direction`
- Commit message: `Retoken the web UI as a paper-and-ink citation bench.`
- Do NOT push unless asked.

## Direction the executor must follow (do not invent another)

```
Intent:     Reviewer on a laptop judging grounded retrieve; calm inspectable freeze; not chat.
Hierarchy:  Page title + one focal region (eval gate / answer / selected trace). Nav is secondary.
Palette:    Paper (warm off-white), ink (near-black with a cool-blue bias), one accent for
            "cite" / focus ring derived from the mark, semantic destructive for leaks/failures.
            Charts: ink ramps + one pass/fail semantic, not five identical grays.
Depth:      Borders-only, low-opacity edges (technical bench). No heavy drop shadows.
Surfaces:   Canvas = paper; cards = same family, 1px border, not a second hue.
Typography: Keep Geist Variable. Heading: slightly tighter tracking, text-wrap: balance.
            Body: muted ink for supporting copy. Mono for ids, text_ref, scores (tabular-nums).
Spacing:    4px grid. Section gap 24–32px. Header tighter than content. max-w-5xl may stay.
Signature:  Citation brackets from CitebenchMark — reuse as a 2px ink rule or bracket motif
            on the header underline / page title, not a decorative gradient.
Rejecting:  Purple SaaS accent; Inter; chat-bubble layout; metric-card parking lot as the
            only composition (006 changes structure; here only stop the cards from looking
            identical to every Nova demo).
```

Suggested token targets (adjust to taste but stay in this world; use `oklch`):

- `--background`: warm paper, e.g. high L, small chroma toward yellow/red (~0.01–0.02), not `oklch(1 0 0)`
- `--foreground`: ink, slightly cool
- `--primary`: ink (buttons stay serious, not candy)
- `--muted-foreground`: readable gray-blue ink, contrast ≥ 4.5:1 on paper for small text
- `--border`: quiet, not the first thing you see
- `--chart-1`…`--chart-5`: distinct enough for generate / abstain / failed / blocked / leaked — **failed/leaked** may use `--destructive`; do not make every series gray

Keep `.dark { ... }` internally consistent if you touch it, but do not add a toggle.

## Steps

### Step 1: Write `.interface-design/system.md`

Create the file with: direction/feel, depth = borders-only, spacing base 4px, type notes (Geist, heading vs body vs mono), palette names (`paper`, `ink`, `cite-ring`), signature = citation brackets, forbidden = chat homepage / second library / invented scores.

**Verify**: file exists and mentions “not a chat product”.

### Step 2: Retoken `styles.css`

Update `:root` (and keep `.dark` from drifting into a random purple sidebar — today `.dark --sidebar-primary` is already a blue-violet `oklch(0.488 0.243 264.376)` while light sidebar is gray; if you edit `.dark`, neutralize that stray hue so unused dark tokens are not a landmine).

Add `html { -webkit-font-smoothing: antialiased; }` in `@layer base`.

**Verify**: `rg -n "oklch\\(1 0 0\\)" apps/web/src/styles.css` — `:root --background` should no longer be pure white `oklch(1 0 0)` unless you documented an exception. Charts should not all be `oklch(0.xx 0 0)` only.

### Step 3: Header and page title

In `__root.tsx`:

- Keep sticky header, `CitebenchMark`, tabs, loading indicator.
- Make the header sit on paper (`bg-background`) with a **quiet** border. Avoid a second “toolbar world” color.
- Active tab: still `aria-current="page"`. Visual: ink/secondary, not a loud pill that looks like a chat app selected channel.
- Optional: a 2px ink accent under the active tab or a thin bracket motif — must work at ~390px width (tabs wrap today).

In `page-header.tsx`:

- `h1` uses `text-wrap: balance` (Tailwind `text-balance`) and slightly tighter tracking.
- Description stays `text-muted-foreground`, `text-pretty`, `max-w-3xl`.

**Verify**: `npm run typecheck` in `apps/web`.

### Step 4: Stat card hierarchy

In `stat-cards.tsx`, make **value** win (weight/size/ink) and **label** lose (11–12px, muted, tracked). Keep `font-mono tabular-nums` on numeric values. Do not add icons or trend deltas (no invented trends).

**Verify**: typecheck.

### Step 5: Manual visual check

With `npm run dev` (and API if you have it):

- `/` `/corpus` `/playground` `/traces` `/evals` `/about`
- Desktop and ~390px
- Squint: header vs content hierarchy; charts not invisible gray-on-gray

If API is down, pages that load FastAPI may error — still check layout/tokens on `/` and `/about` (no loader).

## Test plan

- No new automated UI tests in this plan (repo has none for web).
- Gate: `npm run typecheck`.
- Pattern: existing shadcn components; do not hand-roll buttons.

## Done criteria

- [ ] `.interface-design/system.md` exists with the direction above
- [ ] `:root` paper/ink tokens committed; charts not a 5-stop gray ramp
- [ ] No dark-mode toggle, no chat homepage, no new UI library
- [ ] `cd apps/web && npm run typecheck` exits 0
- [ ] `git status` only in-scope files (+ lockfile only if you did not add deps — **do not add deps**)
- [ ] `plans/README.md` row 005 is DONE

## STOP conditions

- You believe you must add `next-themes`, Framer Motion, or a new font package — stop.
- Contrast of `muted-foreground` on paper fails WCAG AA for body/small text — fix tokens, do not drop the direction.
- Changing `components.json` `"style"` would regenerate all UI primitives — do **not** re-init shadcn.

## Maintenance notes

- Plan 006 restyles copy/layout on these tokens. Plan 007 does not retoken.
- Reviewers: screenshot `/evals` and `/about` — if it still looks like a default shadcn dashboard, tokens did not go far enough.
- Offer is already taken: `system.md` is the save file for future UI sessions.
