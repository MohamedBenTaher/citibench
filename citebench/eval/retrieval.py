"""Retrieval + answerability evaluation against hand-labeled qrels.

Objective, cheap half: Recall@k / MRR / nDCG from `retrieve()` (local embed +
Postgres only — no LLM). Optional `--live` half: run generate to get an
answer/abstain confusion matrix over answerable vs unanswerable questions.

    python -m citebench.eval.retrieval --split evals/splits/retrieval.jsonl \
        --out evals/results/retrieval.json
    python -m citebench.eval.retrieval --live     # adds the calibration matrix
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import citebench.eval.paths  # noqa: F401  # sys.path for the API modules

from citebench.eval.paths import REPO_ROOT
from generate import generate
from retrieve import retrieve
from settings import load_settings

DEFAULT_SPLIT = REPO_ROOT / "evals" / "splits" / "retrieval.jsonl"
DEFAULT_OUT = REPO_ROOT / "evals" / "results" / "retrieval.json"


@dataclass(frozen=True)
class RetrievalRow:
    id: str
    question: str
    gold_doc_ids: tuple[str, ...]
    answerable: bool
    tags: tuple[str, ...]


def load_retrieval_jsonl(path: str | Path) -> list[RetrievalRow]:
    text = Path(path).read_text(encoding="utf-8")
    rows: list[RetrievalRow] = []
    seen: set[str] = set()
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
        row_id = str(payload.get("id") or "").strip()
        if not row_id:
            raise ValueError(f"{path}:{line_no}: id is required")
        if row_id in seen:
            raise ValueError(f"{path}:{line_no}: duplicate id {row_id}")
        seen.add(row_id)
        question = str(payload.get("question") or "").strip()
        if not question:
            raise ValueError(f"{path}:{line_no}: question is required")
        answerable = bool(payload.get("answerable", True))
        gold = tuple(str(item).strip() for item in (payload.get("gold_doc_ids") or []) if str(item).strip())
        if answerable and not gold:
            raise ValueError(f"{path}:{line_no}: answerable row needs gold_doc_ids")
        if not answerable and gold:
            raise ValueError(f"{path}:{line_no}: unanswerable row must not have gold_doc_ids")
        rows.append(
            RetrievalRow(
                id=row_id,
                question=question,
                gold_doc_ids=gold,
                answerable=answerable,
                tags=tuple(str(tag) for tag in (payload.get("tags") or [])),
            )
        )
    if not rows:
        raise ValueError(f"{path}: no rows")
    return rows


def score_row(
    retrieved_doc_ids: list[str],
    gold_doc_ids: tuple[str, ...],
    k: int,
) -> dict[str, float | int | None]:
    """Recall@k, first relevant rank, MRR, and nDCG@k for one question."""
    gold = set(gold_doc_ids)
    top = retrieved_doc_ids[:k]
    relevant_ranks = [index + 1 for index, doc in enumerate(top) if doc in gold]
    recall = (len(relevant_ranks) / len(gold)) if gold else 0.0
    first = min(relevant_ranks) if relevant_ranks else None
    mrr = (1.0 / first) if first else 0.0
    dcg = sum(1.0 / math.log2(rank + 1) for rank in relevant_ranks)
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, min(len(gold), k) + 1))
    ndcg = (dcg / idcg) if idcg > 0 else 0.0
    return {
        "recall": round(recall, 4),
        "first_relevant_rank": first,
        "mrr": round(mrr, 4),
        "ndcg": round(ndcg, 4),
    }


def evaluate(
    rows: list[RetrievalRow],
    retrieved_by_id: dict[str, list[str]],
    k: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    answerable = [row for row in rows if row.answerable]
    n_answerable = len(answerable)
    n_unanswerable = len(rows) - n_answerable
    recall = mrr = ndcg = 0.0
    per_row: list[dict[str, Any]] = []
    for row in rows:
        docs = retrieved_by_id.get(row.id, [])
        scored = score_row(docs, row.gold_doc_ids, k) if row.answerable else None
        if scored:
            recall += float(scored["recall"])
            mrr += float(scored["mrr"])
            ndcg += float(scored["ndcg"])
        per_row.append(
            {
                "id": row.id,
                "question": row.question,
                "answerable": row.answerable,
                "gold_doc_ids": list(row.gold_doc_ids),
                "retrieved_doc_ids": docs[:k],
                "recall": scored["recall"] if scored else None,
                "first_relevant_rank": scored["first_relevant_rank"] if scored else None,
                "mrr": scored["mrr"] if scored else None,
                "ndcg": scored["ndcg"] if scored else None,
            }
        )
    if n_answerable:
        recall /= n_answerable
        mrr /= n_answerable
        ndcg /= n_answerable
    return (
        {
            "recall_at_k": round(recall, 4),
            "mrr": round(mrr, 4),
            "ndcg_at_k": round(ndcg, 4),
            "n_scored": n_answerable,
            "answerable": n_answerable,
            "unanswerable": n_unanswerable,
        },
        per_row,
    )


def calibration(rows: list[RetrievalRow], decisions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    answerable = [row for row in rows if row.answerable]
    unanswerable = [row for row in rows if not row.answerable]
    answered_answerable = sum(1 for row in answerable if decisions.get(row.id, {}).get("answered"))
    answered_unanswerable = sum(1 for row in unanswerable if decisions.get(row.id, {}).get("answered"))
    n_a, n_u = len(answerable), len(unanswerable)
    return {
        "answerable": n_a,
        "unanswerable": n_u,
        "answered_answerable": answered_answerable,
        "abstained_answerable": n_a - answered_answerable,
        "answered_unanswerable": answered_unanswerable,
        "abstained_unanswerable": n_u - answered_unanswerable,
        "false_answer_rate": round(answered_unanswerable / n_u, 4) if n_u else None,
        "false_abstain_rate": round((n_a - answered_answerable) / n_a, 4) if n_a else None,
        "rows": [
            {
                "id": row.id,
                "answerable": row.answerable,
                **{key: decisions.get(row.id, {}).get(key) for key in ("answered", "abstained", "abstain_reason")},
            }
            for row in rows
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Retrieval + answerability evaluation.")
    parser.add_argument("--split", default=str(DEFAULT_SPLIT))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--k", type=int, default=0, help="0 uses settings.top_k")
    parser.add_argument("--live", action="store_true", help="also run generate for the calibration matrix")
    args = parser.parse_args(argv)

    rows = load_retrieval_jsonl(args.split)
    settings = load_settings()
    k = args.k or settings.top_k
    started = datetime.now(timezone.utc)

    retrieved: dict[str, list[str]] = {}
    errors: dict[str, str] = {}
    gate_decisions: dict[str, dict[str, Any]] = {}
    for row in rows:
        try:
            hits = retrieve(row.question, settings=settings)
        except Exception as exc:  # noqa: BLE001 - keep going, record the error
            errors[row.id] = str(exc)
            retrieved[row.id] = []
            gate_decisions[row.id] = {"answered": False, "abstained": False, "abstain_reason": "error"}
            continue
        docs: list[str] = []
        for hit in hits:
            if hit.doc_id not in docs:
                docs.append(hit.doc_id)
        retrieved[row.id] = docs
        top = hits[0] if hits else None
        skipped = bool(top and top.rerank_skipped)
        confident = bool(top) and (skipped or (top.score is not None and top.score >= settings.abstain_min_score))
        gate_decisions[row.id] = {
            "answered": confident,
            "abstained": not confident,
            "abstain_reason": None if confident else ("empty_retrieve" if top is None else "low_confidence"),
        }

    retrieval, per_row = evaluate(rows, retrieved, k)
    for row in per_row:
        row["gate_answered"] = gate_decisions.get(row["id"], {}).get("answered")

    mode = "retrieve+gate"
    calib: dict[str, Any] | None = calibration(rows, gate_decisions)
    if calib is not None:
        calib["kind"] = "retrieval_gate"
    if args.live and settings.groq_api_key:
        decisions: dict[str, dict[str, Any]] = {}
        for row in rows:
            try:
                result = generate(row.question, settings=settings)
                decisions[row.id] = {
                    "answered": not result.abstained,
                    "abstained": bool(result.abstained),
                    "abstain_reason": result.abstain_reason,
                }
            except Exception as exc:  # noqa: BLE001 - record and continue
                decisions[row.id] = {"answered": False, "abstained": False, "abstain_reason": f"error: {exc}"}
        calib = calibration(rows, decisions)
        calib["kind"] = "live"
        mode = "live"
        for row in per_row:
            decision = decisions.get(row["id"], {})
            row["answered"] = decision.get("answered")
            row["abstained"] = decision.get("abstained")

    finished = datetime.now(timezone.utc)
    artifact: dict[str, Any] = {
        "run_id": f"retr-{finished.strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:6]}",
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "measured_at": finished.isoformat(),
        "mode": mode,
        "k": k,
        "n": len(rows),
        "retrieval": retrieval,
        "calibration": calib,
        "errors": errors,
        "rows": per_row,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(
        f"retrieval mode={mode} k={k} recall@{k}={retrieval['recall_at_k']} "
        f"mrr={retrieval['mrr']} ndcg@{k}={retrieval['ndcg_at_k']} "
        f"answerable={retrieval['answerable']} unanswerable={retrieval['unanswerable']}"
    )
    if calib:
        print(
            f"calibration false_answer={calib['false_answer_rate']} "
            f"false_abstain={calib['false_abstain_rate']}"
        )
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
