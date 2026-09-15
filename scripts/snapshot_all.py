#!/usr/bin/env python
"""Fetch every MANIFEST snapshot to disk with retries + resume (no DB, no embed).

Re-run to resume: existing snapshots are skipped. Aborts early on repeated
network failure so a re-run can pick up where this one stopped.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from citebench_api.ingest.manifest import parse_manifest  # noqa: E402
from citebench_api.config import load_settings  # noqa: E402
from citebench_api.ingest.snapshot import (  # noqa: E402
    SnapshotError,
    build_http_client,
    load_snapshot,
    snapshot_url,
)

MAX_CONSECUTIVE_FAILURES = 8


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Snapshot the manifest corpus to disk.")
    parser.add_argument("--manifest", default="")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--delay", type=float, default=0.05)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args(argv)

    settings = load_settings()
    manifest = Path(args.manifest) if args.manifest else settings.manifest_path
    docs = parse_manifest(manifest)
    if args.limit:
        docs = docs[: args.limit]
    raw_root = manifest.parent / "raw"
    raw_root.mkdir(parents=True, exist_ok=True)

    already = 0
    fetched = 0
    missing: list[tuple[str, str]] = []
    consecutive = 0

    with build_http_client() as client:
        for index, doc in enumerate(docs, start=1):
            try:
                load_snapshot(raw_root=raw_root, doc_id=doc.id)
                already += 1
                consecutive = 0
                continue
            except SnapshotError:
                pass

            ok = False
            last_error = ""
            for attempt in range(args.retries):
                try:
                    snapshot_url(
                        doc_id=doc.id,
                        source_url=doc.source_url,
                        raw_root=raw_root,
                        client=client,
                    )
                    ok = True
                    fetched += 1
                    break
                except SnapshotError as exc:
                    last_error = str(exc)
                    if attempt < args.retries - 1:
                        time.sleep(0.5 * (2**attempt))

            if ok:
                consecutive = 0
            else:
                missing.append((doc.id, last_error))
                consecutive += 1
                if consecutive >= MAX_CONSECUTIVE_FAILURES:
                    print(
                        f"STOP: {consecutive} consecutive failures; re-run to resume "
                        f"(last: {last_error})",
                        file=sys.stderr,
                    )
                    break

            if index % 100 == 0:
                print(
                    f"{index}/{len(docs)} already={already} fetched={fetched} "
                    f"missing={len(missing)}",
                    flush=True,
                )
            time.sleep(args.delay)

    print(f"total={len(docs)} already={already} fetched={fetched} missing={len(missing)}")
    for doc_id, error in missing[:20]:
        print(f"MISSING {doc_id}: {error}", file=sys.stderr)
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
