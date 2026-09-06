"""Contract A JSONL loader. Invalid rows fail the load; they are not skipped."""

from __future__ import annotations

import citebench.eval.paths  # noqa: F401  # sys.path for contract stubs

from schemas import EvalRow, REDTEAM_ATTACK_TYPES, load_eval_jsonl

__all__ = ["EvalRow", "REDTEAM_ATTACK_TYPES", "load_eval_jsonl"]
