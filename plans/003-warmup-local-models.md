# Plan 003: Warm local embed + rerank models in API lifespan

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 85d12a0..HEAD -- apps/api/main.py apps/api/embed.py apps/api/rerank.py apps/api/tests/conftest.py docker-compose.yml`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: MED
- **Depends on**: plans/001-skip-dead-groq-embed.md (warmup must not POST Groq `/embeddings`)
- **Category**: perf
- **Planned at**: commit `85d12a0`, 2026-09-07

## Why this matters

The first Playground ask after `docker compose up` loads:

1. nomic-embed-text-v1.5 ONNX via fastembed (`TextEmbedding(...)` in `embed._load_local_model`)
2. FlashRank `ms-marco-MiniLM-L-12-v2` (`rerank.load_ranker`)

Those loads are process-global (locks + caches already exist) but they happen **inside** `/retrieve` or `/generate`, so p95 of the first trace is model-load time plus Groq chat. Compose persists nomic weights in volume `citebench_nomic` (`NOMIC_CACHE_DIR=/tmp/nomic-embed`) but **does not** persist FlashRank: `FLASHRANK_CACHE_DIR` defaults to `/tmp/flashrank` with no named volume (`docker-compose.yml` api environment + volumes). Container recreate re-downloads MiniLM even when nomic survives. Warming in FastAPI lifespan plus a FlashRank volume moves download/load off the first user question.

CI pytest uses `TestClient` / imports `main` in some tests. Loading 0.5 GB of weights in GitHub Actions is unacceptable. Warmup must be skippable.

## Current state

- `apps/api/main.py` lifespan:

```python
@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = load_settings()
    try:
        with connect(settings.database_url) as conn:
            ensure_schema(conn)
    except Exception as exc:
        log.warning("database schema not ready at startup: %s", exc)
    yield
```

- `apps/api/embed.py` — `_load_local_model()` under `_lock`; `reset_embed_cache()` for tests.
- `apps/api/rerank.py` — `load_ranker(model_name)` under `_lock`; `reset_ranker_cache()`.
- `apps/api/tests/conftest.py` — autouse trace isolation only; no model skip flag.
- Compose: `NOMIC_CACHE_DIR`, `FLASHRANK_CACHE_DIR` on the `api` service.

**Conventions**: log with `logging.getLogger("citebench.*")`. Soft-fail DB at startup already (warning, continue). Match that for model warmup: log warning, do not crash the API if weights are missing — `/health` must still return ok so `make start` does not hang forever. First ask can still lazy-load.

**Product constraint**: do not add a second reranker or embed vendor. Warm **exactly** `nomic-ai/nomic-embed-text-v1.5` and `ms-marco-MiniLM-L-12-v2` (or `settings.rerank_model` / local nomic constant already in code).

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Tests without downloads | `.venv/bin/python -m pytest apps/api -q` | all pass; no network fetch of ONNX |
| Health still boots | (manual Compose, optional) `curl -sf localhost:8000/health` | `{"status":"ok"}` |

## Scope

**In scope**:

- `apps/api/main.py` (lifespan)
- `apps/api/embed.py` (optional public `warmup_local_embed()` wrapping `_load_local_model`)
- `apps/api/rerank.py` (optional public `warmup_ranker(model_name)`)
- `apps/api/tests/conftest.py` (set skip env for pytest)
- `apps/api/tests/test_settings.py` or a new `apps/api/tests/test_warmup.py` (unit tests that warmup is skipped)
- `docker-compose.yml` — add named volume for FlashRank (required). Do **not** set `CITEBENCH_SKIP_MODEL_WARMUP` on the `api` service (warmup should run in Compose).
- `.env.example` one comment for the skip flag
- `plans/README.md` status row

**Out of scope**:

- Changing FlashRank model id or nomic model id
- Uvicorn workers
- Pre-baking ONNX into the Docker image (image size / legal); named volumes are the cache
- Web UI “warming” spinner
- `infra/deploy/docker-compose.demo.yml` unless it copies the api volume list — if it does, add the same FlashRank volume there too; if it only overlays Caddy, leave it.

## Git workflow

- Branch: `advisor/003-warmup-local-models`
- Commit message: `Warm nomic and FlashRank at API startup so the first ask is not a model download.`
- Do NOT push unless asked.

## Steps

### Step 1: Skip flag

Define env `CITEBENCH_SKIP_MODEL_WARMUP`. Treat as skip when value is `1`, `true`, `yes` (case-insensitive) **or** when `PYTEST_CURRENT_TEST` is set.

In `apps/api/tests/conftest.py` autouse fixture (existing `isolate_trace_store`), also `monkeypatch.setenv("CITEBENCH_SKIP_MODEL_WARMUP", "1")` so any TestClient lifespan cannot download models even if pytest’s env var is missing on an older pytest.

**Verify**: after step 2, pytest still does not call `_load_local_model` for real. Add a test that monkeypatches lifespan helpers.

### Step 2: Warmup helpers

In `embed.py`, add:

```python
def warmup_local_embed() -> None:
    _load_local_model()
```

In `rerank.py`, add:

```python
def warmup_ranker(model_name: str = DEFAULT_RERANK_MODEL) -> None:
    load_ranker(model_name)
```

Do not call Groq. Do not require `GROQ_API_KEY`.

**Verify**: `rg -n "warmup_local_embed|_embed_via_groq" apps/api/embed.py apps/api/main.py` — warmup path must not reference Groq.

### Step 3: Lifespan

After schema ensure (success or warning), if not skip:

```python
try:
    warmup_local_embed()
    warmup_ranker(settings.rerank_model)
    log.info("local embed and rerank models ready")
except Exception as exc:
    log.warning("model warmup skipped or failed: %s", exc)
```

Keep `/health` independent (already no DB check).

Do **not** make lifespan `async` CPU-bound without care: `_load_local_model` is sync and blocking. FastAPI lifespan can call it directly (startup is allowed to block). Do not `asyncio.to_thread` unless you already understand the running loop — blocking startup is the point.

**Verify**: unit test `test_warmup_skipped_when_env_set` that imports the skip predicate and asserts True when env is `1`. Optional: call a extracted `maybe_warmup(settings)` with monkeypatched warmup functions that record calls — 0 calls when skip, 2 calls when not skip.

Do **not** run real `TextEmbedding()` in pytest.

### Step 4: Persist FlashRank cache in Compose

In `docker-compose.yml` on the `api` service, mirror nomic:

- Keep `FLASHRANK_CACHE_DIR` at `/tmp/flashrank` (or `${FLASHRANK_CACHE_DIR:-/tmp/flashrank}`).
- Add volume `citebench_flashrank:/tmp/flashrank` next to `citebench_nomic:/tmp/nomic-embed`.
- Declare `citebench_flashrank:` under top-level `volumes:` beside `citebench_nomic`.

Do not change Postgres publish ports or passwords in this step.

**Verify**: `rg -n "flashrank" docker-compose.yml` shows both the env dir and a named volume mount. `rg -n "citebench_nomic" docker-compose.yml` still has the nomic volume.

### Step 5: Full suite

```bash
.venv/bin/python -m pytest apps/api -q
```

Expected: all pass; duration similar to before (no extra minutes). If pytest hangs or downloads, STOP — skip flag is not working.

## Test plan

- Skip env / pytest: warmup functions not invoked (monkeypatch).
- Non-skip: `maybe_warmup` calls both helpers once (monkeypatch, no real models).
- Pattern: `apps/api/tests/test_rerank.py` / `test_embed.py` cache resets.

## Done criteria

- [ ] Lifespan warms nomic + FlashRank when skip is unset
- [ ] `docker-compose.yml` has named volume `citebench_flashrank` mounted on `FLASHRANK_CACHE_DIR`
- [ ] Pytest sets skip; CI cannot download ONNX as part of this change
- [ ] Warmup never calls Groq embeddings
- [ ] `.venv/bin/python -m pytest apps/api` exits 0
- [ ] `/health` still does not require models
- [ ] `plans/README.md` row 003 is DONE

## STOP conditions

- GitHub Actions job time jumps because weights download — revert warmup in CI path immediately.
- `load_ranker` / `TextEmbedding` APIs do not match the excerpts (FlashRank constructor changed) — stop and report; do not pin a different model.
- You want to COPY models into `apps/api/Dockerfile` — out of scope.

## Maintenance notes

- First Compose boot without the nomic volume still downloads during **startup**, not during the first `/generate`. `make start` waits on `/health`, which does **not** wait for warmup to finish if warmup runs after health is already serving — **order the code so warmup completes before `yield`**. That way uvicorn does not accept traffic until models are loaded (or warmup failed-soft). Confirm: FastAPI lifespan runs before serving requests; keep warmup **before** `yield`.
- Reviewers: failed warmup must not crash a laptop that lacks disk for ONNX; warning + lazy load is correct.
- Two uvicorn workers would warm twice (RAM). Do not add `--workers` here.
