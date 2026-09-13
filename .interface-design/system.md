# Citebench interface system

## Direction

Citebench is a **research gym**, not a chat product. The circuit is the product:
**Index → Retrieve → Generate/Abstain → Score**. Frozen-corpus honesty, citation
grounding, public evals and traces. Demo screenshots open on Evals or a
failing/abstaining trace — never a chat bubble.

## Feel

Modern technical minimalism / utility-first. Heavy whitespace, a rigid grid,
subtle tonal layering, no playful illustration and no chat-bubble softness.
Think LangSmith / Arize Phoenix trace views + Perplexity citation density + a
clean research notebook. The chrome stays quiet so the data (chunks, scores,
traces) is the hero.

## Palette

Neutral cool-gray base; **semantic accents only**:

| Token | Role | Use |
| --- | --- | --- |
| `--background` / `--card` | canvas / surface | near-white / raised surface (dark: near-black blue) |
| `--foreground` / `--muted-foreground` | ink / muted ink | text, supporting copy — WCAG AA |
| `--primary` / `--ring` | action blue | primary actions, nav, focus rings |
| `--success` | grounded | generated answers, passed gate, grounded chunks |
| `--warning` | insufficient | abstain, low confidence, unmeasured |
| `--destructive` | failure | failed runs, hallucination/leak, failed gate |
| `--info` | retrieval | retrieve/process accents, links in the timeline |

Charts reuse the semantic series (`--chart-1..5` = grounded / retrieve /
abstain / neutral / failed). No purple SaaS accent, no gradients, no second hue
stack.

## Layout

Fixed left sidebar navigation (`Index | Ask | Evals | Traces | Corpus`, plus
`Metrics | About`) with a fluid content column; 12-column desktop grid,
`max-w-6xl` content, cards/tables over free-form chat. On mobile the sidebar
collapses to a top bar with a horizontal nav; traces stay readable in mono.

## Typography

- **Inter Variable** for UI and headings (system sans fallback).
- **Mono** (`font-mono`, `tabular-nums`) for chunk ids, scores, timestamps,
  latency/cost, and code-like traces.
- Headings tight-tracking, `text-balance`; body `text-pretty`, line-height 1.5+.

## Signature patterns

- **Circuit timeline**: numbered steps (Query → Retrieved chunks → Decision →
  Answer → Sources) on Ask; numbered cards on the Index.
- **Perplexity-style citations**: inline numbered citations that resolve to the
  persistent Sources panel; sources show only the retrieved chunks actually
  used. "Citations are a strict subset of retrieved chunk IDs."
- **Coverage**: "grounded on N of M retrieved chunks" next to the answer.
- **Retrieval transparency**: dense, FTS, RRF, and FlashRank scores in a mono
  table; cited rows tinted `--success`.
- **Abstention is a first-class success state**, not an error.
- Citation brackets from `CitebenchMark` remain the brand glyph.

## Motion

Bench-precise and quiet. One easing token `--ease-standard:
cubic-bezier(0.2, 0, 0, 1)`; state transitions 120–150ms; transform/opacity
only; no bounce/elastic; charts read immediately; reduced-motion fallback
everywhere.

## Forbidden

- Chat homepage, message-thread layout, chat-bubble softness
- Playful illustration, gradients, decorative blur
- Purple/indigo "AI product" accents; a second hue stack
- Invented metrics, trend deltas, or demo scores
- Gray body text below WCAG AA
- A second component library (shadcn + TanStack stay)
- Mass-changing `components.json` style (would regenerate primitives)
