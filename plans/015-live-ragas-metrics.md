# Plan 015: Run live RAGAS and publish method-tagged metrics

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**:
> `git diff --stat 028fa3e..HEAD -- citebench/eval/ragas_metrics.py citebench/eval/ci.py citebench/eval/pipeline.py apps/api/requirements*.txt apps/api/metrics.py scripts/local-evals.sh README.md DECISIONS.md`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: L
- **Risk**: HIGH (new eval deps, judge vendor constraint, cost of live runs)
- **Depends on**: plan 014 (re-grounded splits)
- **Category**: direction (I3 / E3, E4)
- **Planned at**: commit `028fa3e`, 2026-09-10

## Why this matters

Every score on the README today is `mode=mock` from a fixture judge
(`evals/results/latest.json:7`), and p95/cost are `—`. That is honest but not
credible for a public bench. This plan makes `--live` run the **real `ragas`
library** with the **Groq** judge and local nomic embeddings, stores an artifact
stamped with the judge model, ragas version, and date, and fills the README's
faithfulness / context-precision / p95 / cost rows from live artifacts and live
traces. No invented numbers; if a metric cannot be measured, it stays `—`.

Hard constraint: Groq is the **only** billed model and nomic-ONNX is the only
embedder. RAGAS defaults to OpenAI; it must be explicitly pointed at Groq +
local nomic, or the live run must fail.

## Current state

- `citebench/eval/ragas_metrics.py:20-29` imports ragas inside a broad
  `except Exception`, leaving names `None` when absent. **`ragas`/`datasets` are
  not in any requirements file** (`apps/api/requirements.txt`,
  `requirements-dev.txt`).
- `score_row` (`ragas_metrics.py:64-80`):
  ```python
  if abstained: return None
  if live and os.environ.get("GROQ_API_KEY", "").strip():
      live_scores = _try_live_ragas(question, answer, contexts, expected)
      if live_scores is not None:
          return live_scores
  return fixture_ragas_scores(question, answer, contexts, expected)
  ```
  i.e. live **silently falls back to the fixture** when ragas is missing or
  `evaluate` throws (`_try_live_ragas`, `:162-196`). This must not happen in a
  "live" artifact.
- `ci.py` artifact (`CiReport.to_artifact`, `:65-98`) has `mode`, `framework:
  "ragas"`, metrics, known_bad; **no judge model, no measured_at, no method tag,
  and no `split_rows`** (so `metrics.py:232-235` `n_scored` is always `None`).
- `metrics.py:222-245` reads `latest.json` `metrics.faithfulness` /
  `context_precision` + `mode`; `:90-133` derive p50/p95 from `RunTrace.latency_ms`
  and cost/1k from traces with billed cost; `null` when none.
- `scripts/local-evals.sh:42-66`: `--live` runs **redteam live only**; CI always
  runs `--mock`.
- `metrics.py` method strings live at `:20-38`; `corpus.json` is the fallback
  corpus artifact (`:259-267`).
- README Numbers (`README.md:157-166`) currently: faithfulness 1.000 (mock),
  context precision 0.833 (mock), p95 `—`, cost/1k `—`.
- No `deepeval` anywhere (only a prose negation, `DECISIONS.md:192`).

**Conventions**: artifacts are JSON written by `citebench/eval/store.py`
(`write_report`, `:46-62`) with `mode` and a metric diff; tests must not require
Groq or a live DB; live gates require `GROQ_API_KEY` (`ci.py:187-204`).

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Install eval extras | `.venv/bin/pip install -r apps/api/requirements-eval.txt` | exit 0 |
| Live CI run | `.venv/bin/python -m citebench.eval.ci --split evals/splits/ci.jsonl --known-bad evals/splits/known_bad.jsonl --threshold-faithfulness 0.7 --live --store-dir evals/results` | exit 0, `mode=live` |
| Live latency/cost batch | `.venv/bin/python scripts/live-smoke.py` | N RunTraces with `latency_ms>0` |
| Metrics | `curl -sS localhost:8000/metrics` | live values + method tags |
| API tests | `.venv/bin/python -m pytest apps/api` | all pass |

## Scope

**In scope**:

- `apps/api/requirements-eval.txt` (**create**) — pinned `ragas`, `datasets`,
  `langchain-groq`, and any transitive pins; not installed by default/CI.
- `citebench/eval/ragas_metrics.py` — real Groq judge + local nomic embeddings;
  live mode raises instead of falling back.
- `citebench/eval/ci.py` — artifact gains `judge_model`, `measured_at`,
  `method`, and `split_rows`.
- `apps/api/metrics.py` — surface the live method tag; keep null semantics.
- `scripts/local-evals.sh` — `--live` also runs CI live.
- `scripts/live-smoke.py` (**create**) — a small live generate batch to populate
  traces for p95/cost.
- `README.md`, `DECISIONS.md`, `evals/results/latest.json` (committed live artifact).
- `plans/README.md` status row.

**Out of scope**:

- Adding OpenAI/Anthropic or any second judge/embed vendor (forbidden).
- CI live wiring — plan 016.
- Changing the 0.7 threshold or the split content (plan 014).
- DeepEval or a second framework.
- Making `--mock` use ragas.

## Git workflow

- Branch: `advisor/015-live-ragas`
- Commit message: `Score the bench with live RAGAS and report measured metrics.`
- Commit `evals/results/latest.json` with `mode=live` and the exact method/model.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Add the eval extra

Create `apps/api/requirements-eval.txt` with pinned versions discovered at
execution time (`pip index versions ragas datasets langchain-groq`), e.g.
`ragas==<x.y.z>`, `datasets==<x.y.z>`, `langchain-groq==<x.y.z>`. Add a header
comment: `# Live eval only. CI installs requirements.txt; this file is opt-in.`
Do **not** add ragas to `requirements.txt`.

**Verify**: `.venv/bin/pip install -r apps/api/requirements-eval.txt` → exit 0;
`.venv/bin/python -c "import ragas, datasets, langchain_groq; print(ragas.__version__)"`.

### Step 2: Point RAGAS at Groq + local nomic

In `citebench/eval/ragas_metrics.py`:
- Implement a `langchain_core.embeddings.Embeddings` adapter whose
  `embed_documents`/`embed_query` call `embed.embed_texts`/`embed.embed_query`
  with the loaded settings (so ragas never calls OpenAI).
- Build `evaluate(..., llm=ChatGroq(model=settings.chat_model, api_key=...),
  embeddings=<NomicEmbeddings>())` with `faithfulness`, `context_precision`,
  `answer_relevancy`.
- Return the judge model id and ragas version alongside the scores so the
  artifact can stamp them.
- In **live** mode, if `ragas`/deps are missing or `evaluate` raises, raise a
  clear `RuntimeError("live RAGAS requested but …")` — do **not** return the
  fixture. Keep the fixture strictly for `live=False`.

**Verify**: a unit test with a fake `evaluate`/judge asserts live mode surfaces
the injected scores and that a raised judge error propagates (no fixture
fallback). Run `.venv/bin/python -m pytest apps/api/tests/test_eval_ci.py`.

### Step 3: Enrich the CI artifact

In `citebench/eval/ci.py`:
- `to_artifact()` adds `judge_model`, `measured_at` (ISO UTC), `method`
  (`citebench.eval.ragas.v1`), `ragas_version`, and `split_rows`
  (`[{id, faithfulness, context_precision, answer_relevancy}]`, no contexts/text).
- Ensure `metrics.py` `n_scored` (`:232-235`) now resolves.

**Verify**: run the **mock** CI and confirm `latest.json` has the new keys and
`split_rows`; `.venv/bin/python -m pytest apps/api/tests/test_metrics.py` → pass.

### Step 4: Wire live CI into `local-evals.sh`

Change the `--live` branch (`scripts/local-evals.sh:56-66`) to also run:
```
"$PY" -m citebench.eval.ci --split evals/splits/ci.jsonl \
  --known-bad evals/splits/known_bad.jsonl --threshold-faithfulness 0.7 \
  --live --store-dir "$EVAL_STORE_DIR"
```
before the live redteam run, and keep requiring `GROQ_API_KEY`.

**Verify**: `GROQ_API_KEY=<set> ./scripts/local-evals.sh --live` → CI reports
`mode=live` and redteam 10/10. (If no key is available, report that and skip; do
not fake it.)

### Step 5: Populate live latency/cost traces

Create `scripts/live-smoke.py` that runs `N` (default 25) real `generate()` calls
over the grounded single-hop/compare questions, each emitting a `RunTrace`, then
prints the trace count and latency range. It needs `GROQ_API_KEY` and an indexed
DB. It must not write invented traces — only real calls.

**Verify**: `curl -sS localhost:8000/traces` shows `N` traces with
`latency_ms > 0`; `curl -sS localhost:8000/metrics` shows non-null `p50`, `p95`,
and `cost.usd`.

### Step 6: Fill the README Numbers table

Using the live artifact + `/metrics`:
- **Faithfulness** = `metrics.faithfulness` from `latest.json` (`mode=live`),
  method `live ragas <ragas_version>, judge <judge_model>, <date>`, tag
  `measured-under-live-ragas-<judge_model>-<date>`.
- **Context precision** = same artifact, same method.
- **p95 latency** = `/metrics` value, method = the `LATENCY_METHOD` string.
- **Cost / 1k queries** = `/metrics` value, method = `COST_PER_1K_METHOD`.
- Add a one-line note that the artifact is committed at `evals/results/latest.json`
  with `mode`, `judge_model`, `measured_at`.
- Remove/rewrite the mock method tags (`measured-under-mock-ragas-judge`).
- Update `DECISIONS.md` C6/C7 paragraphs: live RAGAS is now the published mode;
  mock remains the CI fallback (plan 016).

**Verify**: `.venv/bin/python -m pytest apps/api` → pass. Re-read the README:
every changed number traces to `latest.json` or `/metrics` from this session.

### Step 7: "Drop DeepEval"

Confirm (grep) there is no `deepeval` dependency or code. Keep the DECISIONS note
that only RAGAS is used, or simplify it; do not add DeepEval.

**Verify**: `grep -ri deepeval --include='*.py' --include='*.txt' --include='*.yml' .` → no code hits.

## Test plan

- `test_eval_ci.py`: live mode uses injected judge; judge error propagates; no
  fixture fallback in live; artifact has `judge_model`/`measured_at`/`method`/`split_rows`.
- `test_metrics.py`: `n_scored` now populated; null semantics unchanged.
- Live Groq is manual/opt-in; CI stays mock.
- Verification: `.venv/bin/python -m pytest apps/api` → all pass.

## Done criteria

- [ ] `requirements-eval.txt` exists with pinned versions; not installed by CI.
- [ ] Live RAGAS uses a **Groq** judge and **local nomic** embeddings; live mode
      has no fixture fallback and fails loudly.
- [ ] `evals/results/latest.json` is a `mode=live` artifact with `judge_model`,
      `measured_at`, `method`, `split_rows`.
- [ ] README faithfulness, context precision, p95, cost/1k are live-measured with
      method tags; no mock tags remain; unmeasured stays `—`.
- [ ] `local-evals.sh --live` runs live CI + redteam.
- [ ] `pytest apps/api` exits 0.
- [ ] `plans/README.md` row 015 is DONE.

## STOP conditions

- RAGAS cannot be configured with a non-OpenAI LLM/embeddings without patching
  its internals — stop and report; do not add OpenAI.
- Live judge calls exceed the Groq rate/budget for the split — reduce the split
  in plan 014, not the metric; stop and report.
- A live run cannot complete (no key / quota) — stop; leave metrics `—` rather
  than committing a mock artifact as live.
- `ragas` requires a dependency that conflicts with pinned runtime packages —
  stop and report the conflict.

## Maintenance notes

- Plan 016 wires CI to run live when `GROQ_API_KEY` is a repo secret, mock otherwise.
- Any split or manifest change invalidates the committed live artifact; re-run
  Steps 4–6.
- Reviewers: confirm `latest.json` `mode=live`, `judge_model` is a Groq id, and
  README numbers equal the artifact/`/metrics`.
- Deferred: per-category metric breakdown (single-hop vs compare) is out of scope;
  `split_rows` makes it possible later.
