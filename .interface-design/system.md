# Citebench interface system

## Direction

Citebench is a frozen, inspectable citation bench — **not a chat product**. Reviewers sit at a laptop judging grounded retrieve: calm surfaces, legible hierarchy, evidence you can screenshot. No chat bubbles, no landing-page hero, no invented demo scores.

## Feel

Paper and ink. Warm off-white canvas, near-black ink with a cool-blue bias, citation brackets as the signature motif. Serious bench chrome, not a SaaS dashboard or messaging app.

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

Citation brackets from `CitebenchMark` — reuse as a 2px ink rule or bracket motif on the header underline / page title. Never a decorative gradient.

## Forbidden

- Chat homepage or message-thread layout
- Second component library (shadcn + TanStack stay)
- Invented metrics, trend deltas, or demo scores
- Purple SaaS accent, Inter, dark-mode toggle
- Mass-changing `components.json` style (would regenerate primitives)
