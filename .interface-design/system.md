# Citebench interface system

## Direction

Citebench is a frozen, inspectable citation bench — **not a chat product**. `/` is a research-gym index: identity first, then live board, then the circuit. Reviewers still screenshot `/evals` or a failing trace, not a chat bubble. No invented demo scores.

## Feel

Paper and ink. A gym for research: numbered stations (floor, set, log, weigh-in), not neon or gamification. Warm off-white canvas, near-black ink with a cool-blue bias, citation brackets as the signature motif. Serious bench chrome, not a SaaS dashboard or messaging app.

**Dark is the default.** The bench runs on ink: deep blue-black canvas, warm off-white text, the same citation-bracket motif. Light mode (paper) is available via the header toggle and is stored in `localStorage` under `citebench-theme`. The boot script in `__root.tsx` applies the stored theme before paint; `<html>` ships `class="dark"` so SSR matches the default.

## Palette

| Token role | Name | Use |
|------------|------|-----|
| `--background` | paper (light) / ink (dark) | Page canvas, header |
| `--foreground` | ink (light) / paper (dark) | Headings, primary text, active nav |
| `--ring` | cite-ring | Focus rings, cite accent (from CitebenchMark) |
| `--muted-foreground` | muted ink | Supporting copy, inactive nav — WCAG AA on the active canvas |
| `--destructive` | leak/fail | Semantic failures, leaked citations |
| `--chart-*` | series | generate / abstain / failed / blocked / leaked — not five grays |

Both palettes live in `apps/web/src/styles.css` (`:root` and `.dark`) and stay in
the same oklch family; no purple SaaS accent and no second hue stack.

## Depth

Borders only. 1px quiet edges on cards and header. No heavy drop shadows or glassmorphism toolbars.

## Surfaces

Canvas = paper. Cards share the same family (paper + 1px border), not a second hue stack.

## Typography

- **Geist Variable** for UI and headings (`font-heading` aliases sans).
- **Headings**: slightly tighter tracking, `text-balance`.
- **Body**: muted ink for descriptions, `text-pretty`.
- **Mono** (`font-mono`, `tabular-nums`): ids, `text_ref`, scores, stat values.

## Spacing

4px grid. Section gaps 24–32px (`gap-6` / `gap-8`). Header padding tighter than main content. Content width `max-w-5xl`.

## Signature

The citation bracket is the one signature, used **structurally**: corner brackets
on the hero, a bracket-framed eyebrow on `PageHeader`, a bracket tick on data
labels, and a bracket node on the ordered station rail on `/`. Everything else
stays quiet. Never a decorative gradient. Circuit copy: Floor / Set / Log /
Weigh-in / Scoreboard — a real ordered sequence, not a card grid.

## Anti-slop bans (unslop pass)

- No Inter / Roboto / Arial / system-ui as the brand voice (Geist stays)
- No purple/indigo "AI product" gradients
- No warm cream canvas as a default premium move (dark is default; light is secondary)
- No identical numbered card grids — the circuit is an ordered rail
- No broadsheet hairline rules or zero-radius used as decoration
- No bounce/elastic easing, hover-scale, or scattered decorative micro-animation
- No card-inside-card nesting; no decorative blur; no 999 z-index

## Forbidden

- Chat homepage or message-thread layout
- Startup orange/blue palette or a second display font (keep Geist)
- Second component library (shadcn + TanStack stay)
- Invented metrics, trend deltas, or demo scores
- Purple SaaS accent, Inter
- Mass-changing `components.json` style (would regenerate primitives)
