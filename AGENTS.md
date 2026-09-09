# Citebench agent notes

Citebench is a citation-grounded retrieval **bench**, not a chat product. `/` is a research-gym index. Playground is one ask. Demo screenshots start on `/evals` or `/metrics`.

## Verify

```bash
.venv/bin/python -m pytest apps/api
cd apps/web && npm run typecheck
```

CI has no Postgres. Do not add live-DB tests.

## Product constraints

- No chat homepage, no second LLM vendor, no invented eval scores
- FastAPI GET via TanStack `createServerFn` is forbidden; loaders use `fetchApiJson`
- `POST /ingest` wipe requires `CITEBENCH_ALLOW_WIPE=1`
