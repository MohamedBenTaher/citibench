# Citebench MCP (C9)

Two tools over the Compose API. Not a marketplace, not extra connectors,
and not a UI.

| Tool | Wraps |
| --- | --- |
| `search_corpus` | `POST /retrieve` (C3 hybrid: RRF + FlashRank) |
| `get_trace` | `GET /traces/{id}` (C5 local store; `run_id` or `langfuse_trace_id`) |

## Run against Compose

From the repo root, with the venv that has `apps/api/requirements.txt`:

```bash
cp -n .env.example .env   # GROQ_API_KEY only needed for Playground generate
docker compose up --build

# stdio MCP (Cursor / Claude Desktop). Needs PYTHONPATH at repo root.
export CITEBENCH_API_URL=http://localhost:8000
export PYTHONPATH=.
python -m citebench.mcp
```

Host config (example):

```json
{
  "mcpServers": {
    "citebench": {
      "command": "python",
      "args": ["-m", "citebench.mcp"],
      "cwd": "/path/to/citibench",
      "env": {
        "CITEBENCH_API_URL": "http://localhost:8000",
        "PYTHONPATH": "/path/to/citibench"
      }
    }
  }
}
```

`search_corpus` needs an ingested index (same as `POST /retrieve`). Embeddings
are local nomic. `get_trace` reads `TRACE_STORE_DIR` through the API and works
without Groq.

## Smoke

```bash
# protocol only (no stack)
python -m citebench.mcp --smoke

# after compose is up (503 on search_corpus is still a successful call)
python -m citebench.mcp --smoke --live
```

## Schemas

`search_corpus` arguments: `{ "query": string }` (required).

`get_trace` arguments: `{ "run_id": string }` (required). `run_id` may be the
Citebench run id or a Langfuse id stored on that run.
