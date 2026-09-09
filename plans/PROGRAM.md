# Citebench improvement program

Advisor-only document. Executors implement from the numbered plan files, not from this overview.

Written against git `85d12a0` (2026-09-07). Status lives in `plans/README.md`.

Citebench is a **citation-grounded retrieval bench**, not a chat product. Runtime plans (001–004) cut ask/ingest latency without changing RRF, FlashRank, or Groq-as-sole-LLM. UI/UX plans (005–007) make the existing tabs readable as a bench for a reviewer, without a chat homepage or a second component library.

## Track A — Runtime optimization

| Plan | Outcome |
|------|---------|
| [001](001-skip-dead-groq-embed.md) | Embeddings default to local nomic ONNX; Groq `/embeddings` probe is opt-in |
| [002](002-retrieve-single-connection.md) | One Postgres connection per retrieve; no schema DDL on the read path |
| [003](003-warmup-local-models.md) | Warm nomic + FlashRank at API startup; persist FlashRank cache in Compose |
| [004](004-reuse-groq-http-client.md) | Reuse Groq HTTP client; cache tiktoken encoding |

Order: 001 → 002 → 003 (depends on 001) → 004 (independent).

## Track B — UI and UX

Who: a **reviewer or teammate** with Compose up, opening `/evals` or `/playground` on a laptop. They need to see: freeze counts, one grounded ask or abstain, a RunTrace, RAGAS/redteam scores. They are not chatting.

Feel: **inspectable freeze** — paper, ink, citation brackets (already in `CitebenchMark`). Not a SaaS chat shell, not a marketing landing page.

| Plan | Outcome |
|------|---------|
| [005](005-bench-visual-direction.md) | Tokens, type, and chrome match the bench (not default Nova gray chat-adjacent UI) |
| [006](006-reviewer-information-architecture.md) | `/` is a real index; Evals leads with the gate; copy stops saying “placeholder” |
| [007](007-playground-and-traces-interaction.md) | Ask/abstain, traces, ingest, and API errors behave like a tool, not a dump |

Order: 005 first (tokens), then 006 (structure/copy on those tokens), then 007 (behavior). 006 and 007 may land on the same branch if one executor owns the web app; do not skip 005 or charts will still look like grayscale shadcn defaults.

## What this program does not do

- Chat-as-homepage, conversation threads, extra LLM vendors, fine-tunes
- Login wall on Playground/Evals (C8)
- Invented metrics when traces/evals are empty
- Rewriting FastAPI contracts

## Verify

```bash
.venv/bin/python -m pytest apps/api
cd apps/web && npm run typecheck
```

Web plans also require a manual pass of `/`, `/corpus`, `/playground`, `/traces`, `/evals`, `/about` at desktop (~1280) and a narrow viewport (~390).
