"""One-time fetch of the corpus-v0 smoke corpus (14 URLs) into corpus/v0/raw/."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from citebench_api.ingest.manifest import parse_manifest
from citebench_api.ingest.snapshot import SnapshotError, build_http_client, snapshot_url

DEFAULT_MANIFEST = Path(__file__).resolve().parents[2] / "corpus" / "v0" / "MANIFEST.md"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Snapshot corpus-v0 offline.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    args = parser.parse_args(argv)

    manifest_path = Path(args.manifest)
    docs = parse_manifest(manifest_path)
    raw_root = manifest_path.parent / "raw"
    raw_root.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    with build_http_client() as client:
        for doc in docs:
            try:
                result = snapshot_url(
                    doc_id=doc.id,
                    source_url=doc.source_url,
                    raw_root=raw_root,
                    client=client,
                )
            except SnapshotError as exc:
                failures.append(doc.id)
                print(f"FAIL {doc.id}: {exc}", file=sys.stderr)
                continue
            print(f"ok   {doc.id}  {result.sha256}  {result.bytes_len} bytes  {result.filename}")

    print(f"\n{len(docs) - len(failures)}/{len(docs)} snapshots written to {raw_root}")
    if failures:
        print(f"failed: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
