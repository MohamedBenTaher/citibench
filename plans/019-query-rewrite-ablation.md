# Plan 019: Optional single query-rewrite with an ablation — delete it if it does not help

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index. **This plan is allowed to end in deletion** — read Step 5
> before writing UI or docs.
>
> **Drift check (run first)**:
> `git diff --stat 028fa3e..HEAD -- apps/api/generate.py apps/api/retrieve.py apps/api/settings.py config.yaml apps/api/tests/test_generate.py citebench/eval/ci.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P3
- **Effort**: M
- **Risk**: MED (extra Groq call on the hot path; a rewrite can hurt abstention)
- **Depends on**: plans 015 (live metrics), 017 (filters preserved)
- **Category**: direction (I2 / R3 — spike; may be REJECTED)
- **Planned at**: commit `028fa3e`, 2026-09-10

## Why this matters

Retrieval quality may improve if a terse user query is rewritten into a better
retrieval query before embedding. But a rewrite can also *hurt*: it can pull an
out-of-corpus question into the corpus (breaking abstention) or add latency.
This plan ships the rewrite **behind a default-off flag** and forces an
ablation. Per the program, the code is **deleted** unless the live numbers beat
the baseline. A recorded negative result is a success for this plan.

## Current state

- `generate()` (`apps/api/generate.py`) compiles a LangGraph `START → retrieve →
  generate|abstain → END` (`_compile_graph`, `:356-521`) and passes `query`
  straight to `retrieve_fn` (`:362-371`).
- There is **no** rewrite anywhere: `retrieve.py:148,159` embeds
  `(query or "").strip()`; `generate.py:249,256` passes `query or ""`.
- `validate_run_trace` (`trace.py:171-211`) requires exactly the span tree
  `retrieve → rerank → generate|abstain`. A new span would violate it; a rewrite
  must be recorded as an **attribute** on the retrieve span.
- `chat.py` is the only Groq path (`groq_chat`); `openai/gpt-oss-20b` default.
- Live CI is available after plan 015 (`citebench.eval.ci --live`).
- Filters (plan 017) must survive any rewrite.

**Conventions**: one Groq call max per step; no second vendor; trace stays
pointer-only; config knobs live in `config.yaml` with env overrides in
`settings.py`.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| API tests | `.venv/bin/python -m pytest apps/api` | all pass |
| Baseline live CI | `EVAL_STORE_DIR=/tmp/abl-off .venv/bin/python -m citebench.eval.ci --split evals/splits/ci.jsonl --known-bad evals/splits/known_bad.jsonl --threshold-faithfulness 0.7 --live --store-dir /tmp/abl-off` | `mode=live` artifact |
| Rewrite live CI | same with `CITEBENCH_QUERY_REWRITE=1`, `EVAL_STORE_DIR=/tmp/abl-on` | `mode=live` artifact |
| Ablation | `.venv/bin/python scripts/rewrite-ablation.py --off /tmp/abl-off --on /tmp/abl-on` | writes `rewrite-ablation.json` |

## Scope

**In scope**:

- `apps/api/rewrite.py` (**create**, may be deleted in Step 5) — one Groq rewrite.
- `apps/api/settings.py` + `config.yaml` — `query_rewrite` flag (default off).
- `apps/api/generate.py` — apply rewrite before retrieve; record attributes; keep filters.
- `apps/api/tests/test_generate.py` (or `test_rewrite.py`) — flag/fallback tests.
- `scripts/rewrite-ablation.py` (**create**) — compare two artifacts, write JSON.
- `evals/results/rewrite-ablation.json` (**create**).
- `DECISIONS.md` — record keep/delete decision.
- `plans/README.md` status row (REJECTED with rationale if deleted).

**Out of scope**:

- Multi-hop rewriting, query decomposition, HyDE, or a second LLM call.
- A new span or a second vendor.
- Making rewrite on by default.
- Changing the split or threshold.

## Git workflow

- Branch: `advisor/019-query-rewrite`
- Commit message: `Add an optional query rewrite behind an ablation flag.`
- If the ablation loses, make a **second** commit that removes the flag path and
  sets the plan row to REJECTED; do not leave dead code.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Flag

Add `query_rewrite: bool = False` to `Settings` (`settings.py:36-69`), read from
`_env_flag("CITEBENCH_QUERY_REWRITE")`. Add `query_rewrite: false` + a comment to
`config.yaml`. Add `MAX_REWRITE_WORDS = 40` guard.

**Verify**: `.venv/bin/python -c "import os; os.environ['CITEBENCH_QUERY_REWRITE']='1'; from settings import load_settings; print(load_settings().query_rewrite)"` → `True`.

### Step 2: One rewrite call

Create `apps/api/rewrite.py`:
```python
def rewrite_query(query: str, settings: Settings) -> str:
    """One Groq call → a single retrieval query. Never raises; returns `query` on any failure."""
```
Use `groq_chat` with a strict JSON prompt ("Return {\"query\": \"...\"} only"). On
timeout, 4xx, invalid JSON, or an empty result, return the original query and log.
Clamp to `MAX_REWRITE_WORDS`. Do not change filters or product terms.

**Verify**: unit test with an injected chat fn returning a JSON query → returns it;
returning garbage/raising → returns the original.

### Step 3: Apply in `generate` (and record)

In `generate.py`:
- If `settings.query_rewrite` is true and the query is non-empty, compute
  `rewritten = rewrite_query(query, settings)` and use it for retrieval.
- Attach `original_query` and `rewritten_query` as attributes on the **retrieve**
  span only (do not add a span; do not put chunk text there).
- Keep `abstain` semantics: rewrite must not inject corpus terms that fabricate
  grounding; an out-of-corpus question that abstained must still abstain. Test this.

**Verify**: `.venv/bin/python -m pytest apps/api/tests/test_generate.py apps/api/tests/test_trace.py` → pass (trace validates with the two attributes).

### Step 4: Ablation script

Create `scripts/rewrite-ablation.py --off <store> --on <store>`:
- Read each store's `latest.json` (`mode`, `metrics`, `judge_model`).
- Write `evals/results/rewrite-ablation.json` with baseline + rewritten metrics,
  deltas, judge model, both run ids/dates, and a `decision` field per the rule:
  keep iff `faithfulness_on - faithfulness_off >= 0.02` and
  `context_precision_on >= context_precision_off - 0.02` and
  `answer_relevancy_on >= answer_relevancy_off - 0.02`.
- The script only reports; it does not decide by itself.

**Verify**: run the two live CI commands, then the script; the JSON has both
metric sets and a `decision`.

### Step 5: Keep or delete

- **If decision = keep**: keep the flag default-off, add a short README/DECISIONS
  note with the measured delta and the command to enable it.
- **If decision = delete**: remove `rewrite.py`, the flag wiring in
  `generate.py`/`settings.py`/`config.yaml`, and the tests that only cover it;
  keep `rewrite-ablation.json` as the record; set the README/DECISIONS note to
  "evaluated and rejected — no measurable gain" with the numbers; set
  `plans/README.md` 019 to REJECTED.

**Verify**: `.venv/bin/python -m pytest apps/api` → pass; `git status` shows only
the intended files.

## Test plan

- `test_rewrite.py`/`test_generate.py`: flag off → query unchanged; flag on +
  injected chat → rewritten used in retrieve and recorded on the span; failure →
  original used.
- Abstain regression: an out-of-corpus question still abstains with rewrite on.
- Ablation is manual (needs Groq); baseline vs rewritten artifacts.
- Verification: `.venv/bin/python -m pytest apps/api` → all pass.

## Done criteria

- [ ] Flag exists and is **off** by default.
- [ ] Rewrite is one Groq call, never raises, preserves filters, adds no span.
- [ ] Ablation artifact exists with both metric sets and a decision.
- [ ] If it lost: code is deleted, `latest.json`/README make no rewrite claim, row 019 = REJECTED.
- [ ] If it won: README/DECISIONS record the measured delta.
- [ ] `pytest apps/api` exits 0.
- [ ] `plans/README.md` row 019 is DONE or REJECTED.

## STOP conditions

- The rewrite cannot be recorded without adding a trace span — stop; attributes
  on the retrieve span are the intended design.
- Rewrite breaks abstention on known-bad rows — stop; delete rather than tune.
- The ablation needs more live calls than the Groq budget allows — stop and report;
  do not fabricate a comparison.
- Keeping the rewrite would make it default-on — stop; the program requires
  default-off and a measured win.

## Maintenance notes

- If kept, any split/manifest change requires re-running the ablation.
- Filters (plan 017) and rewrite must not fight: rewrite the question, keep the
  filter.
- Reviewers: verify `rewrite-ablation.json` has real run ids/dates and that a
  losing rewrite leaves no dead flag.
- Deferred: multi-query rewriting is explicitly out of scope.
