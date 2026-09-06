# Citebench

Citebench measures citation-grounded retrieval on a frozen public Kubernetes and Azure corpus.

## Run

```bash
cp -n .env.example .env   # then set GROQ_API_KEY
docker compose up --build
```

- API health: `GET http://localhost:8000/health` → `{"status":"ok"}`
- Web: `http://localhost:3000/` (index plus `/corpus`, `/playground`, `/traces`, `/evals`)
- Database: Postgres 16 with pgvector (`CREATE EXTENSION vector`)

Langfuse is not part of this Compose stack.

## Ingest (C2)

Set `GROQ_API_KEY` (https://console.groq.com/keys). Embeddings use only Groq
`nomic-embed-text-v1.5` via the OpenAI-compatible API.

```bash
# idempotent re-index of the 14 MANIFEST URLs
curl -sS -X POST http://localhost:8000/ingest -H 'Content-Type: application/json' -d '{}'

# optional wipe + reload
curl -sS -X POST http://localhost:8000/ingest -H 'Content-Type: application/json' -d '{"wipe":true}'

# stats (same counts as the Corpus tab)
curl -sS http://localhost:8000/corpus/stats
```

Or open `/corpus` and click **Ingest / Re-index**. Snapshots go to
`corpus/raw/<id>/` with `sha256` recorded on `documents.sha256` and in
`corpus/raw/<id>/sha256`.

## Config

See `config.yaml`. Chunking is 512 tokens / 64 overlap with tiktoken
`cl100k_base`. `faithfulness_threshold: 0.7` is a future CI gate only. This
repository does not report RAGAS scores.

`retrieve` and `emit_trace` remain stubs.
