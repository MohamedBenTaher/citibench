# Plan 016: Make CI fail under the faithfulness gate (live when secrets allow)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**:
> `git diff --stat 028fa3e..HEAD -- .github/workflows/eval-ci.yml scripts/local-evals.sh apps/api/tests/test_eval_ci.py README.md infra/deploy/README.md Makefile`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED (CI secrets/forks; Postgres service; runtime budget)
- **Depends on**: plan 015 (live runner + committed live artifact)
- **Category**: direction (I3 / E5)
- **Planned at**: commit `028fa3e`, 2026-09-10

## Why this matters

A gate that never runs is decoration. Today CI runs only **mock** RAGAS and
mock redteam (`.github/workflows/eval-ci.yml:41-62`), and the env var
`CITEBENCH_EVAL_MOCK` it sets is read by no code. Plan 015 added a real live
runner. This plan makes the faithfulness gate block merges: mock CI on every PR,
and a **live** gate when `GROQ_API_KEY` is configured — plus a documented
mandatory live run on the big freeze before any public tag.

Live CI must stay fast and hermetic, so it runs the live **path** against the
committed `corpus-v0` smoke corpus (14 docs, offline snapshots, plan 009), not a
~1,000-page crawl. The full-freeze live run is the pre-public gate.

## Current state

`.github/workflows/eval-ci.yml` (triggers: push to `main`, PRs):
- Step "RAGAS CI gate" (`:41-52`) sets `CITEBENCH_EVAL_MOCK: "1"` (unused) and runs
  `python -m citebench.eval.ci --split evals/splits/ci.jsonl --known-bad … --threshold-faithfulness 0.7 --mock --store-dir evals/results`.
- Step "Redteam C8" (`:54-62`) runs `python -m citebench.eval.redteam … --mock`.
- No Postgres service; Python 3.12; `pip install -r apps/api/requirements.txt pytest`.
- `scripts/local-evals.sh:42-54` always runs CI `--mock`; plan 015 makes `--live`
  also run CI live.
- Gate enforcement already has unit coverage:
  `apps/api/tests/test_eval_ci.py:152-190` (`test_faithfulness_threshold_enforced`).
- `corpus/v0/{MANIFEST.md,raw/}` exist after plan 009; `CITEBENCH_SNAPSHOT_ONLY=1`
  ingests them offline.
- `make evals` exists; there is no live/pre-public target.

**Constraints**: CI has no Postgres by default and the repo's tests must not need a
live DB (AGENTS.md). Secrets cannot be used in a job-level `if`; use a gate job
that exposes a step output, then a dependent job with `needs.gate.outputs.*`.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Mock CI | `make evals` | exit 0 (CI + redteam) |
| Local live | `GROQ_API_KEY=<set> make evals-live` | exit 0, `mode=live` |
| Syntax check | `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/eval-ci.yml'))"` | exit 0 |
| API tests | `.venv/bin/python -m pytest apps/api` | all pass |

## Scope

**In scope**:

- `.github/workflows/eval-ci.yml` — gate job + live job (Postgres service, v0 offline ingest).
- `Makefile` — `evals-live` target (big-freeze live run).
- `scripts/local-evals.sh` — confirm `--live` covers CI + redteam (from plan 015).
- `README.md` / `infra/deploy/README.md` — document the pre-public live gate.
- `apps/api/tests/test_eval_ci.py` — a test that the committed `latest.json` is
  `mode=live` when present (guards against committing a mock artifact as live).
- `plans/README.md` status row.

**Out of scope**:

- Ingesting the ~1,000-page freeze in CI (too slow/flaky) — that is the local
  pre-public run.
- Changing the threshold, split content, or the live runner (plans 014/015).
- Adding a second CI provider or a DB artifact cache.
- Making PRs from forks run with secrets (they cannot).

## Git workflow

- Branch: `advisor/016-ci-gate`
- Commit message: `Gate CI on live faithfulness when a Groq key is present.`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Add a secret-gate job

At the top of `jobs:` in `.github/workflows/eval-ci.yml`, add:
```yaml
  gate:
    runs-on: ubuntu-latest
    outputs:
      have_key: ${{ steps.check.outputs.have_key }}
    steps:
      - id: check
        env:
          GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
        run: |
          if [ -n "$GROQ_API_KEY" ]; then echo "have_key=true" >> "$GITHUB_OUTPUT"; else echo "have_key=false" >> "$GITHUB_OUTPUT"; fi
```
(Secrets can be referenced in step `env`, and the output drives the dependent job.)

**Verify**: `python -c "import yaml; yaml.safe_load(open('.github/workflows/eval-ci.yml'))"` → exit 0.

### Step 2: Keep mock CI always-on; drop the dead env var

- In the existing mock steps, remove `CITEBENCH_EVAL_MOCK` (unused), keep
  `--mock` and `--threshold-faithfulness 0.7`.
- Ensure a failure of either mock step fails the workflow (default `set -e`).

**Verify**: `make evals` locally → exit 0.

### Step 3: Add the live job (corpus-v0 path)

Add:
```yaml
  live-eval:
    needs: gate
    if: needs.gate.outputs.have_key == 'true'
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_USER: citebench
          POSTGRES_PASSWORD: citebench
          POSTGRES_DB: citebench
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U citebench" --health-interval 5s
          --health-timeout 5s --health-retries 10
    env:
      DATABASE_URL: postgresql://citebench:citebench@127.0.0.1:5432/citebench
      GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
      CITEBENCH_MANIFEST: corpus/v0/MANIFEST.md
      CITEBENCH_SNAPSHOT_ONLY: "1"
      EVAL_STORE_DIR: ${{ github.workspace }}/evals/results
      TRACE_STORE_DIR: ${{ runner.temp }}/citebench-traces
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -U pip && pip install -r apps/api/requirements.txt -r apps/api/requirements-eval.txt
      - name: Ingest corpus-v0 (offline)
        run: python -c "import sys; sys.path.insert(0,'apps/api'); from settings import load_settings; from pipeline import run_ingest; run_ingest(load_settings(), wipe=True)"
      - name: Live RAGAS gate (v0 split)
        run: |
          python -m citebench.eval.ci \
            --split evals/splits/ci-v0.jsonl \
            --known-bad evals/splits/known_bad.jsonl \
            --threshold-faithfulness 0.7 --live --store-dir evals/results
      - uses: actions/upload-artifact@v4
        if: always()
        with: { name: eval-live, path: evals/results/latest.json, if-no-files-found: warn }
```
This uses a new `evals/splits/ci-v0.jsonl`: 3–4 rows grounded in `corpus-v0`
(`ci-v0-001…`). Create it in this plan; add corresponding `CI_FIXTURES` only if
needed for mock (mock does not run this split, so fixtures are optional).

**Verify**: `python -c "import yaml; yaml.safe_load(open('.github/workflows/eval-ci.yml'))"`;
locally (with a key + Docker Postgres) run the two `run:` commands and confirm
`latest.json` is `mode=live` and the gate passes.

### Step 4: Prove the gate fails closed

Keep `test_faithfulness_threshold_enforced` (already asserts exit != 0 below
threshold). Add `test_committed_live_artifact_is_not_mock`: if
`evals/results/latest.json` exists, assert `payload["mode"] == "live"` and
`payload.get("judge_model")`. This prevents plan 015's artifact from being
silently replaced by a mock run before publish.

**Verify**: `.venv/bin/python -m pytest apps/api/tests/test_eval_ci.py` → pass.

### Step 5: Pre-public live gate docs + Make target

- Add `Makefile` target:
```
evals-live:  ## Live RAGAS + redteam on the full big freeze (required before public tag)
	./scripts/local-evals.sh --live
```
- In `README.md` (Evals section) and `infra/deploy/README.md`, state: before
  tagging a public release, run `make evals-live` on the fully ingested big
  freeze; the committed `latest.json` must be `mode=live` with a `judge_model`.
  Do not publish with a mock artifact.

**Verify**: `.venv/bin/python -m pytest apps/api` → pass; `grep -n "evals-live" Makefile README.md`.

## Test plan

- `test_eval_ci.py`: threshold enforcement (exists), committed-artifact-is-live guard.
- Workflow YAML parses; no secret value is printed anywhere (gate uses `env`, not `run` echo).
- No live key in CI for forks → mock path still runs.
- Verification: `.venv/bin/python -m pytest apps/api` → all pass.

## Done criteria

- [ ] `eval-ci.yml` has a `gate` job and a `live-eval` job gated on
      `needs.gate.outputs.have_key == 'true'`; mock job still runs always.
- [ ] `evals/splits/ci-v0.jsonl` exists (grounded in corpus-v0).
- [ ] Live job ingests `corpus/v0` offline against the pgvector service and runs
      live CI with the 0.7 threshold.
- [ ] Dead `CITEBENCH_EVAL_MOCK` removed.
- [ ] `make evals-live` + README/deploy note require a live run before public tag.
- [ ] `pytest apps/api` exits 0.
- [ ] `plans/README.md` row 016 is DONE.

## STOP conditions

- GitHub Actions cannot access the secret in a way that keeps forks from failing
  — stop and report; do not make the live job required without a gate.
- The pgvector service or offline v0 ingest cannot run in the runner budget —
  stop; do not replace it with a mocked "live" run.
- The full-freeze live run needs the 1,000-page crawl in CI — stop; keep it as
  the documented local pre-public gate instead.
- A workflow change would print `GROQ_API_KEY` — stop and fix before committing.

## Maintenance notes

- Plan 022 (ship) requires the committed live artifact; keep this gate green.
- If the corpus or split changes, update `ci-v0.jsonl` too and re-run locally.
- Reviewers: confirm no secret appears in logs and the live job does not run on
  fork PRs (it should be skipped, not failed).
- Deferred: caching the v0 Postgres/ingest to speed CI is optional and not needed
  at 14 docs.
