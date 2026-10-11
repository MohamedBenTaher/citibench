# Plan 021: Public repo/demo hygiene — topics, licenses, and no secrets in git

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**:
> `git diff --stat 028fa3e..HEAD -- README.md .gitignore infra/deploy README.md .env.example docker-compose.yml`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: MED (visibility change and secret scanning are sensitive)
- **Depends on**: plan 016 (green CI gate)
- **Category**: direction (I4 / S1)
- **Planned at**: commit `028fa3e`, 2026-09-10

## Why this matters

The bench is not shipped until it is public and safe to publish. "Public" means
either the repository is public or a demo URL exists; "safe" means no
credentials, tokens, or internal data are in the working tree or git history, and
the corpus licenses are clearly separated from the code license. No invented demo
URL, ever.

## Current state

- `.gitignore` already ignores `.env`, `.venv/`, `pgdata/`, `apps/web/.output/`,
  and `corpus/raw/*` (plan 009 adds `corpus/v0/raw` as an exception).
- `.env.example` documents `GROQ_API_KEY=`, `LANGFUSE_*`, `DEMO_PASSWORD=citebench`
  with placeholder values only.
- `docker-compose.yml` and `infra/deploy/` must contain no real keys; the demo
  password default `citebench` is documented as a throwaway.
- `README.md` says "No public URL ships with the repo" (`:201`) and
  `infra/deploy/try-provision.sh` is runbook-only.
- There is **no** `LICENSE` file in the repo root.
- Repo visibility + topics are GitHub settings, not repo files.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Tracked-file secret scan | `gitleaks detect --source . --no-git` (or `trufflehog filesystem .`) | no verified secrets |
| History scan | `gitleaks detect --source .` | no verified secrets |
| Env not tracked | `git ls-files .env .env.local` | empty output |
| Visibility (operator) | `gh repo view --json visibility` | current value |
| Topics | `gh repo edit --add-topic …` | exit 0 |

## Scope

**In scope**:

- Root `LICENSE` (**create**, MIT for the code) + a `NOTICE`/README note that
  corpus documents keep their own licenses (CC BY 4.0, PostgreSQL, MIT, OSTEP).
- `README.md` — badge, license section, "no secrets" statement.
- `infra/deploy/README.md`, `try-provision.sh` — confirm no invented URL/credentials.
- GitHub topics + repo description (via `gh`, operator-confirmed).
- `plans/README.md` status row.

**Out of scope**:

- Rewriting git history or force-pushing — if a secret is found, **stop and
  report**; rotation + history purge is an operator action.
- Changing repo visibility without explicit operator confirmation.
- Deploying a live demo (no credentials assumed).
- Changing the corpus licenses.

## Git workflow

- Branch: `advisor/021-public-hygiene`
- Commit message: `Prepare the repo for public release.`
- Do NOT push, publish, or change visibility unless the operator explicitly asks.
- Never print a secret value; reference `file:line` + credential type only.

## Steps

### Step 1: Secret scan (working tree + history)

Run the scans above. Also `git grep -n -I -E 'gsk_[A-Za-z0-9]{20,}|sk-lf-[A-Za-z0-9-]{10,}|BEGIN (RSA|OPENSSH|EC) PRIVATE KEY'`
across tracked files. If anything verifies, STOP: report `file:line`, credential
type, and recommended rotation; do not print the value.

**Verify**: both gitleaks runs report no verified secrets; `git ls-files .env`
empty.

### Step 2: LICENSE + corpus attribution

Add root `LICENSE` (MIT, current year, "Citebench contributors"). In `README.md`
add a short "License" section: code is MIT; each corpus document retains its
source license and is snapshotted under `corpus/MANIFEST.md` with the `license`
column; the bench does not redistribute pirated material.

**Verify**: `ls LICENSE`; `grep -n "## License" README.md`.

### Step 3: README public-facing polish

- Add a CI status badge (uses the workflow name from plan 016).
- Add topics: `retrieval`, `rag`, `ragas`, `pgvector`, `fastapi`, `tanstack-start`,
  `evaluation`, `citations` (via `gh repo edit --add-topic …`, operator-confirmed).
- Confirm the README's Deploy section still says no URL ships and points at
  `infra/deploy/README.md`.

**Verify**: `grep -n "badge\|shields.io" README.md`; `gh repo view --json repositoryTopics` (operator).

### Step 4: Visibility / demo decision

If the operator wants a **public repo**: run
`gh repo edit --visibility public --accept-visibility-change-consequences` only
after explicit confirmation. If they want a **public demo** instead, confirm the
deploy runbook produced a real URL and add it to the README top and `infra/deploy/README.md`.
If neither is available, record the decision as BLOCKED in `plans/README.md` with
the reason — do not invent a URL.

**Verify**: `gh repo view --json visibility,url` shows the chosen state (or the
row is BLOCKED).

## Test plan

- No code tests. Gates are the two gitleaks runs and `git ls-files .env`.
- Verification: `pytest apps/api` still passes (no code changed).

## Done criteria

- [ ] No verified secrets in tree or history; `.env` untracked.
- [ ] Root `LICENSE` exists (MIT for code) + README License/corpus attribution.
- [ ] README badge + topics set (or row BLOCKED with a reason).
- [ ] Visibility/demo decision recorded; no invented URL.
- [ ] `plans/README.md` row 021 is DONE or BLOCKED.

## STOP conditions

- Any verified secret — stop, report location/type, recommend rotation; do not
  print the value and do not rewrite history yourself.
- Making the repo public is not explicitly authorized — stop; leave it private
  and record the plan as BLOCKED.
- The only way to "have a demo" is to invent a URL — stop; do not.

## Maintenance notes

- Plan 022 adds the screenshot + blurb once this lands.
- Reviewers: re-run gitleaks on each PR; never commit `.env`.
- Deferred: history purge tooling (BFG/filter-repo) if a secret is found later.
