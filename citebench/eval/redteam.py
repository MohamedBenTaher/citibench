"""C8 redteam runner: Contract A rows with attack_type + expect_block."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

from citebench.eval.asserts import naive_success_assert
from citebench.eval.ci import resolve_mode
from citebench.eval.loader import REDTEAM_ATTACK_TYPES, EvalRow, load_eval_jsonl
from citebench.eval.paths import DEFAULT_REDTEAM
from citebench.eval.pipeline import AnswerFn, EvalAnswer, live_answer, mock_answer_fn_for_rows
from citebench.eval.store import resolve_eval_store_dir
from citebench.eval.traces import emit_row_trace

REQUIRED_CASE_COUNT = 10


@dataclass
class RedteamRowResult:
    id: str
    run_id: str
    attack_type: str
    expect_block: bool
    blocked: bool
    passed: bool
    abstained: bool
    answer: str


@dataclass
class RedteamReport:
    run_id: str
    started_at: datetime
    finished_at: datetime
    split: str
    mode: str
    exit_code: int
    loader_error: str | None
    passed: int
    failed: int
    blocked: int
    rows: list[RedteamRowResult] = field(default_factory=list)
    gate_reason: str | None = None
    failing_run_ids: list[str] = field(default_factory=list)

    def to_artifact(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "split": self.split,
            "mode": self.mode,
            "framework": "redteam",
            "gate_passed": self.exit_code == 0,
            "gate_reason": self.gate_reason,
            "loader_error": self.loader_error,
            "case_count": len(self.rows),
            "passed": self.passed,
            "failed": self.failed,
            "blocked": self.blocked,
            "rows": [
                {
                    "id": row.id,
                    "run_id": row.run_id,
                    "attack_type": row.attack_type,
                    "expect_block": row.expect_block,
                    "blocked": row.blocked,
                    "passed": row.passed,
                    "abstained": row.abstained,
                }
                for row in self.rows
            ],
            "failing_run_ids": self.failing_run_ids,
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m citebench.eval.redteam")
    parser.add_argument(
        "--split",
        default=str(DEFAULT_REDTEAM),
        help="Redteam JSONL (Contract A + attack_type/expect_block)",
    )
    parser.add_argument("--output", default="", help="Write redteam.json here")
    parser.add_argument(
        "--store-dir",
        default="",
        help="Eval result store (redteam.json lives next to latest.json)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Reuse generate/abstain with empty retrieve (no Groq)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Call live generate (requires GROQ_API_KEY and an ingested index)",
    )
    return parser


def validate_redteam_split(rows: list[EvalRow]) -> None:
    if len(rows) != REQUIRED_CASE_COUNT:
        raise ValueError(
            f"redteam split must contain exactly {REQUIRED_CASE_COUNT} cases, got {len(rows)}"
        )
    types = {row.attack_type for row in rows}
    missing = REDTEAM_ATTACK_TYPES - types
    if missing:
        raise ValueError(f"redteam split must mix attack types; missing {sorted(missing)}")
    for row in rows:
        if "redteam" not in row.tags:
            raise ValueError(f"{row.id}: tags must include redteam")
        if row.attack_type not in REDTEAM_ATTACK_TYPES:
            raise ValueError(f"{row.id}: invalid attack_type")
        if row.expect_block is None:
            raise ValueError(f"{row.id}: expect_block is required")


def row_blocked(row: EvalRow, answer: EvalAnswer) -> bool:
    """A block is an abstain with no concrete answer and no citations."""
    return not naive_success_assert(row, answer)


def run_redteam(
    *,
    split: str | Path | None = None,
    store_dir: str | Path | None = None,
    mock: bool = False,
    live: bool = False,
    answer_fn: AnswerFn | None = None,
) -> RedteamReport:
    started = datetime.now(timezone.utc)
    run_id = f"redteam-{uuid4().hex[:12]}"
    dest = resolve_eval_store_dir(store_dir)
    split_path = str(split or DEFAULT_REDTEAM)
    mode = "mock"
    loader_error: str | None = None
    rows_out: list[RedteamRowResult] = []
    failing: list[str] = []
    gate_reason: str | None = None
    exit_code = 1

    try:
        mode = resolve_mode(mock=mock, live=live)
    except ValueError as exc:
        return _finish(
            run_id,
            started,
            split_path,
            mode,
            dest,
            exit_code=2,
            loader_error=str(exc),
            rows_out=[],
            failing=[],
            gate_reason=str(exc),
        )

    if mode == "live" and not os.environ.get("GROQ_API_KEY", "").strip() and answer_fn is None:
        loader_error = "GROQ_API_KEY is required for --live redteam"
        return _finish(
            run_id,
            started,
            split_path,
            mode,
            dest,
            exit_code=2,
            loader_error=loader_error,
            rows_out=[],
            failing=[],
            gate_reason=loader_error,
        )

    try:
        rows = load_eval_jsonl(split_path)
        validate_redteam_split(rows)
    except Exception as exc:
        return _finish(
            run_id,
            started,
            split_path,
            mode,
            dest,
            exit_code=2,
            loader_error=str(exc),
            rows_out=[],
            failing=[],
            gate_reason=f"loader error: {exc}",
        )

    answerer = answer_fn or (_default_answerer(mode, rows))
    for row in rows:
        answer = answerer(row.question, row.id)
        blocked = row_blocked(row, answer)
        expect_block = bool(row.expect_block)
        passed = blocked if expect_block else not blocked
        if not passed:
            failing.append(answer.run_id)
            emit_row_trace(answer, failed=True, reason="redteam_expect_block_missed")
        rows_out.append(
            RedteamRowResult(
                id=row.id,
                run_id=answer.run_id,
                attack_type=str(row.attack_type),
                expect_block=expect_block,
                blocked=blocked,
                passed=passed,
                abstained=answer.abstained,
                answer=answer.answer,
            )
        )

    failed = len(failing)
    passed_n = len(rows_out) - failed
    blocked_n = sum(1 for row in rows_out if row.blocked)
    if failed:
        gate_reason = f"{failed} of {len(rows_out)} redteam cases leaked"
        exit_code = 1
    else:
        gate_reason = "ok"
        exit_code = 0

    return _finish(
        run_id,
        started,
        split_path,
        mode,
        dest,
        exit_code=exit_code,
        loader_error=None,
        rows_out=rows_out,
        failing=failing,
        gate_reason=gate_reason,
        passed=passed_n,
        failed=failed,
        blocked=blocked_n,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = run_redteam(
        split=args.split,
        store_dir=args.store_dir or None,
        mock=args.mock,
        live=args.live,
    )
    dest = resolve_eval_store_dir(args.store_dir or None)
    artifact = dest / "redteam.json"
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(
            artifact.read_text(encoding="utf-8") if artifact.is_file() else "",
            encoding="utf-8",
        )
    print(
        f"citebench.eval.redteam mode={report.mode} exit={report.exit_code} "
        f"passed={report.passed}/{len(report.rows)} blocked={report.blocked} "
        f"reason={report.gate_reason}",
        file=sys.stderr,
    )
    return report.exit_code


def read_redteam_artifact(store_dir: str | Path | None = None) -> dict[str, Any] | None:
    path = resolve_eval_store_dir(store_dir) / "redteam.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _default_answerer(mode: str, rows: list[EvalRow]) -> AnswerFn:
    if mode == "live":
        return live_answer
    return mock_answer_fn_for_rows(rows)


def _finish(
    run_id: str,
    started: datetime,
    split: str,
    mode: str,
    dest: Path,
    *,
    exit_code: int,
    loader_error: str | None,
    rows_out: list[RedteamRowResult],
    failing: list[str],
    gate_reason: str | None,
    passed: int | None = None,
    failed: int | None = None,
    blocked: int | None = None,
) -> RedteamReport:
    report = RedteamReport(
        run_id=run_id,
        started_at=started,
        finished_at=datetime.now(timezone.utc),
        split=split,
        mode=mode,
        exit_code=exit_code,
        loader_error=loader_error,
        passed=passed if passed is not None else sum(1 for row in rows_out if row.passed),
        failed=failed if failed is not None else len(failing),
        blocked=blocked if blocked is not None else sum(1 for row in rows_out if row.blocked),
        rows=rows_out,
        gate_reason=gate_reason,
        failing_run_ids=failing,
    )
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "redteam.json").write_text(
        json.dumps(report.to_artifact(), indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return report


if __name__ == "__main__":
    raise SystemExit(main())
