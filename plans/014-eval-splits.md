# Plan 014: Re-ground `ci.jsonl`, known-bad, and redteam in the big freeze

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**:
> `git diff --stat 028fa3e..HEAD -- evals/splits/ci.jsonl evals/splits/known_bad.jsonl evals/redteam.jsonl citebench/eval/pipeline.py apps/api/tests/test_eval_ci.py apps/api/tests/test_redteam.py docs/contracts/eval-jsonl.md`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED (splits that are not actually grounded would make eval theater)
- **Depends on**: plan 013 (big freeze ingested and countable)
- **Category**: direction (I3 / E1, E2)
- **Planned at**: commit `028fa3e`, 2026-09-10

## Why this matters

The current `ci.jsonl` has 3 rows written for the 14-page freeze. The corpus is
now ~1,000+ pages, so the CI split must be re-grounded: single-hop questions,
comparison questions that need two sources, and abstain questions whose answers
are **not** in the freeze. Known-bad and the 10 redteam cases must be re-checked
after the corpus grew, because a bigger corpus can accidentally make an old
"unanswerable" question answerable (or an injection string retrievable). A split
that is not grounded is worse than a small one.

## Current state

**Contract A** (`docs/contracts/stubs/schemas.py:36-89`): `EvalRow` fields
`id, question, expected, must_cite, abstain, known_bad, tags, attack_type,
expect_block`. Invariants: `known_bad` implies `abstain`; `abstain` implies not
`must_cite`; redteam fields require the `redteam` tag and `expect_block` implies
`abstain` + not `must_cite`. `load_eval_jsonl` rejects invalid/duplicate rows
(`schemas.py:145-165`). Unknown keys are ignored (`docs/contracts/eval-jsonl.md:33`).

**Current `ci.jsonl`** = 3 rows (`ci-001..003`), all
`must_cite:true, abstain:false, known_bad:false`, e.g.
```json
{"id":"ci-001","question":"How does the kube-scheduler place pods onto nodes?","expected":"…","must_cite":true,"abstain":false,"known_bad":false,"tags":["k8s","scheduler"]}
```

**Tests that constrain this**:
- `apps/api/tests/test_eval_ci.py:28-41` `test_ci_jsonl_is_small_real_contract_a`
  asserts `2 <= len(rows) <= 8` and **every** row `known_bad is False`,
  `abstain is False`, `must_cite is True`. Adding abort/abstain rows breaks it.
- `apps/api/tests/test_eval_ci.py:208-243` runs the committed `ci.jsonl` in
  **mock** mode and asserts `faithfulness >= 0.7`. New rows with no mock fixture
  fall back to keyword matching (`fixture_for_row`, `citebench/eval/pipeline.py:88-98`)
  and may drop below the gate, failing the test.
- `apps/api/tests/test_redteam.py:29-35` asserts exactly 10 redteam cases.

**Mock fixtures** (`citebench/eval/pipeline.py:36-85`): `CI_FIXTURES` keyed
`ci-001/002/003`; `default_mock_answer` (`:101-117`) looks up a fixture, else
keyword fallback. Live mode calls real `generate` (`pipeline.py:131-144`).

**Known-bad** (`evals/splits/known_bad.jsonl`) = 3 InnovX/Acme rows; the freeze
does not contain those answers. **Redteam** (`evals/redteam.jsonl`) = 10 rows
(injection/pii_leak/jailbreak), 4/3/3.

**Conventions**: JSONL, one row per line, ids kebab-case matching
`^[A-Za-z0-9][A-Za-z0-9._-]*$`; `expected` is a short grounding sentence, never a
fabricated fact.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Load split | `.venv/bin/python -c "from citebench.eval.loader import load_eval_jsonl; print(len(load_eval_jsonl('evals/splits/ci.jsonl')))"` | row count |
| Grounding check | `curl -sS -X POST localhost:8000/retrieve -H 'Content-Type: application/json' -d '{"query":"<question>"}'` | top hits from the expected doc |
| Mock evals | `make evals` | CI + redteam pass |
| API tests | `.venv/bin/python -m pytest apps/api` | all pass |

## Scope

**In scope**:

- `evals/splits/ci.jsonl` — new single-hop/compare/abstain rows.
- `evals/splits/known_bad.jsonl` — re-verified (edit only if something is now answerable).
- `evals/redteam.jsonl` — re-verified; stays exactly 10.
- `citebench/eval/pipeline.py` — mock fixtures for the new rows (so mock CI stays deterministic).
- `apps/api/tests/test_eval_ci.py`, `apps/api/tests/test_redteam.py` — update count/invariant assertions.
- `docs/contracts/eval-jsonl.md` — document the category tags (single-hop/compare/abstain).
- `docs/decision-trail.tsv`, `plans/README.md` status row.

**Out of scope**:

- Live RAGAS execution and README numbers — plan 015.
- Running the naive success assert logic differently.
- Adding a second eval framework or an LLM-as-judge in the split.
- Changing the 0.7 gate.

## Git workflow

- Branch: `advisor/014-render-eval-splits`
- Commit message: `Re-ground the CI, known-bad, and redteam splits in the big freeze.`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Author single-hop rows

For a single-hop row, the answer must be in **one** doc in the freeze. Choose
~8 questions spanning K8s, Azure, Postgres, FastAPI, OSTEP (e.g. "What does a
Kubernetes Service of type ClusterIP expose?"). For each:
1. Run `POST /retrieve` with the exact question; confirm the top hits come from
   the doc named in `expected`.
2. Write the row with `must_cite:true, abstain:false, known_bad:false,
   tags:["single-hop", <product>]`.

### Step 2: Author compare rows

~8 rows whose answer requires **two** sources (e.g. compare K8s `Service` vs
`Ingress`; AKS managed identity vs Azure blob managed identity). `expected` names
both docs. Same invariants as Step 1, `tags:["compare", …]`. Confirm retrieve
returns at least one hit from each named doc.

### Step 3: Author abstain rows

~4–8 rows that are plausible but **not** answered by the freeze. Verify absence
by checking `/retrieve` returns no confident grounding (and, if indexed, by
grep over `corpus/raw` text). Rows:
`{"..., "must_cite":false, "abstain":true, "known_bad":false, "tags":["abstain", …]}`.
Do not reuse the known-bad InnovX/Acme prompts here; those stay in `known_bad.jsonl`.

**Target size**: 16–24 total rows. Keep ids unique and ordered (`ci-001`, …).
Record in the commit body, per row, the doc(s) that ground it.

**Verify**: `load_eval_jsonl('evals/splits/ci.jsonl')` returns the row count with
no error; ids unique.

### Step 4: Update mock fixtures so mock CI still passes

In `citebench/eval/pipeline.py`, add a `CI_FIXTURES` entry for every new row id:
a grounded answer plus `contexts` copied from the real expected chunk text
(so `fixture_ragas_scores` scores high). Keep `fixture_for_row` as the fallback.
Do **not** make the fixture answer cite a doc not in the freeze.

**Verify**: `make evals` → CI gate passes with the new split in mock mode and
redteam reports 10/10 blocks. If the mock gate fails, fix fixtures (do not lower
the threshold).

### Step 5: Update tests

In `apps/api/tests/test_eval_ci.py`:
- Replace `test_ci_jsonl_is_small_real_contract_a` with a version that:
  - asserts `16 <= len(rows) <= 32` (adjust to the final count),
  - asserts every row has `known_bad is False`,
  - asserts non-abstain rows are `must_cite is True` and abstain rows are
    `must_cite is False`,
  - asserts `{tags}` covers `{"single-hop","compare","abstain"}`.
- Keep the mock-gate test; it now exercises the expanded split.

In `apps/api/tests/test_redteam.py`: no count change (still 10); if the attack
strings changed, keep `len(rows) == 10` and all three attack types.

**Verify**: `.venv/bin/python -m pytest apps/api` → all pass.

### Step 6: Re-verify known-bad and redteam

- Known-bad: for each of the 3 rows, run `/retrieve` with the question and
  confirm no freeze chunk answers it. If the bigger corpus now answers one, edit
  the prompt to a still-unanswerable one and note it.
- Redteam: run `./scripts/local-evals.sh` (mock) and confirm 10/10 blocked. If a
  case now passes retrieval of a real doc, strengthen the injection string so it
  still tests blocking, keeping exactly 10 cases and all attack types.

**Verify**: `EVAL_STORE_DIR=evals/results .venv/bin/python -m citebench.eval.redteam --split evals/redteam.jsonl --mock --store-dir evals/results`
→ `passed:10 failed:0`.

### Step 7: Contract note + trail

- In `docs/contracts/eval-jsonl.md`, add a short "Tags" note: `single-hop`,
  `compare`, `abstain` are the CI categories; redteam rows use `redteam` + attack type.
- Append `docs/decision-trail.tsv`:
  `<today>\te1-eval-splits\tci.jsonl re-grounded (<N> rows: single-hop/compare/abstain) on big freeze; known-bad + 10 redteam re-verified\tPASS`.

## Test plan

- `test_eval_ci.py`: expanded split contract (count, invariants, category tags);
  mock gate still passes.
- `test_redteam.py`: exactly 10, all attack types, expect_block invariants.
- No live Groq in CI.
- Verification: `.venv/bin/python -m pytest apps/api` → all pass; `make evals` → pass.

## Done criteria

- [ ] `ci.jsonl` covers single-hop, compare, and abstain; every answer is grounded
      in the freeze or deliberately absent; ids unique; loads clean.
- [ ] Mock CI (`make evals`) passes the 0.7 gate on the new split (fixtures added).
- [ ] `known_bad.jsonl` rows verified unanswerable; `redteam.jsonl` still exactly 10
      with 10 blocks.
- [ ] Tests updated; `pytest apps/api` exits 0.
- [ ] `eval-jsonl.md` + decision-trail updated.
- [ ] `plans/README.md` row 014 is DONE.

## STOP conditions

- A "single-hop" or "compare" row cannot be grounded by `/retrieve` — stop and
  replace it; do not ship an ungrounded row.
- An abstain row turns out to be answered by the freeze — stop and change it.
- Mock CI cannot pass without lowering the threshold or inventing a fixture that
  cites outside the freeze — stop and report.
- Redteam must drop below 10 cases or lose an attack type — stop; that is a
  contract change, not an executor decision.

## Maintenance notes

- Plan 015 scores exactly this split live; any row edit after 015 means re-running
  the live artifact.
- Re-freezing the corpus (new manifest) invalidates grounding; re-run Steps 1–6.
- Reviewers: spot-check 3 rows by running `/retrieve` and reading the cited chunk.
- Deferred: RAGAS "context recall" (needs ground-truth contexts) is not added here.
