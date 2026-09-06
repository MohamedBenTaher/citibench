"""Persist last / previous CI score artifacts for the Evals tab."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from citebench.eval.paths import DEFAULT_EVAL_STORE, REPO_ROOT


def resolve_eval_store_dir(explicit: str | Path | None = None) -> Path:
    if explicit:
        return Path(explicit)
    env = os.environ.get("EVAL_STORE_DIR", "").strip()
    if env:
        return Path(env)
    if DEFAULT_EVAL_STORE.exists() or (REPO_ROOT / "evals").is_dir():
        return DEFAULT_EVAL_STORE
    return Path("/tmp/citebench-evals")


def read_latest(store_dir: Path) -> dict[str, Any] | None:
    path = store_dir / "latest.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def read_previous(store_dir: Path) -> dict[str, Any] | None:
    path = store_dir / "previous.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def write_report(report: Any, store_dir: str | Path) -> Path:
    dest = Path(store_dir)
    dest.mkdir(parents=True, exist_ok=True)
    latest_path = dest / "latest.json"
    previous_path = dest / "previous.json"
    incoming = report.to_artifact()
    existing = read_latest(dest)
    if existing and existing.get("run_id") and existing.get("run_id") != incoming.get("run_id"):
        previous_path.write_text(
            json.dumps(existing, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
    previous = read_previous(dest)
    incoming["previous"] = _metric_view(previous) if previous else None
    incoming["diff"] = _diff(_metric_view(incoming), incoming["previous"]) if previous else None
    latest_path.write_text(json.dumps(incoming, indent=2, default=str) + "\n", encoding="utf-8")
    return latest_path


def _metric_view(payload: dict[str, Any] | None) -> dict[str, float] | None:
    if not payload:
        return None
    metrics = payload.get("metrics")
    if not isinstance(metrics, dict):
        return None
    return {
        "faithfulness": float(metrics.get("faithfulness") or 0.0),
        "context_precision": float(metrics.get("context_precision") or 0.0),
        "answer_relevancy": float(metrics.get("answer_relevancy") or 0.0),
    }


def _diff(
    current: dict[str, float] | None,
    previous: dict[str, float] | None,
) -> dict[str, float] | None:
    if not current or not previous:
        return None
    return {key: current[key] - previous[key] for key in current}
