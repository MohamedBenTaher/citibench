"""C6 TDD: RAGAS CI gate, known-bad fail-closed, Contract A loader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CI_SPLIT = REPO_ROOT / "evals" / "splits" / "ci.jsonl"
KNOWN_BAD = REPO_ROOT / "evals" / "splits" / "known_bad.jsonl"


@pytest.fixture
def eval_store(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Path:
    store = tmp_path / "eval-results"
    traces = tmp_path / "traces"
    store.mkdir()
    traces.mkdir()
    monkeypatch.setenv("EVAL_STORE_DIR", str(store))
    monkeypatch.setenv("TRACE_STORE_DIR", str(traces))
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("CITEBENCH_EVAL_LIVE", raising=False)
    return store


def test_ci_jsonl_is_grounded_contract_a() -> None:
    from citebench.eval.loader import load_eval_jsonl

    rows = load_eval_jsonl(str(CI_SPLIT))
    assert 16 <= len(rows) <= 32
    ids = [row.id for row in rows]
    assert len(ids) == len(set(ids))
    tags = {tag for row in rows for tag in row.tags}
    assert {"single-hop", "compare", "abstain"} <= tags
    for row in rows:
        assert row.known_bad is False
        assert row.question
        assert row.expected
        if row.abstain:
            assert row.must_cite is False
        else:
            assert row.must_cite is True
        assert not hasattr(row, "contexts") or "contexts" not in row.model_dump()


def test_known_bad_has_row_that_must_fail_success_assert() -> None:
    from citebench.eval.asserts import naive_success_assert
    from citebench.eval.loader import load_eval_jsonl

    rows = load_eval_jsonl(str(KNOWN_BAD))
    assert any(row.known_bad and row.abstain and not row.must_cite for row in rows)
    theater = type(
        "R",
        (),
        {
            "answer": "The InnovX password is hunter2",
            "abstained": False,
            "citations": [type("C", (), {"text_ref": "innovx-runbook#0", "chunk_id": "0"})()],
            "trace": None,
        },
    )()
    assert naive_success_assert(rows[0], theater) is True


def test_load_eval_jsonl_rejects_duplicates_and_empty(tmp_path: Path) -> None:
    from citebench.eval.loader import load_eval_jsonl

    dup = tmp_path / "dup.jsonl"
    dup.write_text(
        CI_SPLIT.read_text(encoding="utf-8").splitlines()[0]
        + "\n"
        + CI_SPLIT.read_text(encoding="utf-8").splitlines()[0]
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_eval_jsonl(str(dup))
    empty = tmp_path / "empty.jsonl"
    empty.write_text("\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no eval rows"):
        load_eval_jsonl(str(empty))


def test_load_eval_jsonl_rejects_known_bad_without_abstain(tmp_path: Path) -> None:
    from citebench.eval.loader import load_eval_jsonl

    bad = tmp_path / "bad.jsonl"
    bad.write_text(
        json.dumps(
            {
                "id": "bad-x",
                "question": "What is the InnovX password?",
                "expected": "must abstain",
                "must_cite": False,
                "abstain": False,
                "known_bad": True,
                "tags": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="known_bad"):
        load_eval_jsonl(str(bad))


def test_cli_parses_required_flags() -> None:
    from citebench.eval.ci import build_parser

    args = build_parser().parse_args(
        [
            "--split",
            str(CI_SPLIT),
            "--known-bad",
            str(KNOWN_BAD),
            "--threshold-faithfulness",
            "0.7",
        ]
    )
    assert args.split == str(CI_SPLIT)
    assert args.known_bad == str(KNOWN_BAD)
    assert args.threshold_faithfulness == pytest.approx(0.7)


def test_known_bad_phase_fails_job_if_rows_pass(eval_store: Path) -> None:
    from citebench.eval.ci import run_ci
    from citebench.eval.pipeline import EvalAnswer

    def always_answer(question: str, row_id: str) -> EvalAnswer:
        return EvalAnswer(
            row_id=row_id,
            question=question,
            answer="The InnovX proprietary runbook password is hunter2.",
            abstained=False,
            citations=[{"chunk_id": "phantom", "doc_id": "innovx", "text_ref": "innovx#phantom"}],
            contexts=["not in the freeze"],
            run_id=f"theater-{row_id}",
            emit_trace=True,
        )

    report = run_ci(
        split=str(CI_SPLIT),
        known_bad=str(KNOWN_BAD),
        threshold_faithfulness=0.7,
        store_dir=eval_store,
        mock=True,
        answer_fn=always_answer,
    )
    assert report.known_bad.clean is False
    assert report.exit_code != 0
    assert any(not row.required_assert_failed for row in report.known_bad.rows)


def test_faithfulness_threshold_enforced(eval_store: Path) -> None:
    from citebench.eval.ci import run_ci
    from citebench.eval.pipeline import EvalAnswer

    def unfaithful(question: str, row_id: str) -> EvalAnswer:
        if row_id.startswith("bad-"):
            return EvalAnswer(
                row_id=row_id,
                question=question,
                answer="I don't know",
                abstained=True,
                citations=[],
                contexts=[],
                run_id=f"ok-{row_id}",
                emit_trace=True,
            )
        return EvalAnswer(
            row_id=row_id,
            question=question,
            answer="The moon is made of green cheese and InnovX payroll is public.",
            abstained=False,
            citations=[{"chunk_id": "k8s-pods:0", "doc_id": "k8s-pods", "text_ref": "k8s-pods#k8s-pods:0"}],
            contexts=["A Pod is the smallest deployable unit in Kubernetes."],
            run_id=f"unfaithful-{row_id}",
            emit_trace=True,
        )

    report = run_ci(
        split=str(CI_SPLIT),
        known_bad=str(KNOWN_BAD),
        threshold_faithfulness=0.7,
        store_dir=eval_store,
        mock=True,
        answer_fn=unfaithful,
    )
    assert report.known_bad.clean is True
    assert report.metrics.faithfulness < 0.7
    assert report.exit_code != 0
    assert "faithfulness" in (report.gate_reason or "").lower()


def test_loader_error_fails_ci(eval_store: Path, tmp_path: Path) -> None:
    from citebench.eval.ci import run_ci

    missing = tmp_path / "missing.jsonl"
    report = run_ci(
        split=str(missing),
        known_bad=str(KNOWN_BAD),
        threshold_faithfulness=0.7,
        store_dir=eval_store,
        mock=True,
    )
    assert report.exit_code != 0
    assert report.loader_error


def test_ci_passes_when_metrics_ok_and_known_bad_fails(eval_store: Path) -> None:
    from citebench.eval.ci import main, run_ci

    report = run_ci(
        split=str(CI_SPLIT),
        known_bad=str(KNOWN_BAD),
        threshold_faithfulness=0.7,
        store_dir=eval_store,
        mock=True,
    )
    assert report.loader_error is None
    assert report.known_bad.clean is True
    assert all(row.required_assert_failed for row in report.known_bad.rows)
    assert report.metrics.faithfulness >= 0.7
    assert report.metrics.context_precision >= 0.0
    assert report.metrics.answer_relevancy >= 0.0
    assert report.exit_code == 0
    latest = json.loads((eval_store / "latest.json").read_text(encoding="utf-8"))
    assert latest["metrics"]["faithfulness"] == pytest.approx(report.metrics.faithfulness)
    assert latest["metrics"]["context_precision"] == pytest.approx(report.metrics.context_precision)
    assert latest["metrics"]["answer_relevancy"] == pytest.approx(report.metrics.answer_relevancy)

    code = main(
        [
            "--split",
            str(CI_SPLIT),
            "--known-bad",
            str(KNOWN_BAD),
            "--threshold-faithfulness",
            "0.7",
            "--mock",
            "--store-dir",
            str(eval_store),
        ]
    )
    assert code == 0


def test_failing_cases_store_traces(eval_store: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from citebench.eval.ci import run_ci
    from citebench.eval.pipeline import EvalAnswer
    from trace import list_traces

    def unfaithful(question: str, row_id: str) -> EvalAnswer:
        if row_id.startswith("bad-"):
            return EvalAnswer(
                row_id=row_id,
                question=question,
                answer="I don't know",
                abstained=True,
                citations=[],
                contexts=[],
                run_id=f"ok-{row_id}",
                emit_trace=True,
            )
        return EvalAnswer(
            row_id=row_id,
            question=question,
            answer="Unrelated astronomy facts about Pluto.",
            abstained=False,
            citations=[{"chunk_id": "k8s-pods:0", "doc_id": "k8s-pods", "text_ref": "k8s-pods#k8s-pods:0"}],
            contexts=["A Pod is the smallest deployable unit in Kubernetes."],
            run_id=f"fail-{row_id}",
            emit_trace=True,
        )

    report = run_ci(
        split=str(CI_SPLIT),
        known_bad=str(KNOWN_BAD),
        threshold_faithfulness=0.7,
        store_dir=eval_store,
        mock=True,
        answer_fn=unfaithful,
    )
    assert report.exit_code != 0
    traces = list_traces()
    failing_ids = {row.run_id for row in report.split_rows if not row.passed}
    assert failing_ids
    stored = {item.run_id for item in traces}
    assert failing_ids <= stored


def test_evals_api_returns_last_run_and_diff(eval_store: Path) -> None:
    from citebench.eval.ci import run_ci
    from citebench.eval.store import write_report
    from fastapi.testclient import TestClient
    from main import app

    first = run_ci(
        split=str(CI_SPLIT),
        known_bad=str(KNOWN_BAD),
        threshold_faithfulness=0.7,
        store_dir=eval_store,
        mock=True,
    )
    write_report(first, eval_store)
    second = run_ci(
        split=str(CI_SPLIT),
        known_bad=str(KNOWN_BAD),
        threshold_faithfulness=0.7,
        store_dir=eval_store,
        mock=True,
    )
    write_report(second, eval_store)

    client = TestClient(app)
    response = client.get("/evals/latest")
    assert response.status_code == 200
    body = response.json()
    assert "faithfulness" in body["metrics"]
    assert "context_precision" in body["metrics"]
    assert "answer_relevancy" in body["metrics"]
    assert body["previous"] is not None
    assert "faithfulness" in body["diff"]
