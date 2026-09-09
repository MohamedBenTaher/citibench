# Citebench interface system

## Direction

Citebench is a frozen, inspectable citation bench — **not a chat product**. `/` is a research-gym index: identity first, then live board, then the circuit. Reviewers still screenshot `/evals` or a failing trace, not a chat bubble. No invented demo scores.

## Feel

Paper and ink. A gym for research: numbered stations (floor, set, log, weigh-in), not neon or gamification. Warm off-white canvas, near-black ink with a cool-blue bias, citation brackets as the signature motif. Serious bench chrome, not a SaaS dashboard or messaging app.

## Palette

| Token role | Name | Use |
|------------|------|-----|
| `--background` | paper | Page canvas, header |
| `--foreground` | ink | Headings, primary text, active nav |
| `--ring` | cite-ring | Focus rings, cite accent (from CitebenchMark) |
| `--muted-foreground` | muted ink | Supporting copy, inactive nav — WCAG AA on paper |
| `--destructive` | leak/fail | Semantic failures, leaked citations |
| `--chart-*` | series | generate / abstain / failed / blocked / leaked — not five grays |

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

Citation brackets from `CitebenchMark` — reuse as a 2px ink rule, corner brackets on the gym hero, and header underline. Never a decorative gradient. Circuit copy: Floor / Set / Log / Weigh-in.

## Forbidden

- Chat homepage or message-thread layout
- Startup orange/blue palette or a second display font (keep Geist)
- Second component library (shadcn + TanStack stay)
- Invented metrics, trend deltas, or demo scores
- Purple SaaS accent, Inter, dark-mode toggle
- Mass-changing `components.json` style (would regenerate primitives)
