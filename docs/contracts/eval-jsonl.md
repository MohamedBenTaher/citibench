# Contract A — Eval JSONL

C1 ships the schema, the known-bad split, and stubs. RAGAS execution is C2+.
Do not invent extra fields in loaders without a decision-trail row.

## Paths

| Path | Role |
| --- | --- |
| `evals/splits/known_bad.jsonl` | Anti-theater split. Required in C1. |
| `evals/splits/dev.jsonl` | Future development split. Absent in C1. |
| `evals/splits/test.jsonl` | Future held-out split. Absent in C1. |
| `docs/contracts/stubs/schemas.py` | `EvalRow`, `load_eval_jsonl` |

One JSON object per line. UTF-8. No trailing comma. Duplicate `id` values
inside a file are invalid.

## Fields

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `id` | string | yes | Stable row id (`bad-001`, later `dev-…`). Non-empty. Unique per file. |
| `question` | string | yes | User question as asked. Non-empty. No retrieved context. |
| `expected` | string | yes | Grader-facing expected behavior, not a gold essay. |
| `must_cite` | bool | yes | If true, a passing answer must include at least one `ChunkRef`. |
| `abstain` | bool | yes | If true, the system must refuse; any concrete answer fails. |
| `known_bad` | bool | yes | If true, the question is outside the freeze by construction. |
| `tags` | list[string] | yes | Free-form labels. Empty list is valid. |

Unknown keys are ignored by the loader but must not be required for a pass.
Do not store retrieved chunks, model output, or RAGAS scores on the row.

## Invariants

1. `id` matches `^[A-Za-z0-9][A-Za-z0-9._-]*$` and is unique in the file.
2. `question` and `expected` are stripped; empty strings are rejected.
3. If `known_bad` is true, `abstain` must be true.
4. If `abstain` is true, `must_cite` must be false.
5. `tags` contains no empty strings and no duplicates.
6. A `known_bad` row must not require a `corpus/MANIFEST.md` id as evidence.

`EvalRow` in `schemas.py` enforces 1–5. Loaders must not skip invalid rows.

## Known-bad phase (anti-theater)

Before any RAGAS metric is computed, the runner must execute
`evals/splits/known_bad.jsonl` in full.

- Required behavior: abstain. No password, no payroll summary, no invented
  citation to a phantom internal doc.
- Failure: any concrete answer, any fabricated cite, or a generate span
  without an abstain span.
- Purpose: a pipeline that always answers cannot post a 0.7 faithfulness
  score and call itself grounded.

C1 does not run this phase. The file is present so C2 cannot “forget” it.

## RAGAS and the 0.7 CI gate

C6 CI entrypoint:

```
python -m citebench.eval.ci --split evals/splits/ci.jsonl --known-bad evals/splits/known_bad.jsonl --threshold-faithfulness 0.7
```

Gate: mean RAGAS **faithfulness >= 0.7**. That number is a threshold, not a
published Citebench score. README must not display a fabricated 0.7 result.
The Evals tab may show the last real CI artifact.

Companion metrics may be logged; they do not gate CI. Faithfulness is
computed only on non-abstain rows. Known-bad rows use the abstain rule.

## Loaders

```
load_eval_jsonl(path: str) -> list[EvalRow]
```

Reads JSONL, validates each line as `EvalRow`, rejects duplicates. C1 stub
raises `NotImplementedError`. Do not implement ingest or retrieve here.
