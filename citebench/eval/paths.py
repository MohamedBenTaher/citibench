"""Import path bootstrap so eval CI can reach apps/api and Contract A stubs."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
API_DIR = REPO_ROOT / "apps" / "api"
STUBS_DIR = REPO_ROOT / "docs" / "contracts" / "stubs"
DEFAULT_EVAL_STORE = REPO_ROOT / "evals" / "results"
DEFAULT_CI_SPLIT = REPO_ROOT / "evals" / "splits" / "ci.jsonl"
DEFAULT_KNOWN_BAD = REPO_ROOT / "evals" / "splits" / "known_bad.jsonl"

for _path in (str(REPO_ROOT), str(API_DIR), str(STUBS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)
