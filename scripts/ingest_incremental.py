#!/usr/bin/env python
"""Incremental offline ingest: small batches, resumable, commits per document.

Intended to run in the background (see scripts/ingest-bg.sh). Each cycle
processes at most `--batch` not-yet-indexed documents and exits, so stopping
the process at any time never loses committed work. Re-running resumes.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from citebench_api.ingest.pipeline import run_ingest  # noqa: E402
from citebench_api.config import load_settings  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Incrementally ingest the frozen corpus.")
    parser.add_argument("--batch", type=int, default=15, help="documents per cycle")
    parser.add_argument("--cycle-pause", type=float, default=10.0, help="seconds between cycles")
    parser.add_argument("--max-batches", type=int, default=0, help="0 = until done")
    parser.add_argument("--once", action="store_true", help="run a single batch then exit")
    args = parser.parse_args(argv)

    settings = load_settings()
    if not settings.snapshot_only:
        print("refusing: set CITEBENCH_SNAPSHOT_ONLY=1 (offline ingest only)", file=sys.stderr)
        return 2
    print(
        f"manifest={settings.manifest_path} batch={args.batch} "
        f"threads={os.environ.get('FASTEMBED_THREADS', 'default')}",
        flush=True,
    )

    batches = 0
    while True:
        stats = run_ingest(settings, only_missing=True, limit=args.batch)
        batches += 1
        print(
            f"[{time.strftime('%H:%M:%S')}] batch {batches}: "
            f"processed={stats['processed_count']} failed={stats['failed_count']} "
            f"pending={stats['pending_after']} docs_ok={stats['doc_count']} "
            f"pages={stats['page_count']} chunks={stats['chunk_count']}",
            flush=True,
        )
        if args.once or stats["processed_count"] == 0 or stats["pending_after"] == 0:
            break
        if args.max_batches and batches >= args.max_batches:
            break
        time.sleep(args.cycle_pause)

    print(f"done: batches={batches}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
