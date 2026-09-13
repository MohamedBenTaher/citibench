import json
import math
from pathlib import Path

import pytest

from citebench.eval.retrieval import (
    RetrievalRow,
    evaluate,
    load_retrieval_jsonl,
    score_row,
)


def test_score_row_perfect_rank() -> None:
    out = score_row(["a", "b", "c"], ("b",), 8)
    assert out["recall"] == 1.0
    assert out["first_relevant_rank"] == 2
    assert out["mrr"] == pytest.approx(0.5)
    assert out["ndcg"] == pytest.approx(1 / math.log2(3), abs=1e-4)


def test_score_row_miss() -> None:
    out = score_row(["a", "b"], ("z",), 8)
    assert out["recall"] == 0.0
    assert out["first_relevant_rank"] is None
    assert out["mrr"] == 0.0
    assert out["ndcg"] == 0.0


def test_score_row_multi_gold_ndcg() -> None:
    out = score_row(["a", "b", "c", "d"], ("a", "c"), 8)
    dcg = 1.0 + 1 / math.log2(4)
    idcg = 1.0 + 1 / math.log2(3)
    assert out["recall"] == pytest.approx(1.0)
    assert out["ndcg"] == pytest.approx(dcg / idcg, abs=1e-4)


def test_evaluate_aggregates() -> None:
    rows = [
        RetrievalRow("a", "q1", ("x",), True, ()),
        RetrievalRow("b", "q2", ("y",), True, ()),
        RetrievalRow("c", "q3", (), False, ()),
    ]
    retrieval, per_row = evaluate(rows, {"a": ["x"], "b": ["nope", "y"], "c": ["z"]}, 8)
    assert retrieval["answerable"] == 2
    assert retrieval["unanswerable"] == 1
    assert retrieval["recall_at_k"] == pytest.approx(1.0)
    assert retrieval["mrr"] == pytest.approx((1.0 + 0.5) / 2)
    assert len(per_row) == 3
    assert per_row[2]["recall"] is None


def test_load_retrieval_jsonl_validates(tmp_path: Path) -> None:
    good = tmp_path / "good.jsonl"
    good.write_text(
        json.dumps(
            {"id": "r-1", "question": "Q?", "gold_doc_ids": ["d"], "answerable": True, "tags": []}
        )
        + "\n",
        encoding="utf-8",
    )
    rows = load_retrieval_jsonl(good)
    assert rows[0].gold_doc_ids == ("d",)

    missing_gold = tmp_path / "missing.jsonl"
    missing_gold.write_text(
        json.dumps({"id": "r-2", "question": "Q?", "answerable": True}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="gold_doc_ids"):
        load_retrieval_jsonl(missing_gold)
