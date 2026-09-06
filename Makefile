# Citebench local environment.
#   make setup   — .env + Python venv + API/eval deps
#   make start   — Compose (api, web, Postgres/pgvector)
#   make ingest  — index the frozen 14-doc corpus (needs GROQ_API_KEY)

PYTHON  ?= python3
COMPOSE ?= docker compose
WEB_PORT ?= 3000
API     ?= http://127.0.0.1:8000
WEB     ?= http://127.0.0.1:$(WEB_PORT)
VENV    := .venv
PY      := $(VENV)/bin/python

.PHONY: help setup start up stop down logs status ingest evals test mcp-smoke

help:
	@echo "Citebench"
	@echo
	@echo "  make setup      copy .env.example → .env, create .venv, install deps"
	@echo "  make start      docker compose up --build (api :8000, TanStack Start web :$(WEB_PORT), db)"
	@echo "  make ingest     POST /ingest (requires GROQ_API_KEY in .env)"
	@echo "  make evals      pytest + mock RAGAS + mock redteam (local, before provision)"
	@echo "  make test       pytest only (uses .venv)"
	@echo "  make status     health + corpus stats"
	@echo "  make logs       follow Compose logs"
	@echo "  make stop       docker compose stop"
	@echo "  make down       docker compose down"
	@echo "  make mcp-smoke  protocol-only MCP smoke (no stack)"
	@echo
	@echo "After setup, put GROQ_API_KEY in .env (https://console.groq.com/keys)."

setup: .env $(PY)
	$(PY) -m pip install -q -U pip
	$(PY) -m pip install -q -r apps/api/requirements-dev.txt
	@echo
	@echo "Setup done. Next:"
	@echo "  1. Set GROQ_API_KEY in .env"
	@echo "  2. make start"
	@echo "  3. make ingest"
	@echo "  4. open $(WEB)/  (index)  $(WEB)/evals  (scores, not a chat homepage)"

.env:
	cp .env.example .env
	@echo "Wrote .env from .env.example — add GROQ_API_KEY before ingest/retrieve/generate."

$(PY):
	$(PYTHON) -m venv $(VENV)

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
	@echo "Tabs $(WEB)/corpus  $(WEB)/playground  $(WEB)/traces  $(WEB)/evals"

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

test: $(PY)
	$(PY) -m pip install -q -r apps/api/requirements-dev.txt
	cd apps/api && $(CURDIR)/$(PY) -m pytest

mcp-smoke: $(PY)
	PYTHONPATH=. CITEBENCH_API_URL=$(API) $(PY) -m citebench.mcp --smoke
