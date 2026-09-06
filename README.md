# Citebench

Citebench measures citation-grounded retrieval on a frozen public Kubernetes and Azure corpus.

## Run

```bash
docker compose up --build
```

- API health: `GET http://localhost:8000/health` → `{"status":"ok"}`
- Web: `http://localhost:3000/` (index plus `/corpus`, `/playground`, `/traces`, `/evals`)
- Database: Postgres 16 with pgvector (`CREATE EXTENSION vector`)

Langfuse is not part of this Compose stack.

## Config

See `config.yaml`. `faithfulness_threshold: 0.7` is a future CI gate only. This repository does not report RAGAS scores.

C1 is a skeleton: health, routes, contracts, and the frozen manifest. Ingest, retrieve, and eval execution are out of scope.
