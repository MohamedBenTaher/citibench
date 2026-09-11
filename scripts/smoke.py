#!/usr/bin/env python
"""Offline corpus-v0 smoke loop: ingest from disk, then run mock evals.

Requires CITEBENCH_SNAPSHOT_ONLY=1 and DATABASE_URL pointing at a scratch DB
(see `make smoke`). Never fetches the network for documents.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "apps" / "api"
sys.path.insert(0, str(API_DIR))

from pipeline import run_ingest  # noqa: E402
from settings import load_settings  # noqa: E402


def _eval_store() -> Path:
    default = Path(os.environ.get("TMPDIR", "/tmp")) / "citebench-smoke" / "evals"
    store = Path(os.environ.get("EVAL_STORE_DIR", str(default)))
    store.mkdir(parents=True, exist_ok=True)
    return store


def main() -> int:
    settings = load_settings()
    if not settings.snapshot_only:
        print(
            "refusing to run: set CITEBENCH_SNAPSHOT_ONLY=1 so smoke never fetches "
            "documents from the network.",
            file=sys.stderr,
        )
        return 2

    print(f"manifest: {settings.manifest_path}")
    print(f"database: {settings.database_url}")
    stats = run_ingest(settings, wipe=True)
    print(
        "ingest:",
        f"status={stats.get('run_status')}",
        f"docs={stats.get('doc_count')}",
        f"pages={stats.get('page_count')}",
        f"chunks={stats.get('chunk_count')}",
    )
    if stats.get("run_status") != "ok":
        print(f"smoke failed: ingest not clean: {stats.get('run_error')}", file=sys.stderr)
        return 1

    env = dict(os.environ)
    env["PYTHONPATH"] = f"{ROOT}:{API_DIR}"
    env["EVAL_STORE_DIR"] = str(_eval_store())
    env.setdefault("TRACE_STORE_DIR", str(Path(os.environ.get("TMPDIR", "/tmp")) / "citebench-smoke" / "traces"))

    commands = [
        [
            sys.executable, "-m", "citebench.eval.ci",
            "--split", "evals/splits/ci.jsonl",
            "--known-bad", "evals/splits/known_bad.jsonl",
            "--threshold-faithfulness", "0.7",
            "--mock",
            "--store-dir", env["EVAL_STORE_DIR"],
        ],
        [
            sys.executable, "-m", "citebench.eval.redteam",
            "--split", "evals/redteam.jsonl",
            "--mock",
            "--store-dir", env["EVAL_STORE_DIR"],
        ],
    ]
    for command in commands:
        print("+", " ".join(command))
        result = subprocess.run(command, cwd=ROOT, env=env)
        if result.returncode != 0:
            return result.returncode
    print("smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
