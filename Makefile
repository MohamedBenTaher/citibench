# Citebench local environment.
#   make setup   — .env + Python venv + API/eval deps
#   make start   — Compose (api, web, Postgres/pgvector)
#   make ingest  — index the frozen 14-doc corpus (local nomic-embed-text-v1.5)

PYTHON  ?= python3
UV      ?= uv
COMPOSE ?= docker compose
WEB_PORT ?= 3000
API     ?= http://127.0.0.1:8000
WEB     ?= http://127.0.0.1:$(WEB_PORT)
VENV    := .venv
PY      := $(VENV)/bin/python

.PHONY: help setup start up stop down logs status ingest evals evals-live smoke test mcp-smoke

help:
	@echo "Citebench"
	@echo
	@echo "  make setup      copy .env.example → .env, create .venv, install deps"
	@echo "  make start      docker compose up --build (api :8000, TanStack Start web :$(WEB_PORT), db)"
	@echo "  make ingest     POST /ingest (local nomic embeddings; first run downloads ONNX)"
	@echo "  make evals      pytest + mock RAGAS + mock redteam (local, before provision)"
	@echo "  make evals-live live RAGAS (Groq judge) + live redteam; required before a public tag"
	@echo "  make smoke      offline corpus-v0 smoke: ingest from disk + mock evals (scratch DB)"
	@echo "  make test       pytest only (uses .venv)"
	@echo "  make status     health + corpus stats"
	@echo "  make logs       follow Compose logs"
	@echo "  make stop       docker compose stop"
	@echo "  make down       docker compose down"
	@echo "  make mcp-smoke  protocol-only MCP smoke (no stack)"
	@echo
	@echo "After setup, put GROQ_API_KEY in .env (https://console.groq.com/keys)."

setup: .env $(PY)
	$(UV) sync --frozen
	@echo
	@echo "Setup done. Next:"
	@echo "  1. Set GROQ_API_KEY in .env (Playground generate)"
	@echo "  2. make start"
	@echo "  3. make ingest"
	@echo "  4. open $(WEB)/  (index)  $(WEB)/evals  (scores, not a chat homepage)"

.env:
	cp .env.example .env
	@echo "Wrote .env from .env.example — add GROQ_API_KEY before ingest/retrieve/generate."

$(PY):
	$(UV) venv $(VENV)

start up: .env
	@echo "Citebench web → $(WEB)  (not Gotenberg; that API also uses :3000)"
	WEB_PORT=$(WEB_PORT) $(COMPOSE) up --build -d
	@echo "Waiting for API $(API)/health ..."
	@i=0; \
	until curl -sf "$(API)/health" >/dev/null; do \
	  i=$$((i+1)); \
	  if [ $$i -ge 40 ]; then echo "API did not become healthy." >&2; exit 1; fi; \
	  sleep 2; \
	done
	@curl -sS "$(API)/health"; echo
	@echo "API  $(API)"
	@echo "Web  $(WEB)"
	@echo "Tabs $(WEB)/corpus  $(WEB)/playground  $(WEB)/traces  $(WEB)/evals  $(WEB)/about"

stop:
	$(COMPOSE) stop

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

status:
	@curl -sS "$(API)/health"; echo
	@curl -sS "$(API)/corpus/stats" || true; echo

ingest:
	curl -sS -X POST "$(API)/ingest" -H 'Content-Type: application/json' -d '{}'
	@echo
	@curl -sS "$(API)/corpus/stats"; echo

evals: $(PY)
	./scripts/local-evals.sh

# Live RAGAS + redteam. Needs GROQ_API_KEY and .venv-eval (requirements-eval.txt).
# Mandatory before a public tag; CI runs the same live gate when the secret exists.
evals-live: $(PY)
	./scripts/live-evals.sh

# Offline corpus-v0 smoke loop. Uses a scratch DB (citebench_v0) so it never
# wipes the big freeze. Never fetches documents (CITEBENCH_SNAPSHOT_ONLY=1).
smoke: $(PY)
	@$(COMPOSE) exec -T db psql -U citebench -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='citebench_v0'" | grep -q 1 || \
		$(COMPOSE) exec -T db createdb -U citebench citebench_v0
	CITEBENCH_MANIFEST=corpus/v0/MANIFEST.md \
	CITEBENCH_SNAPSHOT_ONLY=1 \
	CITEBENCH_ALLOW_WIPE=1 \
	DATABASE_URL=postgresql://citebench:citebench@127.0.0.1:5432/citebench_v0 \
	$(PY) scripts/smoke.py

test: $(PY)
	cd apps/api && $(CURDIR)/$(PY) -m pytest

mcp-smoke: $(PY)
	PYTHONPATH=. CITEBENCH_API_URL=$(API) $(PY) -m citebench.mcp --smoke
