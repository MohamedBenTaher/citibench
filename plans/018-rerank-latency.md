# Plan 018: Prove rerank integrity and measure retrieve latency at scale

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**:
> `git diff --stat 028fa3e..HEAD -- apps/api/retrieve.py apps/api/rerank.py apps/api/tests/test_retrieve.py apps/api/tests/test_rerank.py apps/api/metrics.py README.md`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: LOW (tests + measurement; no pipeline rewrite)
- **Depends on**: plan 013 (big corpus ingested)
- **Category**: direction (I2 / R2)
- **Planned at**: commit `028fa3e`, 2026-09-10

## Why this matters

Two claims must be *provable* once the corpus is ~10k chunks: (1) a FlashRank
failure is never silent — every hit and the `RunTrace` say `rerank_skipped=true`;
(2) retrieval is still fast enough that adding an ANN index is not yet justified.
`DECISIONS.md` already argues against HNSW at 148 chunks; this plan re-checks
that at scale and records the number, so the "no ANN yet" decision stays honest.

RRF and FlashRank stay exactly as they are.

## Current state

- `retrieve.py:201-230` sets the flag on failure and keeps RRF order:
  ```python
  try:
      rerank_scores = [float(score) for score in rank_fn(query_text, pool)]
      ...
  except Exception as exc:
      rerank_skipped = True
      rerank_status = "error"; rerank_error = str(exc)
      log.warning("FlashRank failed; falling back to RRF order: %s", exc)
  ```
  Skip hits get `score=item.fused_score`, `rerank_score=None`, `skipped=True`
  (`:216-220`); per-hit flag in `_to_hit` (`:326-345`); span attrs include
  `rerank_skipped` (`:246-262`).
- `rerank.py:55-76` `flashrank_rerank` raises `RerankError` if FlashRank omits an
  input index; `retrieve` owns the fallback.
- `generate.py:178-184` `retrieve_abstain_reason` skips `low_confidence` when all
  hits are `rerank_skipped`; `_rerank_skipped` (`:614-624`) resolves the run flag.
- `trace.py` `RunTrace.rerank_skipped` (`:104-125`) and `validate_run_trace`
  (`:171-211`) require the flag to match.
- `metrics.py` `p95` (`:90-105`, `:124-125`) is over `RunTrace.latency_ms`, not
  retrieve-only; there is no retrieve-stage benchmark script today.
- Tests: `test_retrieve.py`, `test_rerank.py` exist; use injected `RerankFn`.

**Conventions**: injected fakes via the `*_fn` keyword args; never require a live
DB in unit tests. Bench numbers carry a method tag and are never hand-typed.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| API tests | `.venv/bin/python -m pytest apps/api` | all pass |
| Bench | `.venv/bin/python scripts/bench-retrieve.py --n 50` | writes `evals/results/retrieve-bench.json` |
| Corpus size | `curl -sS localhost:8000/corpus/stats` | `chunk_count` |
| Manual rerank | (unit test) force `RerankFn` raising | all hits `rerank_skipped` |

## Scope

**In scope**:

- `apps/api/tests/test_retrieve.py` — forced-rerank-failure regression.
- `apps/api/tests/test_generate.py` — runaway/trace flag consistency when skipped.
- `scripts/bench-retrieve.py` (**create**) — retrieve-only latency at scale.
- `evals/results/retrieve-bench.json` (**create**).
- `README.md` / `DECISIONS.md` — record the measured retrieve latency and the ANN decision.
- `plans/README.md` status row.

**Out of scope**:

- Adding an ANN index (HNSW/IVFFlat) — only if the bench justifies it, and then
  as a **new** plan with explicit approval; do not do it here.
- Changing `top_k`, RRF `k`, or the rerank model.
- Retrieving user docs (plan 020).
- A load-testing framework.

## Git workflow

- Branch: `advisor/018-rerank-latency`
- Commit message: `Prove rerank skip visibility and measure retrieve latency.`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Forced-rerank-failure regression test

In `apps/api/tests/test_retrieve.py`, add a test that calls `retrieve()` with an
injected `rerank_fn` that raises `RerankError` (or any exception) and injected
search fns returning a fixed pool. Assert:
- every returned `ChunkHit.rerank_skipped is True`,
- order equals the RRF order truncated to `top_k`,
- `score` equals `fused_score`,
- the rerank stage event has `rerank_skipped=True` and `status="error"`.

Also add a `test_generate.py` case: with a fully-skipped retrieve, the run trace's
`rerank_skipped` is `True` and the abstain reason is `empty_retrieve` (if empty)
or a normal generate/low-confidence skip — **not** `low_confidence` (since scores
are on the RRF scale).

**Verify**: `.venv/bin/python -m pytest apps/api/tests/test_retrieve.py apps/api/tests/test_generate.py apps/api/tests/test_trace.py` → pass.

### Step 2: Bench script

Create `scripts/bench-retrieve.py`:
- Loads `Settings`, connects to Postgres, and calls `retrieve()` directly
  (import from `apps/api`) for `--n` queries drawn from `evals/splits/ci.jsonl`
  questions (cycling).
- Warm up once (models + connection), then time each call with
  `time.perf_counter()`.
- Report `n`, `chunk_count` (from `corpus_stats`), `mean_ms`, `p50_ms`, `p95_ms`,
  and the retrieval config (`top_k`, `dense_k`, `lexical_k`, `rerank_pool`).
- Write `evals/results/retrieve-bench.json` with `measured_at`,
  `measured_under=f"retrieve-bench-{date}"`, `n`, corpus `chunk_count`, and the
  latency stats. No invented values; if the DB is empty, exit non-zero.

**Verify**: `.venv/bin/python scripts/bench-retrieve.py --n 50` → writes the JSON;
`python -c "import json;print(json.load(open('evals/results/retrieve-bench.json')))"`.

### Step 3: Decide on ANN (do not implement)

Compare `p95_ms` against a stated budget (suggest: p95 < 400 ms on the dev laptop
is fine; record the actual number). Append a `DECISIONS.md` note and a README line
with the measured latency + chunk count + method tag. If p95 exceeds the budget,
**stop and report** — propose HNSW as a separate plan; do not add it now.

**Verify**: `git diff DECISIONS.md README.md` shows measured values only.

## Test plan

- `test_retrieve.py`: forced rerank failure → all hits skipped, RRF order, span flag.
- `test_generate.py`: skipped retrieve does not trigger `low_confidence`; trace flag matches.
- `test_rerank.py`: unchanged (raises on partial scores).
- Bench is manual (needs DB), not CI.
- Verification: `.venv/bin/python -m pytest apps/api` → all pass.

## Done criteria

- [ ] Forced-rerank-failure test exists and passes; no silent skip path remains.
- [ ] `scripts/bench-retrieve.py` writes `retrieve-bench.json` with real stats and tag.
- [ ] README/DECISIONS record retrieve p50/p95 + `chunk_count` + method tag, or a
      STOP report proposing ANN.
- [ ] RRF/FlashRank/top_k unchanged.
- [ ] `pytest apps/api` exits 0.
- [ ] `plans/README.md` row 018 is DONE.

## STOP conditions

- The bench shows p95 over budget — stop; ANN is a separate, approved plan.
- A rerank failure can still produce hits with `rerank_skipped=False` — stop; that
  is a contract violation the plan exists to prevent.
- The bench needs a live Groq key (it should not) — stop; retrieve is local.
- `retrieve-bench.json` would need hand-edited numbers — stop.

## Maintenance notes

- Plan 017 filters can change pool sizes; re-run the bench after filters land if
  latency shifts.
- Plan 019 rewrite adds an optional LLM call **before** retrieve; time it
  separately and do not fold it into retrieve latency.
- Reviewers: confirm the bench JSON tag/date and that the forced-failure test
  actually raises.
- Deferred: ANN index, quantization (plan 008.2).
