# Citebench agent notes

Citebench is a citation-grounded retrieval **bench**, not a chat product. `/` is a research-gym index. Playground is one ask. Demo screenshots start on `/evals` or `/metrics`.

## Verify

```bash
.venv/bin/python -m pytest apps/api
cd apps/web && npm run typecheck
```

CI has no Postgres. Do not add live-DB tests.

Run web commands with **Node 22 / npm 10** (the version in `apps/web/Dockerfile`).
Regenerating `apps/web/package-lock.json` with a newer npm silently prunes the
nested `nitro/node_modules` resolutions, and the image's `npm ci` then fails with
"Missing: chokidar@4.0.3 from lock file". If you must add a web dependency, use
`npx npm@10 install` and confirm with a scratch `npx npm@10 ci`.

## Product constraints

- No chat homepage, no second LLM vendor, no invented eval scores
- FastAPI GET via TanStack `createServerFn` is forbidden; loaders use `fetchApiJson`
- `POST /ingest` wipe requires `CITEBENCH_ALLOW_WIPE=1`
