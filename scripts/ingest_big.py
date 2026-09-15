#!/usr/bin/env python
"""Offline ingest of the frozen manifest from on-disk snapshots (no network)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from citebench_api.ingest.pipeline import run_ingest  # noqa: E402
from citebench_api.config import load_settings  # noqa: E402


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes"}


def main() -> int:
    settings = load_settings()
    if not settings.snapshot_only:
        print("refusing: set CITEBENCH_SNAPSHOT_ONLY=1 (offline ingest only)", file=sys.stderr)
        return 2
    resume = _flag("CITEBENCH_INGEST_RESUME")
    print(f"manifest: {settings.manifest_path}", flush=True)
    print(f"database: {settings.database_url}", flush=True)
    print(f"resume: {resume}", flush=True)
    stats = run_ingest(settings, wipe=not resume, only_missing=resume)
    summary = {
        key: stats.get(key)
        for key in ("run_status", "doc_count", "page_count", "chunk_count", "user_doc_count")
    }
    print(f"stats: {summary}", flush=True)
    failures = stats.get("failures", [])
    print(f"failures: {len(failures)}", flush=True)
    for row in failures[:10]:
        print(f"  FAIL {row['id']}: {row['error']}", flush=True)
    return 0 if stats.get("run_status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
