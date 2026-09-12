"""Collect live answers + retrieved context texts for the eval split.

Runs in the RUNTIME env (`.venv`) because it uses Citebench's real generate()
and retrieve(). It writes one JSON object per row (answer, abstain flag,
citation pointers, and the retrieved chunk TEXTS). The separate eval env then
scores that file with RAGAS (see citebench/eval/live_score.py).

Usage:
    python -m citebench.eval.answers --out /tmp/citebench-run/answers.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import citebench.eval.paths  # noqa: F401  # sys.path for the API modules

from citebench.eval.loader import load_eval_jsonl
from generate import generate
from retrieve import retrieve
from settings import load_settings

DEFAULT_SPLIT = "evals/splits/ci.jsonl"
DEFAULT_KNOWN_BAD = "evals/splits/known_bad.jsonl"


def collect_one(question: str, settings: Any) -> dict[str, Any]:
    hits = retrieve(question, settings=settings)
    contexts = [hit.text for hit in hits if hit.text]
    result = generate(question, settings=settings)
    return {
        "answer": result.answer,
        "abstained": bool(result.abstained),
        "abstain_reason": result.abstain_reason,
        "citations": [ref.model_dump() for ref in result.citations],
        "contexts": contexts,
        "run_id": result.run_id,
        "model": result.model,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect live answers for RAGAS scoring.")
    parser.add_argument("--split", default=DEFAULT_SPLIT)
    parser.add_argument("--known-bad", default=DEFAULT_KNOWN_BAD)
    parser.add_argument("--out", required=True)
    parser.add_argument("--limit", type=int, default=0, help="0 = all rows")
    args = parser.parse_args(argv)

    settings = load_settings()
    if not settings.groq_api_key:
        print("GROQ_API_KEY is required to collect live answers", file=sys.stderr)
        return 2

    rows = load_eval_jsonl(args.split) + load_eval_jsonl(args.known_bad)
    if args.limit:
        rows = rows[: args.limit]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    collected = 0
    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            record: dict[str, Any] = {
                "id": row.id,
                "question": row.question,
                "expected": row.expected,
                "must_cite": row.must_cite,
                "abstain": row.abstain,
                "known_bad": row.known_bad,
                "tags": list(row.tags),
            }
            try:
                record.update(collect_one(row.question, settings))
            except Exception as exc:  # noqa: BLE001 - record and continue
                record.update(
                    {
                        "answer": "",
                        "abstained": False,
                        "abstain_reason": None,
                        "citations": [],
                        "contexts": [],
                        "run_id": "",
                        "model": "",
                        "error": str(exc),
                    }
                )
            handle.write(json.dumps(record) + "\n")
            handle.flush()
            collected += 1
            preview = str(record.get("answer", ""))[:64].replace("\n", " ")
            print(
                f"{row.id}: abstained={record.get('abstained')} "
                f"cites={len(record.get('citations') or [])} answer={preview!r}",
                flush=True,
            )

    print(f"wrote {collected} rows to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
