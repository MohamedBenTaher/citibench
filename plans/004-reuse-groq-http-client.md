# Plan 004: Reuse Groq HTTP client and tiktoken encoding

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 85d12a0..HEAD -- apps/api/chat.py apps/api/generate.py apps/api/tests/test_chat.py apps/api/tests/test_generate.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: perf
- **Planned at**: commit `85d12a0`, 2026-09-07

## Why this matters

Every `groq_chat()` opens a new `httpx.Client` (TLS handshake) for one POST, then closes it. Playground asks are latency-sensitive; Groq chat dominates, but handshake + client setup is free waste on every generate that does not abstain at retrieve.

`estimate_embed_tokens` in `generate.py` calls `tiktoken.get_encoding(tokenizer)` on every generate (including abstain). Encoding load is cached inside tiktoken in practice, but Citebench should hold the encoding in-process next to the other process-global caches (`embed._local_model`, `rerank._ranker`).

Do **not** compile LangGraph once in this plan: `generate()` closes over a per-request `stage_sink`. A module-level `compile()` without contextvars would mix traces. Graph compile is negligible vs Groq.

## Current state

- `apps/api/chat.py` `groq_chat`:

```python
with httpx.Client(timeout=httpx.Timeout(60.0, connect=15.0)) as client:
    for model in models:
        try:
            return _post_chat(client, url, headers, messages, model, temperature)
```

- `apps/api/tests/test_chat.py` patches `httpx.Client` via `monkeypatch.setattr(chat.httpx, "Client", lambda **_kwargs: fake)` (same pattern as `test_embed.py`).
- `apps/api/generate.py`:

```python
def _count_tokens(text: str, tokenizer: str) -> int:
    encoding = tiktoken.get_encoding(tokenizer)
    return len(encoding.encode(text))
```

**Conventions**: `ChatError` for HTTP failures; 401 vs 5xx mapping in `main.py` `_runtime_http_error`. Timeouts: 60s read, 15s connect. `response_format: json_object` must stay.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Chat + generate tests | `.venv/bin/python -m pytest apps/api/tests/test_chat.py apps/api/tests/test_generate.py -q` | all pass |
| Full API suite | `.venv/bin/python -m pytest apps/api -q` | all pass |

## Scope

**In scope**:

- `apps/api/chat.py`
- `apps/api/generate.py` (`_count_tokens` only)
- `apps/api/tests/test_chat.py`
- `apps/api/tests/test_generate.py` only if a constructor/import breaks
- `plans/README.md` status row

**Out of scope**:

- Rewriting LangGraph / `StateGraph`
- `embed.py` httpx client (plan 001 should skip Groq embed by default)
- Changing retry counts (5) or backoff
- Streaming completions

## Git workflow

- Branch: `advisor/004-reuse-groq-http-client`
- Commit message: `Reuse a process-wide Groq HTTP client and cache the tiktoken encoding.`
- Do NOT push unless asked.

## Steps

### Step 1: Process-wide httpx client in chat.py

Add a module-level lock + client, plus reset for tests (mirror `embed.reset_embed_cache`):

```python
from threading import Lock

_http_lock = Lock()
_http_client: httpx.Client | None = None

def reset_http_client() -> None:
    global _http_client
    with _http_lock:
        if _http_client is not None:
            _http_client.close()
        _http_client = None

def _get_http_client() -> httpx.Client:
    global _http_client
    with _http_lock:
        if _http_client is None:
            _http_client = httpx.Client(timeout=httpx.Timeout(60.0, connect=15.0))
        return _http_client
```

`groq_chat` uses `_get_http_client()` **without** a `with` that closes the client after one request.

Keep the per-call retry loop inside `_post_chat`.

**Verify**: existing chat tests will fail until step 2 because they patch `httpx.Client` and expect the constructor to run every call.

### Step 2: Update tests

In `apps/api/tests/test_chat.py`:

1. Call `chat.reset_http_client()` at the start of each test that fakes HTTP (or an autouse fixture in that file).
2. Patch `_get_http_client` to return the existing `_FakeClient` **or** patch `httpx.Client` then call `reset_http_client()` so the next `_get_http_client()` uses the fake constructor.

Preferred: `monkeypatch.setattr(chat, "_get_http_client", lambda: fake)` so fakes stay context-manager-shaped. `_FakeClient` already implements `__enter__`/`__exit__`/`post`. `_get_http_client` should return an object with `.post(...)` only — `__enter__` is unused. `_FakeClient.post` already matches.

Add a test `test_groq_chat_reuses_client` that:
- Uses a fake whose `post` succeeds
- Calls `groq_chat` twice
- Asserts the same fake received two `post`s (models list length 2) and `httpx.Client` was constructed at most once if you still wrap a real constructor.

**Verify**: `.venv/bin/python -m pytest apps/api/tests/test_chat.py -q`

### Step 3: Cache tiktoken encoding

In `generate.py`, cache encodings:

```python
_encoding_lock = Lock()
_encodings: dict[str, Any] = {}

def _count_tokens(text: str, tokenizer: str) -> int:
    encoding = _get_encoding(tokenizer)
    return len(encoding.encode(text))
```

`_get_encoding` calls `tiktoken.get_encoding` once per tokenizer name.

Do not change `estimate_embed_tokens` formula (prefix + query, skip empty).

Add a tiny test in `test_generate.py`: `estimate_embed_tokens` still counts prefix tokens (there may already be a cost test — keep those passing). Optional: monkeypatch `tiktoken.get_encoding` to count calls — two `estimate_embed_tokens` with same tokenizer → one `get_encoding` call.

**Verify**: `.venv/bin/python -m pytest apps/api/tests/test_generate.py -q`

### Step 4: Full suite

```bash
.venv/bin/python -m pytest apps/api -q
```

## Test plan

- Chat 404 model fallback still tries `openai/gpt-oss-20b` (`test_chat.py` existing).
- New: two `groq_chat` calls share one client (fake).
- Generate cost / abstain tests unchanged.
- Pattern: `_FakeClient` in `test_chat.py`.

## Done criteria

- [ ] `groq_chat` does not `with httpx.Client(...)` per call
- [ ] `reset_http_client()` exists and tests use it
- [ ] tiktoken encoding loaded at most once per tokenizer name per process
- [ ] `.venv/bin/python -m pytest apps/api` exits 0
- [ ] LangGraph code in `generate.py` otherwise untouched
- [ ] `plans/README.md` row 004 is DONE

## STOP conditions

- httpx client reuse appears to share headers/cookies incorrectly across keys — Citebench has one `GROQ_API_KEY` per process; if you add multi-tenant keys, stop and report rather than a thread-local map.
- Tests cannot patch the client without rewriting `_post_chat` — keep `_post_chat(client, ...)` injectable.
- You start converting `groq_chat` to `httpx.AsyncClient` and FastAPI `async def` — out of scope (sync endpoints stay).

## Maintenance notes

- Reviewers: connection reuse vs Groq keep-alive; timeouts must remain 60s.
- If the process is long-lived, rare Groq IP changes are handled by httpx connection pooling already.
- Closing the client on shutdown is optional; uvicorn process exit is enough. Do not add atexit unless tests leak fds (then close in `reset_http_client` only).
