"""Eval artifacts: /evals/latest, /evals/retrieval(+run), /evals/redteam."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()


def _read_json_object(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _load_redteam_cases(path: Path) -> list[dict[str, Any]]:
    """Read Contract A redteam JSONL without requiring the citebench package."""
    rows: list[dict[str, Any]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict) or not payload.get("id"):
            raise ValueError(f"{path}:{line_no}: redteam row must be an object with id")
        rows.append(
            {
                "id": payload["id"],
                "question": payload.get("question"),
                "expected": payload.get("expected"),
                "attack_type": payload.get("attack_type"),
                "expect_block": payload.get("expect_block"),
                "tags": list(payload.get("tags") or []),
            }
        )
    return rows


def _redteam_jsonl_path() -> Path:
    env = os.environ.get("REDTEAM_JSONL", "").strip()
    if env:
        return Path(env)
    for candidate in (
        Path("/app/evals/redteam.jsonl"),
        Path(__file__).resolve().parents[2] / "evals" / "redteam.jsonl",
        Path("evals/redteam.jsonl"),
    ):
        if candidate.is_file():
            return candidate
    return Path("/app/evals/redteam.jsonl")


def _eval_store_dir() -> Path:
    env = os.environ.get("EVAL_STORE_DIR", "").strip()
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    if len(here.parents) > 2:
        candidate = here.parents[2] / "evals" / "results"
        if candidate.is_dir() or candidate.parent.is_dir():
            return candidate
    return Path("/tmp/citebench-evals")


@router.get("/evals/latest")
def get_evals_latest() -> dict[str, Any]:
    path = _eval_store_dir() / "latest.json"
    if not path.is_file():
        return {
            "present": False,
            "metrics": None,
            "previous": None,
            "diff": None,
            "detail": "no eval run yet",
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail=f"eval artifact unreadable: {exc}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=500, detail="eval artifact must be an object")
    payload["present"] = True
    return payload


@router.get("/evals/retrieval")
def get_evals_retrieval() -> dict[str, Any]:
    """Objective retrieval metrics + answerability calibration (qrels artifact)."""
    path = _eval_store_dir() / "retrieval.json"
    if not path.is_file():
        return {"present": False, "detail": "no retrieval run yet"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail=f"retrieval artifact unreadable: {exc}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=500, detail="retrieval artifact must be an object")
    payload["present"] = True
    return payload


_retrieval_run_lock = threading.Lock()


@router.post("/evals/retrieval/run")
def post_retrieval_run(
    compare: bool = Query(default=True, description="score config variants too"),
) -> dict[str, Any]:
    """Run the retrieval evaluation and refresh the artifact (local, no LLM)."""
    if not _retrieval_run_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="retrieval run already in progress")
    try:
        out = _eval_store_dir() / "retrieval.json"
        command = [
            sys.executable,
            "-m",
            "citebench.eval.retrieval",
            "--out",
            str(out),
        ]
        if compare:
            command.append("--compare")
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=1800,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(status_code=504, detail="retrieval run timed out") from exc
        if completed.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"retrieval run failed: {completed.stderr[-600:]}",
            )
        payload = _read_json_object(out) or {}
        payload["present"] = True
        return payload
    finally:
        _retrieval_run_lock.release()


@router.get("/evals/redteam")
def get_evals_redteam() -> dict[str, Any]:
    """Last redteam run plus the 10 committed cases. Public; no login wall."""
    store = _eval_store_dir()
    artifact = _read_json_object(store / "redteam.json")
    cases: list[dict[str, Any]] = []
    split_error: str | None = None
    path = _redteam_jsonl_path()
    split_path = str(path)
    try:
        if path.is_file():
            cases = _load_redteam_cases(path)
        else:
            split_error = f"redteam split not found: {path}"
    except Exception as exc:
        split_error = str(exc)
    by_id = {
        row["id"]: row
        for row in (artifact or {}).get("rows", [])
        if isinstance(row, dict) and row.get("id")
    }
    merged = []
    for case in cases:
        run = by_id.get(case["id"], {})
        merged.append({**case, **{k: run[k] for k in ("run_id", "blocked", "passed", "abstained") if k in run}})
    return {
        "present": artifact is not None,
        "split": split_path,
        "case_count": len(cases),
        "cases": merged,
        "run": artifact,
        "detail": split_error,
    }
