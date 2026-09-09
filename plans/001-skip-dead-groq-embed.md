# Plan 001: Skip Groq for embeddings (local ONNX by default)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 85d12a0..HEAD -- config.yaml apps/api/embed.py apps/api/settings.py apps/api/tests/test_embed.py apps/api/tests/test_settings.py DECISIONS.md .env.example README.md`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: perf
- **Planned at**: commit `85d12a0`, 2026-09-07

## Why this matters

Groq **no longer hosts** `nomic-embed-text-v1.5`. Citebench already falls back to local ONNX via fastembed after a `model_not_found` / 404. That fallback is correct and is **not** a second billed embed provider.

The waste: every API process that has `GROQ_API_KEY` still POSTs Groq `/embeddings` on the first ingest or retrieve until `_groq_model_missing` is set. That is one or two HTTP round trips (model id plus underscore alias) before ONNX runs. Playground generate always has a Groq key (chat requires it), so **every container restart** pays this tax on the first ask and on ingest.

Defaulting embeddings to local ONNX removes that dead probe. Keep an explicit `groq_then_local` mode so the existing 404-fallback tests and DECISIONS story remain true.

## Current state

- `config.yaml` — knobs for models and retrieve. Comments already say Groq 404s the embed model.
- `apps/api/settings.py` — `load_settings()` reads yaml + env into frozen `Settings`. There is **no** embed-backend field today.
- `apps/api/embed.py` — `embed_texts` tries Groq whenever `settings.groq_api_key` is set and `_groq_model_missing` is false.
- `apps/api/tests/test_embed.py` — covers payload shape, query prefix, Groq 404 → local, custom host 404 does **not** fallback, empty key → local.
- `DECISIONS.md` C2 ingest binding (2026-09-06): Groq embeddings removed; try Groq then local ONNX.

Excerpt from `apps/api/embed.py` (hot path):

```python
prefixed = [used_prefix + text for text in texts]
if settings.groq_api_key and not _groq_model_missing:
    try:
        return _embed_via_groq(prefixed, settings, batch_size=batch_size)
    except EmbedError as exc:
        if _should_fallback_local(exc, settings):
            # ... mark missing, then fall through to local
        else:
            raise
return _embed_local(...)
```

Excerpt from `config.yaml`:

```yaml
embed_model: nomic-embed-text-v1.5
# Same 768-d nomic weights. Groq hosted them, then 404'd (model_not_found).
# Ingest/retrieve try Groq /embeddings, then local ONNX via fastembed.
```

**Conventions to match**:

- Frozen `Settings` dataclass in `apps/api/settings.py`; env overrides use `os.environ.get` next to yaml keys (see `GROQ_CHAT_MODEL`, `ABSTAIN_MIN_SCORE`).
- Tests build `Settings(...)` with many required fields — copy `_settings()` in `test_embed.py` / `make_settings()` in `test_generate.py`.
- Comments must not describe this as a second embed vendor.

**Product constraint** (from `DECISIONS.md`): Groq is the sole *generation* provider. Embeddings stay the same open `nomic-embed-text-v1.5` weights. Do not add OpenAI/Voyage/etc.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| API tests | `.venv/bin/python -m pytest apps/api/tests/test_embed.py apps/api/tests/test_settings.py -q` | all pass |
| Full API suite | `.venv/bin/python -m pytest apps/api -q` | all pass |

If `.venv` is missing: `make setup` first (creates venv, installs `apps/api/requirements-dev.txt`). Do not use system `pytest`.

## Scope

**In scope**:

- `config.yaml`
- `apps/api/settings.py`
- `apps/api/embed.py`
- `apps/api/tests/test_embed.py`
- `apps/api/tests/test_settings.py`
- `DECISIONS.md` (one short sentence in the C2 embed paragraph)
- `.env.example` (optional one-line comment for the new env var)
- `README.md` only if the ingest paragraph still says “tries Groq `/embeddings` first” as the default — update that sentence to match the new default
- `plans/README.md` status row

**Out of scope**:

- `apps/api/chat.py` / Groq chat fallbacks
- FlashRank, retrieve RRF knobs, `top_k`
- Dockerfiles, Compose volumes
- Plan 003 warmup (do not add lifespan loading here)
- Any new billed embed HTTP API

## Git workflow

- Branch: `advisor/001-skip-dead-groq-embed`
- Commit message style (imperative, like `Fall back to local nomic embeddings when Groq 404s the model.`):

  `Skip Groq embeddings by default and go straight to local nomic ONNX.`

- Do NOT push or open a PR unless asked.

## Steps

### Step 1: Add `embed_backend` to config and Settings

In `config.yaml`, add (next to the existing embed comments):

```yaml
# local = ONNX via fastembed (default). groq_then_local = historical probe
# for hosted nomic (Groq 404s; kept for tests / rollback).
embed_backend: local
```

In `apps/api/settings.py`:

1. Add field `embed_backend: str = "local"` on `Settings`.
2. In `load_settings()`, set it from `os.environ.get("EMBED_BACKEND")` or `raw.get("embed_backend")` or `"local"`.
3. Normalize to lowercase stripped string.
4. If the value is not `local` or `groq_then_local`, raise `ValueError` with those two allowed names (fail closed at process start, not mid-request).

**Verify**: `.venv/bin/python -c "from apps.api.settings import load_settings"` will fail because `apps.api` is not a package. Instead, from `apps/api`:

```bash
cd apps/api && ../../.venv/bin/python -c "from settings import load_settings; s=load_settings(); print(s.embed_backend)"
```

Expected: prints `local`. Then `cd` back to repo root.

### Step 2: Gate Groq embed on backend

In `apps/api/embed.py` `embed_texts`, change the Groq branch condition from:

`if settings.groq_api_key and not _groq_model_missing:`

to:

`if settings.embed_backend == "groq_then_local" and settings.groq_api_key and not _groq_model_missing:`

Keep `_should_fallback_local`, `_mark_groq_missing`, and `_embed_via_groq` unchanged.

Use an exhaustive check if you branch on backend elsewhere:

```python
backend = settings.embed_backend
if backend == "groq_then_local":
    ...
elif backend == "local":
    return _embed_local(...)
else:
    raise ValueError(f"unknown embed_backend: {backend}")
```

If `embed_texts` only uses the `if groq_then_local` then fallthrough to local, that is enough (unknown values already rejected in `load_settings`). Direct `Settings(...)` in tests may still pass a bad string — `embed_texts` should treat anything other than `groq_then_local` as local **or** raise. Prefer **raise** `EmbedError` on unknown backend so tests catch typos.

**Verify**: `.venv/bin/python -m pytest apps/api/tests/test_embed.py::test_no_groq_key_uses_local -q` still passes.

### Step 3: Tests

In `apps/api/tests/test_embed.py`:

1. Add `embed_backend: str = "groq_then_local"` to `_settings()` **default** so existing Groq 404 tests keep probing Groq without repeating the field. Tests that construct `Settings` without `_settings()` must still compile — `Settings` default `embed_backend="local"` covers `test_embed_query_uses_search_query_prefix` if that constructor is updated.

   Simplest: add `embed_backend="local"` as dataclass default (step 1). Then in `_settings()` pass `embed_backend="groq_then_local"` so `test_groq_model_not_found_falls_back_to_local` still hits Groq.

2. New test `test_local_backend_skips_groq_even_when_key_present`:
   - `embed.reset_embed_cache()`
   - `_settings(embed_backend="local")` with a non-empty `groq_api_key`
   - Monkeypatch `httpx.Client` to a client whose `post` raises `AssertionError("groq must not be called")` **or** monkeypatch `_embed_via_groq` to raise
   - Monkeypatch `_embed_local` to return a 768-d vector
   - `embed_texts(["hello"], settings)` returns that vector and Groq is not called

3. Keep `test_groq_model_not_found_falls_back_to_local` using `embed_backend="groq_then_local"`.

In `apps/api/tests/test_settings.py`:

- `test_load_settings_binds_groq_chat_model`: assert `settings.embed_backend == "local"`.

Any other test that instantiates full `Settings(...)` without the new field: dataclass default `"local"` means they keep compiling.

**Verify**:

```bash
.venv/bin/python -m pytest apps/api/tests/test_embed.py apps/api/tests/test_settings.py -q
```

All pass, including the new skip-Groq test.

### Step 4: Docs (minimal)

- `DECISIONS.md` C2 paragraph that currently says ingest/retrieve “try Groq, then fall back”: add that the **default** `embed_backend` is `local`; `groq_then_local` remains the probe path.
- README ingest sentence that says Groq is tried first: say local ONNX is default; Groq embed probe is opt-in.
- `.env.example`: comment `# EMBED_BACKEND=local` (and that `groq_then_local` restores the old probe). Do not put secret values.

**Verify**: `rg -n "try Groq" README.md DECISIONS.md` — remaining hits must not claim Groq-first is the default.

### Step 5: Full suite

```bash
.venv/bin/python -m pytest apps/api -q
```

Expected: all pass.

## Test plan

- New: local backend + Groq key present → no Groq HTTP (see step 3).
- Existing: Groq 404 fallback (`test_groq_model_not_found_falls_back_to_local`) still with `groq_then_local`.
- Existing: custom embed host 404 does not fallback (`test_custom_embed_host_404_does_not_fallback`) — still `groq_then_local` + non-groq base.
- Pattern: `apps/api/tests/test_embed.py` fakes (`_FakeClient`, `_FakeResponse`).

## Done criteria

- [ ] `embed_backend: local` in `config.yaml`; `load_settings().embed_backend == "local"`
- [ ] Default `embed_texts` with a Groq key does not call `_embed_via_groq`
- [ ] `groq_then_local` still 404-falls-back in tests
- [ ] `.venv/bin/python -m pytest apps/api` exits 0
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row for 001 is DONE

## STOP conditions

- `Settings` construction in tests fails across many files because the new field was required without a default — add a default instead of editing every test.
- You think you need a new embed HTTP vendor — stop; that violates DECISIONS.
- `fastembed` import path or `_LOCAL_NOMIC` id would need to change to make local work — stop; that is a different incident (weights), not this plan.

## Maintenance notes

- If Groq ever hosts nomic again, flipping `EMBED_BACKEND=groq_then_local` restores the probe without a code change.
- Reviewers should confirm Playground still requires `GROQ_API_KEY` for **chat** (`POST /generate` 503 without key).
- Plan 003 will load ONNX at startup and must not reintroduce a Groq embed POST.
