"""C6 CI gate: known-bad fail-closed, then RAGAS faithfulness >= 0.7."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

from citebench.eval.asserts import naive_success_assert, required_assert_failed
from citebench.eval.loader import EvalRow, load_eval_jsonl
from citebench.eval.pipeline import AnswerFn, EvalAnswer, live_answer, mock_answer_fn_for_rows
from citebench.eval.ragas_metrics import RagasScores, mean_scores, score_row
from citebench.eval.store import resolve_eval_store_dir, write_report
from citebench.eval.traces import emit_row_trace


@dataclass
class KnownBadRowResult:
    id: str
    run_id: str
    required_assert_failed: bool
    answer: str
    abstained: bool


@dataclass
class KnownBadPhase:
    clean: bool
    rows: list[KnownBadRowResult] = field(default_factory=list)


@dataclass
class SplitRowResult:
    id: str
    run_id: str
    passed: bool
    abstained: bool
    faithfulness: float | None
    context_precision: float | None
    answer_relevancy: float | None


@dataclass
class CiReport:
    run_id: str
    started_at: datetime
    finished_at: datetime
    split: str
    known_bad_split: str
    mode: str
    threshold_faithfulness: float
    exit_code: int
    loader_error: str | None
    known_bad: KnownBadPhase
    metrics: RagasScores
    split_rows: list[SplitRowResult]
    gate_reason: str | None
    failing_run_ids: list[str] = field(default_factory=list)

    def to_artifact(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "split": self.split,
            "known_bad_split": self.known_bad_split,
            "mode": self.mode,
            "framework": "ragas",
            "threshold_faithfulness": self.threshold_faithfulness,
            "gate_passed": self.exit_code == 0,
            "gate_reason": self.gate_reason,
            "loader_error": self.loader_error,
            "metrics": {
                "faithfulness": self.metrics.faithfulness,
                "context_precision": self.metrics.context_precision,
                "answer_relevancy": self.metrics.answer_relevancy,
            },
            "known_bad": {
                "clean": self.known_bad.clean,
                "rows": [
                    {
                        "id": row.id,
                        "run_id": row.run_id,
                        "required_assert_failed": row.required_assert_failed,
                        "abstained": row.abstained,
                    }
                    for row in self.known_bad.rows
                ],
            },
            "failing_run_ids": self.failing_run_ids,
            "previous": None,
            "diff": None,
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m citebench.eval.ci")
    parser.add_argument("--split", required=True, help="CI JSONL split (Contract A)")
    parser.add_argument("--known-bad", required=True, help="Anti-theater JSONL split")
    parser.add_argument(
        "--threshold-faithfulness",
        type=float,
        default=0.7,
        help="Mean RAGAS faithfulness gate",
    )
    parser.add_argument("--output", default="", help="Write latest score artifact here")
    parser.add_argument(
        "--store-dir",
        default="",
        help="Eval result store (latest.json / previous.json)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use fixture RAGAS judge (CI when Groq is unavailable)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Force live Groq + RAGAS (fails if GROQ_API_KEY is missing)",
    )
    return parser


def resolve_mode(*, mock: bool, live: bool) -> str:
    if live and mock:
        raise ValueError("use only one of --mock or --live")
    if live:
        return "live"
    if mock:
        return "mock"
    if os.environ.get("CITEBENCH_EVAL_LIVE", "").strip() in {"1", "true", "yes"}:
        return "live"
    if os.environ.get("GROQ_API_KEY", "").strip():
        return "live"
    return "mock"


def run_ci(
    *,
    split: str,
    known_bad: str,
    threshold_faithfulness: float = 0.7,
    store_dir: str | Path | None = None,
    mock: bool = False,
    live: bool = False,
    answer_fn: AnswerFn | None = None,
) -> CiReport:
    started = datetime.now(timezone.utc)
    run_id = f"eval-{uuid4().hex[:12]}"
    dest = resolve_eval_store_dir(store_dir)
    mode = "mock"
    loader_error: str | None = None
    known_phase = KnownBadPhase(clean=False, rows=[])
    split_rows: list[SplitRowResult] = []
    metrics = RagasScores(0.0, 0.0, 0.0)
    failing: list[str] = []
    gate_reason: str | None = None
    exit_code = 1

    try:
        mode = resolve_mode(mock=mock, live=live)
    except ValueError as exc:
        loader_error = str(exc)
        return _finish(
            run_id,
            started,
            split,
            known_bad,
            mode,
            threshold_faithfulness,
            exit_code=2,
            loader_error=loader_error,
            known_phase=known_phase,
            metrics=metrics,
            split_rows=split_rows,
            gate_reason=loader_error,
            failing=failing,
            dest=dest,
        )

    if mode == "live" and not os.environ.get("GROQ_API_KEY", "").strip() and answer_fn is None:
        loader_error = "GROQ_API_KEY is required for --live eval"
        return _finish(
            run_id,
            started,
            split,
            known_bad,
            mode,
            threshold_faithfulness,
            exit_code=2,
            loader_error=loader_error,
            known_phase=known_phase,
            metrics=metrics,
            split_rows=split_rows,
            gate_reason=loader_error,
            failing=failing,
            dest=dest,
        )

    try:
        known_rows = load_eval_jsonl(known_bad)
    except Exception as exc:
        loader_error = str(exc)
        return _finish(
            run_id,
            started,
            split,
            known_bad,
            mode,
            threshold_faithfulness,
            exit_code=2,
            loader_error=loader_error,
            known_phase=known_phase,
            metrics=metrics,
            split_rows=split_rows,
            gate_reason=f"loader error: {exc}",
            failing=failing,
            dest=dest,
        )

    try:
        split_eval_rows = load_eval_jsonl(split)
    except Exception as exc:
        loader_error = str(exc)
        # Known-bad still runs when the split cannot load? Contract: execute
        # known_bad in full before RAGAS. Split loader errors still fail the job.
        answerer = answer_fn or _default_answerer(mode, known_rows)
        known_phase = _run_known_bad(known_rows, answerer)
        return _finish(
            run_id,
            started,
            split,
            known_bad,
            mode,
            threshold_faithfulness,
            exit_code=2,
            loader_error=loader_error,
            known_phase=known_phase,
            metrics=metrics,
            split_rows=split_rows,
            gate_reason=f"loader error: {exc}",
            failing=failing,
            dest=dest,
        )

    answerer = answer_fn or _default_answerer(mode, known_rows + split_eval_rows)
    known_phase = _run_known_bad(known_rows, answerer)
    if not known_phase.clean:
        for row in known_phase.rows:
            if not row.required_assert_failed:
                failing.append(row.run_id)
        split_rows, metrics, more_failing = _run_split(
            split_eval_rows,
            answerer,
            threshold_faithfulness,
            live=(mode == "live"),
        )
        failing.extend(more_failing)
        return _finish(
            run_id,
            started,
            split,
            known_bad,
            mode,
            threshold_faithfulness,
            exit_code=1,
            loader_error=None,
            known_phase=known_phase,
            metrics=metrics,
            split_rows=split_rows,
            gate_reason="known-bad phase unclean: a known_bad row passed its success assert",
            failing=failing,
            dest=dest,
        )

    split_rows, metrics, more_failing = _run_split(
        split_eval_rows,
        answerer,
        threshold_faithfulness,
        live=(mode == "live"),
    )
    failing.extend(more_failing)
    if metrics.faithfulness < threshold_faithfulness:
        gate_reason = (
            f"faithfulness {metrics.faithfulness:.4f} < threshold {threshold_faithfulness}"
        )
        exit_code = 1
    else:
        gate_reason = "ok"
        exit_code = 0

    return _finish(
        run_id,
        started,
        split,
        known_bad,
        mode,
        threshold_faithfulness,
        exit_code=exit_code,
        loader_error=None,
        known_phase=known_phase,
        metrics=metrics,
        split_rows=split_rows,
        gate_reason=gate_reason,
        failing=failing,
        dest=dest,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = run_ci(
        split=args.split,
        known_bad=args.known_bad,
        threshold_faithfulness=args.threshold_faithfulness,
        store_dir=args.store_dir or None,
        mock=args.mock,
        live=args.live,
    )
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(
            Path(resolve_eval_store_dir(args.store_dir or None) / "latest.json").read_text(
                encoding="utf-8"
            )
            if (resolve_eval_store_dir(args.store_dir or None) / "latest.json").is_file()
            else "",
            encoding="utf-8",
        )
    print(
        f"citebench.eval.ci mode={report.mode} exit={report.exit_code} "
        f"faithfulness={report.metrics.faithfulness:.4f} "
        f"context_precision={report.metrics.context_precision:.4f} "
        f"answer_relevancy={report.metrics.answer_relevancy:.4f} "
        f"known_bad_clean={report.known_bad.clean} reason={report.gate_reason}",
        file=sys.stderr,
    )
    return report.exit_code


def _default_answerer(mode: str, rows: list[EvalRow]) -> AnswerFn:
    if mode == "live":
        return live_answer
    return mock_answer_fn_for_rows(rows)


def _run_known_bad(rows: list[EvalRow], answerer: AnswerFn) -> KnownBadPhase:
    results: list[KnownBadRowResult] = []
    clean = True
    for row in rows:
        answer = answerer(row.question, row.id)
        failed = required_assert_failed(row, answer)
        if not failed:
            clean = False
            emit_row_trace(answer, failed=True, reason="known_bad_passed_success_assert")
        results.append(
            KnownBadRowResult(
                id=row.id,
                run_id=answer.run_id,
                required_assert_failed=failed,
                answer=answer.answer,
                abstained=answer.abstained,
            )
        )
    return KnownBadPhase(clean=clean, rows=results)


def _run_split(
    rows: list[EvalRow],
    answerer: AnswerFn,
    threshold: float,
    *,
    live: bool,
) -> tuple[list[SplitRowResult], RagasScores, list[str]]:
    scored: list[RagasScores] = []
    split_rows: list[SplitRowResult] = []
    failing: list[str] = []
    for row in rows:
        answer = answerer(row.question, row.id)
        ragas = score_row(
            question=row.question,
            answer=answer.answer,
            contexts=answer.contexts,
            expected=row.expected,
            abstained=answer.abstained,
            live=live,
        )
        if ragas is not None:
            scored.append(ragas)
        cite_ok = (not row.must_cite) or bool(answer.citations)
        row_pass = True
        if row.abstain:
            row_pass = not naive_success_assert(row, answer)
        elif answer.abstained or ragas is None:
            row_pass = False
        elif ragas.faithfulness < threshold or not cite_ok:
            row_pass = False
        if not row_pass:
            failing.append(answer.run_id)
            emit_row_trace(answer, failed=True, reason="split_row_failed_ragas_or_cite")
        split_rows.append(
            SplitRowResult(
                id=row.id,
                run_id=answer.run_id,
                passed=row_pass,
                abstained=answer.abstained,
                faithfulness=None if ragas is None else ragas.faithfulness,
                context_precision=None if ragas is None else ragas.context_precision,
                answer_relevancy=None if ragas is None else ragas.answer_relevancy,
            )
        )
    return split_rows, mean_scores(scored), failing


def _finish(
    run_id: str,
    started: datetime,
    split: str,
    known_bad: str,
    mode: str,
    threshold_faithfulness: float,
    *,
    exit_code: int,
    loader_error: str | None,
    known_phase: KnownBadPhase,
    metrics: RagasScores,
    split_rows: list[SplitRowResult],
    gate_reason: str | None,
    failing: list[str],
    dest: Path,
) -> CiReport:
    report = CiReport(
        run_id=run_id,
        started_at=started,
        finished_at=datetime.now(timezone.utc),
        split=split,
        known_bad_split=known_bad,
        mode=mode,
        threshold_faithfulness=threshold_faithfulness,
        exit_code=exit_code,
        loader_error=loader_error,
        known_bad=known_phase,
        metrics=metrics,
        split_rows=split_rows,
        gate_reason=gate_reason,
        failing_run_ids=failing,
    )
    write_report(report, dest)
    return report


if __name__ == "__main__":
    raise SystemExit(main())
