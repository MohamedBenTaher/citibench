# Plan 023: Make rerank fit the retrieve latency budget

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**:
> `git diff --stat 07f7a46..HEAD -- apps/api/rerank.py apps/api/retrieve.py apps/api/tests/test_rerank.py scripts/bench-retrieve.py citebench/eval/retrieval.py README.md DECISIONS.md`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MEDIUM (changes retrieval latency *and* possibly quality)
- **Depends on**: plan 013 (big freeze), plan 018 (measurement)
- **Category**: direction (I2 / R2 follow-up)
- **Planned at**: commit `07f7a46`, 2026-09-13

## Why this matters

Plan 018 measured retrieve latency on the frozen corpus and hit its STOP
condition: **p50 2401 ms / p95 2548 ms at 31,288 chunks**
(`evals/results/retrieve-bench.json`), ~6× the planned 400 ms budget. But the
stage breakdown shows the dense scan is only **~140 ms**; the **cross-encoder
(FlashRank `ms-marco-MiniLM-L-12-v2`, top-50 pool) is ~2180 ms** — ~86% of the
total. An ANN index would not fix this, so ANN stays deferred
(`DECISIONS.md` "Retrieve latency at scale"). This plan attacks the actual
bottleneck.

Hard constraint: this is a **bench**, so latency work must not silently trade
away retrieval quality. Every rerank change is gated on the committed qrels
(Recall@8 0.904 / MRR 0.616 / nDCG@8 0.692) via `citebench.eval.retrieval`.

## Current state

- `rerank.py:40-52` caches one `Ranker` per process; `flashrank_rerank`
  (`:55-76`) loads it once and scores the whole pool in one `ranker.rerank`
  call. So the cost is **inference**, not model load.
- `retrieve.py:259-294` fuses with RRF, takes `pool = fused[:cfg.rerank_pool]`
  (default 50), reranks, keeps `top_k=8`. `rerank_pool` and `rerank_enabled`
  are already `RetrieveConfig` knobs.
- `scripts/bench-retrieve.py` times full retrieve (n=50) and reports
  `stage_mean_ms` (embed/vector/fts/rerank). `--n` only; no per-variant knob.
- `citebench/eval/retrieval.py` evaluates a `RetrieveConfig` and `--compare`
  runs named variants (`hybrid+rerank`, `hybrid no rerank`, `dense only`,
  `lexical only`); none vary `rerank_pool`.
- `DECISIONS.md` allows off-the-shelf models only; no fine-tuning.

**Conventions**: injected fakes via `*_fn`; never require a live DB in unit
tests. Bench/eval numbers carry a method tag and are never hand-typed.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| API tests | `.venv/bin/python -m pytest apps/api` | all pass |
| Retrieve bench | `.venv/bin/python scripts/bench-retrieve.py --n 50` | writes `retrieve-bench.json` |
| Quality ablation | `.venv/bin/python -m citebench.eval.retrieval --compare` | prints per-variant Recall@8/MRR/nDCDF@8 |
| Corpus size | `curl -sS localhost:8000/corpus/stats` | `chunk_count` 31288 |

## Scope

**In scope**:

- `apps/api/rerank.py` — expose and tune inference knobs (e.g. `max_length`,
  onnxruntime thread count) and/or allow an alternate off-the-shelf rerank
  model; keep the one-Ranker-per-process cache and the `RerankError` contract.
- `apps/api/retrieve.py` / `RetrieveConfig` — if `rerank_pool` (or a
  `rerank_max_length`) becomes the chosen knob, make it config-driven and keep
  the default behavior reproducible.
- `citebench/eval/retrieval.py` — add qrels variants that vary `rerank_pool`
  (and model, if tried) so the ablation is committed and reproducible.
- `scripts/bench-retrieve.py` — option to bench a named config (so before/after
  is one command), still one artifact with a method tag.
- `evals/results/retrieve-bench.json` — the new measured numbers.
- `README.md` / `DECISIONS.md` — replace the "over budget" note with the result.
- `plans/README.md` status row.

**Out of scope**:

- ANN index (HNSW/IVFFlat) — explicitly deferred in `DECISIONS.md`; untouched.
- Changing RRF `k=60`, `top_k=8`, or the fusion algorithm.
- Fine-tuning any model; adding a second billed vendor.
- Retrieving user docs (plan 020).
- A load-testing framework.

## Git workflow

- Branch: `advisor/023-rerank-latency`
- Commit messages (one per logical change):
  `Bench rerank knobs against qrels.` then
  `Cut rerank cost within the quality gate.`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Make the knob measurable before changing it

1. Add a `--variant NAME=json` (or similar) option to
   `scripts/bench-retrieve.py` that benches a `RetrieveConfig` override,
   writing the same payload plus the variant label. Keep the default run
   identical to plan 018.
2. In `citebench/eval/retrieval.py`, add committed variants that vary
   `rerank_pool`: e.g. `hybrid+rerank pool=20`, `pool=10`. Model the new
   variants on the existing `run_variant` wiring.

**Verify**: `.venv/bin/python -m citebench.eval.retrieval --compare` prints the
new rows; `.venv/bin/python scripts/bench-retrieve.py --n 50` is unchanged on
the default config.

### Step 2: Measure the matrix, cheapest knob first

For each candidate, record **both** quality (`--compare`) and latency
(`bench --variant`):

1. **`max_length`**: FlashRank defaults to 512; our chunks are ~512 tokens.
   Try a smaller `max_length` (e.g. 256/128). Measure quality delta + rerank ms.
2. **Threads**: try `OMP_NUM_THREADS` / onnxruntime intra-op threads (document
   the laptop's core count). This changes no scores — latency only.
3. **`rerank_pool`**: 50 → 30 → 20 → 10. Fewer passages ≈ linear rerank cost.
4. **Alternate off-the-shelf model** (only if 1–3 miss budget): e.g. the
   6-layer `ms-marco-MiniLM-L-6-v2`. Must be re-benchmarked on the same qrels.

Prefer the change with the smallest quality delta that meets a budget; do not
stack changes until each is measured alone.

**Verify**: a small table (in the commit message or `DECISIONS.md` draft) with
one row per candidate: `variant | p50 | p95 | rerank_ms | Recall@8 | nDCG@8`.

### Step 3: Apply the winner, re-gate, re-bench

1. If `rerank_pool`/`max_length` wins, set the new default in
   `retrieve_config_from_settings` / `RetrieveConfig` (keep it overridable).
   If threads win, set them where the Ranker is constructed and document it.
2. Re-run the full qrels comparison and the bench.

**Quality gate** (STOP if unmet):

- Recall@8 ≥ **0.894** (0.904 − 0.01) and nDCG@8 ≥ **0.682** (0.692 − 0.01),
  else revert and report.
- `False-abstain` must stay **0.000** and `False-answer` must not exceed
  **0.250**.

**Latency target**: p95 < **400 ms**. If the best quality-safe candidate still
exceeds it, **stop and report** with the table and a proposed revised budget or
a bigger change (e.g. an int8/quantized ONNX rerank). Do not silently lower the
target.

**Verify**: `.venv/bin/python -m pytest apps/api` → all pass;
`.venv/bin/python scripts/bench-retrieve.py --n 50` → new `retrieve-bench.json`.

### Step 4: Record the decision

Update `README.md` (retrieve p50/p95 rows + method tag) and `DECISIONS.md`
(replace the "over budget" paragraph with the chosen knob, the quality delta,
and the new numbers). Then set plan 023's row to DONE in `plans/README.md`.

**Verify**: `git diff README.md DECISIONS.md` contains measured values only.

## Test plan

- `test_rerank.py`: unchanged contract (raises on partial scores); add a test
  that a configured `max_length`/model is passed through to `load_ranker`.
- `test_retrieve.py`: a `rerank_pool` override changes pool size (existing
  injected-fn tests already cover ordering; assert the pool passed to the
  injected `rerank_fn`).
- Eval gate is manual (needs DB + qrels), not CI.
- Verification: `.venv/bin/python -m pytest apps/api` → all pass.

## Done criteria

- [ ] Bench script can measure a named config; eval has `rerank_pool` variants.
- [ ] One quality-safe change is applied, or a STOP report proposes the next step.
- [ ] Recall@8 ≥ 0.894, nDCG@8 ≥ 0.682, false-abstain 0.000, false-answer ≤ 0.250.
- [ ] `retrieve-bench.json` re-measured with a fresh method tag and date.
- [ ] README/DECISIONS show the before/after with the knob and quality delta.
- [ ] RRF/`top_k` unchanged; no ANN index added.
- [ ] `pytest apps/api` exits 0.
- [ ] `plans/README.md` row 023 is DONE.

## STOP conditions

- Any change drops Recall@8 below 0.894 or nDCG@8 below 0.682, or moves the
  abstain calibration outside the bounds above — revert and report.
- The best quality-safe candidate still leaves p95 ≥ 400 ms — stop; propose the
  next step (quantization / different model) as a **new** plan.
- A rerank failure can still produce hits with `rerank_skipped=False` — stop;
  contract violation.
- The work needs a live Groq key — stop; retrieve + qrels are local.
- `retrieve-bench.json` would need hand-edited numbers — stop.

## Maintenance notes

- Re-run the bench after plan 017 filters, plan 019 rewrite, or any pool-size
  change; latency and quality both move with the pool.
- Plan 019's rewrite call is **before** retrieve; keep it out of retrieve-only
  latency and report it separately.
- Reviewers: confirm the ablation table exists, the method tag/date are fresh,
  and the chosen knob is overridable (not hard-coded) so the comparison axis
  stays honest.
- Deferred: ANN index (only if a future bench shows the dense scan dominating),
  quantization of the reranker, plan 008.2.
