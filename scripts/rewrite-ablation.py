#!/usr/bin/env python
"""Compare two eval-store runs (rewrite off vs on) and record the decision.

    .venv/bin/python scripts/rewrite-ablation.py --off /tmp/abl-off --on /tmp/abl-on

Reports only: the recorded `decision` is computed mechanically from the plan's
rule, but the keep/delete call stays with the operator.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_OUT = ROOT / "evals" / "results" / "rewrite-ablation.json"
METRICS = ("faithfulness", "context_precision", "answer_relevancy")

FAITHFULNESS_MIN_GAIN = 0.02
PRECISION_TOLERANCE = 0.02
RELEVANCY_TOLERANCE = 0.02


def _read_artifact(path: Path) -> dict | None:
    """Accept a store dir (latest.json) or a direct artifact path."""
    target = path if path.suffix == ".json" else path / "latest.json"
    if not target.is_file():
        return None
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _side(artifact: dict | None, label: str) -> dict:
    if artifact is None:
        return {"missing": True, "detail": f"{label}: artifact not found"}
    return {
        "run_id": artifact.get("run_id"),
        "mode": artifact.get("mode"),
        "judge_model": artifact.get("judge_model") or artifact.get("judge"),
        "started_at": artifact.get("started_at"),
        "metrics": {key: artifact.get("metrics", {}).get(key) for key in METRICS},
    }


def _decide(on: dict | None, off: dict | None) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if on is None or off is None:
        return "incomplete", ["both live runs are required"]
    if on.get("mode") != "live" or off.get("mode") != "live":
        return "incomplete", ["ablation requires mode=live artifacts on both sides"]
    m_off, m_on = off.get("metrics", {}), on.get("metrics", {})
    values = [m_off.get(key) for key in METRICS] + [m_on.get(key) for key in METRICS]
    if None in values:
        return "incomplete", ["missing metric keys in the artifacts"]
    faith_off, prec_off, rele_off = (m_off[key] for key in METRICS)
    faith_on, prec_on, rele_on = (m_on[key] for key in METRICS)
    if faith_on - faith_off < FAITHFULNESS_MIN_GAIN:
        reasons.append(f"faithfulness gain {faith_on - faith_off:.4f} < {FAITHFULNESS_MIN_GAIN}")
    if prec_on < prec_off - PRECISION_TOLERANCE:
        reasons.append(f"context_precision dropped by {prec_off - prec_on:.4f}")
    if rele_on < rele_off - RELEVANCY_TOLERANCE:
        reasons.append(f"answer_relevancy dropped by {rele_off - rele_on:.4f}")
    return ("keep" if not reasons else "delete"), reasons


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Query-rewrite ablation report.")
    parser.add_argument("--off", required=True, help="baseline store dir or live.json")
    parser.add_argument("--on", required=True, help="rewrite-on store dir or live.json")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)

    off_artifact = _read_artifact(Path(args.off))
    on_artifact = _read_artifact(Path(args.on))
    off_side = _side(off_artifact, "off")
    on_side = _side(on_artifact, "on")
    decision, reasons = _decide(on_artifact, off_artifact)

    payload = {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "measured_under": "rewrite-ablation-live-compare",
        "rule": {
            "faithfulness_min_gain": FAITHFULNESS_MIN_GAIN,
            "context_precision_tolerance": PRECISION_TOLERANCE,
            "answer_relevancy_tolerance": RELEVANCY_TOLERANCE,
        },
        "rewrite_off": off_side,
        "rewrite_on": on_side,
        "decision": decision,
        "reasons": reasons,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"decision={decision}" + (f" ({'; '.join(reasons)})" if reasons else ""))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
