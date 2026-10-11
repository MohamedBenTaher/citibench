# Plan 025: Repair the "honest numbers" — stale labels, a fail-able gate, and the live-path context bug

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**:
> `git diff --stat 93c3bb9..HEAD -- README.md citebench/eval/pipeline.py citebench/eval/ragas_metrics.py apps/api/citebench_api/generation/generate.py apps/api/tests/test_eval_ci.py DECISIONS.md docs/RETRIEVAL-EVALS.md`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1 (this is the project's stated differentiator — "no invented
  scores" — and it currently has stale/mislabeled numbers)
- **Effort**: M
- **Risk**: MED (one step touches the live eval path; guard with a STOP)
- **Depends on**: plan 024 (cut the branch from the fast-forwarded `main`)
- **Category**: docs + correctness
- **Planned at**: commit `93c3bb9`, 2026-10-10

## Why this matters

Citebench's entire pitch is that it measures instead of vibes, and the README
goes out of its way to label every number with a measurement method. Right now
three published numbers are wrong or stale, the always-on CI faithfulness gate
can never actually fail (so it protects nothing), the test meant to catch a
mock artifact masquerading as live is a silent no-op, and the `ci.py --live`
path feeds chunk **IDs** (not text) into the judge, guaranteeing ~0
faithfulness. Fixing these closes the gap between the repo's claim and its
behavior — which is exactly what an interviewer who reads the "Numbers
(honest)" table would test.

## Current state

### 5.1 — Stale README numbers

- `README.md:194-195` (retrieve latency) reads **297 ms** (p50) and **316 ms**
  (p95), tagged `measured-under-retrieve-bench-2026-09-14`.
- The committed artifact `evals/results/retrieve-bench.json` at HEAD records
  `measured_under: "retrieve-bench-2026-09-15"`, `p50_ms: 302.699`,
  `p95_ms: 352.902`, `mean_ms: 309.323`. The 297/316 values exist only at an
  earlier commit (`8f59705`), so the README is citing a run that no longer
  matches the file. p95 is understated by ~11.7%.

### 5.2 — Mislabeled corpus-chunk provenance

- `README.md:186` tags the chunk count `measured-under-live-ingest-2026-09-12`.
- `evals/results/corpus.json` records `measured_under: "local-snapshots"` and
  `fetched: 0` — nothing was fetched from the network; it was produced from
  local HTML snapshots. "live-ingest" is wrong.

### 5.3 — The mock faithfulness gate cannot fail

- `citebench/eval/pipeline.py:36-44` — `_fixture()` sets
  `"contexts": [answer]`, i.e. the "context" the answer is scored against is
  the answer itself.
- `citebench/eval/ragas_metrics.py:107-115` — `_faithfulness()` computes
  statement overlap between `answer` and `" ".join(contexts)`. With
  `contexts == [answer]` this is always 1.0. The README labels it "Fixture
  judge" (honest), but the gate it feeds (`ci.py` faithfulness ≥ 0.7) can
  never fire, so the always-on CI job provides no regression signal.
- `citebench/eval/ragas_metrics.py:76-80` — in live mode, if the real RAGAS
  judge is unavailable or throws, `score_row()` **silently** returns fixture
  scores. There is no per-row marker distinguishing a live score from a
  fixture fallback, and `ci.py` writes `framework: "ragas"` either way.
- The enforcement machinery itself is real and tested:
  `citebench/eval/ci.py:289-296` sets `exit_code = 1` when faithfulness is
  under threshold, and `apps/api/tests/test_eval_ci.py:156` proves a non-zero
  exit with an injected unfaithful answer. Do not rewrite this — only the
  fixture provenance and fallback signaling need fixing.

### 5.4 — Silent no-op test

- `apps/api/tests/test_eval_ci.py:328-334`:

  ```python
  def test_committed_live_artifact_is_not_mock() -> None:
      live = REPO_ROOT / "evals" / "results" / "live.json"
      if not live.exists():
          return
      payload = json.loads(live.read_text(encoding="utf-8"))
      assert payload.get("mode") == "live"
      assert payload.get("judge_model")
  ```

  `live.json` does not exist in the repo, so this test always `return`s and
  passes without asserting anything.

### 5.5 — Live-path context bug

- `citebench/eval/pipeline.py:221-225`:

  ```python
  def _contexts_from_result(result: Any) -> list[str]:
      texts: list[str] = []
      for item in getattr(result, "retrieved_chunk_ids", None) or []:
          texts.append(str(item))
      return texts
  ```

  `retrieved_chunk_ids` holds chunk **ids** (`generate.py:365`), not text. The
  correct path (`citebench/eval/answers.py:33`) does
  `[hit.text for hit in hits if hit.text]`. `GenerateResult`
  (`apps/api/citebench_api/generation/generate.py:89`) does not carry the chunk
  texts, only the ids, so `live_answer` (`pipeline.py:149-160`) cannot recover
  them.

### 5.6 — Unbacked baseline numbers

- `DECISIONS.md:62-64` and `docs/RETRIEVAL-EVALS.md:224` quote a MiniLM-L-12-Q
  baseline (recall@8 **0.904**, MRR **0.616**, nDCG@8 **0.692**, false-answer
  **0.250**) used as the "before" for the TinyBERT swap. No committed artifact
  in `evals/results/retrieval.json` (which contains 8 `errors: {}` variants)
  carries a MiniLM arm, so these numbers are not reproducible from the repo.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Tests | `.venv/bin/python -m pytest apps/api -q` | 183 passed |
| Eval CLI smoke | `.venv/bin/python -m citebench.eval.ci --split evals/splits/ci.jsonl --known-bad evals/splits/known_bad.jsonl --threshold-faithfulness 0.7 --mock --store-dir evals/results` | exit 0, `mode=mock` |
| Web typecheck | `(cd apps/web && npm run typecheck)` | exit 0 |

## Scope

**In scope**:
- `README.md` (numbers table only)
- `citebench/eval/pipeline.py` (`_fixture`, `_contexts_from_result`, `live_answer`)
- `citebench/eval/ragas_metrics.py` (provenance/fallback signaling)
- `citebench/eval/ci.py` (write per-row provenance — only if the report shape requires it)
- `apps/api/citebench_api/generation/generate.py` (add `retrieved_contexts` field to `GenerateResult`)
- `apps/api/tests/test_eval_ci.py` (the silent no-op test)
- `DECISIONS.md`, `docs/RETRIEVAL-EVALS.md` (footnote the MiniLM baseline)
- New/updated tests under `apps/api/tests/` and `citebench/eval/`

**Out of scope** (do NOT touch):
- `citebench/eval/ci.py`'s exit-code/gate logic (lines ~254-296) — it is
  correct; only provenance is in scope.
- `citebench/eval/live_score.py` and `citebench/eval/answers.py` — the
  documented live path; already correct.
- Retrieval ranking code, the corpus, and any config defaults.
- Plan 028's working-tree cleanup (the laya spike files).

## Git workflow

- Branch: `advisor/025-honest-numbers` (cut from the fast-forwarded `main`).
- Commit message style matches the repo's imperative past tense, e.g.
  `Refresh the honest-numbers table against the committed artifacts.`
- One commit per step is fine; do NOT push unless the operator asks.

## Steps

### Step 1: Refresh the latency rows

In `README.md`, replace the p50/p95 cells and their method tags so they match
`evals/results/retrieve-bench.json` at HEAD:

- p50: `297 ms` → `303 ms`, tag → `measured-under-retrieve-bench-2026-09-15`
- p95: `316 ms` → `353 ms`, same tag
- Also update the "under the 400 ms budget" sentence if it references the old
  number.

**Verify**: `grep -n "retrieve-bench-2026-09-15\|303 ms\|353 ms" README.md`
returns the two rows. `grep -n "retrieve-bench-2026-09-14" README.md` returns
nothing.

### Step 2: Fix the chunk-count provenance label

In `README.md:186`, change `measured-under-live-ingest-2026-09-12` to
`measured-under-local-snapshots` (this matches `evals/results/corpus.json`
`measured_under`).

**Verify**: `grep -n "measured-under-local-snapshots" README.md` returns the
chunk row (and possibly the pages row, which is already correct). No row still
says `live-ingest`.

### Step 3: Add explicit judge provenance to the eval report (per-row `source`)

In `citebench/eval/ragas_metrics.py`, change `score_row()` so it returns a
provenance marker alongside the scores, and never silently downgrades a live
run to fixture. Concretely:

- Have `score_row()` (or a new companion) return/track `source` where the
  values are `"live"` or `"fixture"`.
- When `live=True` but `_try_live_ragas()` returns `None` (missing judge /
  exception), do **not** silently substitute fixture scores: either raise, or
  return a sentinel that `ci.py` writes as `source: "fixture-fallback"` and
  fails the gate. The simplest correct behavior for a `--live` run is to fail
  loudly rather than fabricate — match the existing live-judge-error behavior
  in `citebench/eval/live_score.py:146-148` and `179-184`.
- In `citebench/eval/ci.py`, write `source` into the report rows so a reviewer
  can see at a glance which rows were judged live vs fixture. Keep the
  top-level `mode` field as-is.

**Verify**: `.venv/bin/python -m citebench.eval.ci --split evals/splits/ci.jsonl --known-bad evals/splits/known_bad.jsonl --threshold-faithfulness 0.7 --mock --store-dir evals/results` exits 0; open
`evals/results/latest.json` and confirm every non-abstain row carries a
`source` field set to `"fixture"` for the mock run.

### Step 4: Make the silent no-op test loud

In `apps/api/tests/test_eval_ci.py`, change the `if not live.exists(): return`
to an explicit `pytest.skip("no committed live.json — run make evals-live
before tagging")` (import `pytest` at the top of the file if not already
imported). Keep the two assertions for when the file exists.

**Verify**: `.venv/bin/python -m pytest apps/api/tests/test_eval_ci.py -q -rs`
shows `test_committed_live_artifact_is_not_mock` as **skipped** with the
reason, not silently passed.

### Step 5: Fix the live-path context bug

1. In `apps/api/citebench_api/generation/generate.py`, add a field to
   `GenerateResult` (near `retrieved_chunk_ids`, line 98):
   `retrieved_contexts: list[str] = Field(default_factory=list)`.
2. Where `generate()` builds the result (around line 365, where
   `retrieved_chunk_ids=[hit.chunk_id for hit in hits]` is set), also set
   `retrieved_contexts=[hit.text for hit in hits if hit.text]`.
3. In `citebench/eval/pipeline.py`, change `_contexts_from_result()` to prefer
   `result.retrieved_contexts` (falling back to the old id-based behavior only
   if the field is absent, to avoid breaking any other caller):

   ```python
   def _contexts_from_result(result: Any) -> list[str]:
       ctx = getattr(result, "retrieved_contexts", None)
       if ctx:
           return [str(t) for t in ctx if t]
       return [str(i) for i in (getattr(result, "retrieved_chunk_ids", None) or [])]
   ```

**Verify**: `.venv/bin/python -m pytest apps/api -q` still exits 0 (183+);
add a test (Step 7) asserting `_contexts_from_result` returns text, not ids,
for a `GenerateResult` with both fields populated.

### Step 6: Footnote the MiniLM baseline

In `DECISIONS.md:62-64` and `docs/RETRIEVAL-EVALS.md:224`, keep the numbers
(they are a legitimate historical "before") but append a provenance note, e.g.
"measured 2026-09-13 in a local run; the MiniLM arm is not preserved in a
committed artifact, so this baseline is not independently reproducible from
the repo."

**Verify**: `grep -n "not.*reproducible\|not preserved in a committed" DECISIONS.md docs/RETRIEVAL-EVALS.md` returns the new notes.

### Step 7: Add regression tests

- In `apps/api/tests/` (model `test_generate.py` as the structural pattern),
  add a test that a `GenerateResult` produced for a non-empty retrieval carries
  `retrieved_contexts` equal to the retrieved chunk texts, and that
  `_contexts_from_result()` returns those texts (not the ids).
- In `apps/api/tests/test_eval_ci.py`, keep the existing injected-unfaithful
  test (line 156) — it is the proof the gate fires — and confirm it still
  passes after Step 3.

**Verify**: `.venv/bin/python -m pytest apps/api -q` exits 0 with the new
tests present and passing.

## Test plan

- New: `GenerateResult.retrieved_contexts` populated with chunk text (not ids);
  `_contexts_from_result` returns text.
- New: `score_row` provenance (`source`) is `"fixture"` in mock mode and the
  live fallback no longer silently substitutes fixture scores.
- Existing: the gate-fires test (test_eval_ci.py:156) still proves non-zero
  exit; the skip test is now a loud skip.
- Verification: `.venv/bin/python -m pytest apps/api -q` → all pass (183 + new).

## Done criteria

- [ ] README latency rows read 303/353 ms tagged `retrieve-bench-2026-09-15`,
      and no stale `2026-09-14` tag remains.
- [ ] README chunk row is tagged `measured-under-local-snapshots`.
- [ ] Mock eval report rows carry a `source` field; a `--live` run no longer
      silently falls back to fixture scores.
- [ ] `test_committed_live_artifact_is_not_mock` reports as **skipped** (loud)
      instead of silently passing.
- [ ] `_contexts_from_result` returns chunk text; `GenerateResult` carries
      `retrieved_contexts`.
- [ ] MiniLM baseline carries a provenance footnote in both docs.
- [ ] `.venv/bin/python -m pytest apps/api -q` exits 0; no out-of-scope files
      modified (`git status`).

## STOP conditions

- The excerpts above don't match the live files (drift).
- Adding `retrieved_contexts` requires touching code outside the in-scope list
  (e.g. the LangGraph state plumbing is more entangled than assumed) — STOP and
  report rather than widening scope.
- Making the live fallback fail-loud breaks an existing green test that
  legitimately expects fallback — investigate and report; do not delete the
  test to make CI green.
- The operator does not want the mock faithfulness to be relabeled/annotated
  (it changes a published artifact shape).

## Maintenance notes

- Making the **default mock faithfulness actually fail-able** (so a regression
  in the answerer shows up) requires corpus-grounded fixture contexts instead
  of `contexts == [answer]`, which is data authoring for the 14 answerable CI
  rows — deliberately deferred here because it is higher-risk and separate from
  labeling honesty.
- Any future run of `make evals` or `make evals-live` will rewrite
  `evals/results/latest.json`/`redteam.json`/`live.json`; after Step 3 those
  files carry `source` provenance — keep that field when regenerating.
- Re-run the README number refresh after any future re-bench (plan 023-style
  runs), not as a one-time fix.
