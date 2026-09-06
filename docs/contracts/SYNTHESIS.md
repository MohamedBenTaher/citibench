# Architect synthesis (C1)

This document grafts the arena into a landable C1 skeleton and records what
was rejected. It is not a scorecard.

## Grafts

- **Health-only FastAPI** in `apps/api`. `GET /health` returns
  `{"status":"ok"}`. No retrieve, no ingest, no chat routes.
- **Empty Next App Router** in `apps/web` with a boring index at `/` and four
  tab routes: `/corpus`, `/playground`, `/traces`, `/evals`. Playground copy
  states it is not a chat surface. (Later: same four tabs on TanStack Start;
  FastAPI contracts unchanged.)
- **Compose** services `api`, `web`, `db` (`pgvector/pgvector:pg16`). Langfuse
  is omitted on purpose.
- **`config.yaml`** binds Groq, nomic-embed-text-v1.5, MiniLM L-12, 512/64,
  top_k 8, faithfulness 0.7, empty `chat_model`.
- **`infra/postgres/init.sql`** — `CREATE EXTENSION IF NOT EXISTS vector`.
- **Contracts A/B/C** plus pydantic stubs. Loaders, `retrieve`, and
  `emit_trace` raise `NotImplementedError`.
- **Corpus freeze** of 14 public Kubernetes + Azure URLs (2026-09-05).
- **`known_bad.jsonl`** as the anti-theater split (InnovX / Acme).
- **Decision trail** row `github-land` for MohamedBenTaher/citibench.

## Rejects

- C2 PDF/HTML ingest, chunk writers, and pgvector upserts.
- Hybrid retrieve implementation (RRF + FlashRank runtime).
- LangGraph / agent graphs.
- Langfuse service, keys, or SDK calls.
- RAGAS CI workflow that would print a fake 0.7.
- MCP servers and third-party connectors.
- Chat homepage, streaming playground, or chat polish.
- Fine-tuned embedders or rerankers on the 14-doc freeze.
- Extra LLM providers beside Groq.

## Verification checklist

- [ ] `docker compose up --build` starts `api`, `web`, `db`.
- [ ] `GET /health` → 200 `{"status":"ok"}`.
- [ ] `CREATE EXTENSION vector` works on the Compose database.
- [ ] `/`, `/corpus`, `/playground`, `/traces`, `/evals` → 200.
- [ ] `/` is an index, not a chat UI.
- [ ] Playground states it is not a chat surface.
- [ ] Seed files present verbatim: `DECISIONS.md`, `corpus/MANIFEST.md`,
      `evals/splits/known_bad.jsonl`, Contracts A/B/C, `SYNTHESIS.md`,
      `docs/contracts/stubs/schemas.py`, `docs/decision-trail.tsv`.
- [ ] Line counts near targets: DECISIONS ~85, eval-jsonl ~80, schemas ~118.
- [ ] README has a one-liner and compose instructions; no fake metrics;
      0.7 called out as a future CI gate only.
