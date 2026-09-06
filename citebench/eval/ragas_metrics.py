"""RAGAS metrics used by the C6 gate.

Live Groq uses the ragas library when installed. CI without Groq uses a
fixture judge that implements the same three metric definitions:

- faithfulness: supported answer statements / statements (context entailment)
- context_precision: share of retrieved contexts that match the question
- answer_relevancy: how well the answer addresses the question

Faithfulness is the only CI gate. Companion metrics are logged.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Sequence

try:
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import answer_relevancy, context_precision, faithfulness
except Exception:  # ragas is optional; CI uses the fixture judge
    Dataset = None
    evaluate = None
    answer_relevancy = None
    context_precision = None
    faithfulness = None

_STOP = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "does",
        "for",
        "from",
        "how",
        "in",
        "into",
        "is",
        "it",
        "of",
        "on",
        "or",
        "onto",
        "the",
        "to",
        "what",
        "with",
    }
)


@dataclass(frozen=True)
class RagasScores:
    faithfulness: float
    context_precision: float
    answer_relevancy: float


def score_row(
    *,
    question: str,
    answer: str,
    contexts: Sequence[str],
    expected: str = "",
    abstained: bool = False,
    live: bool = False,
) -> RagasScores | None:
    """Score one non-abstain row. Abstain rows return None (excluded from the mean)."""
    if abstained:
        return None
    if live and os.environ.get("GROQ_API_KEY", "").strip():
        live_scores = _try_live_ragas(question, answer, contexts, expected)
        if live_scores is not None:
            return live_scores
    return fixture_ragas_scores(question, answer, contexts, expected)


def mean_scores(rows: Sequence[RagasScores]) -> RagasScores:
    if not rows:
        return RagasScores(faithfulness=0.0, context_precision=0.0, answer_relevancy=0.0)
    n = float(len(rows))
    return RagasScores(
        faithfulness=sum(item.faithfulness for item in rows) / n,
        context_precision=sum(item.context_precision for item in rows) / n,
        answer_relevancy=sum(item.answer_relevancy for item in rows) / n,
    )


def fixture_ragas_scores(
    question: str,
    answer: str,
    contexts: Sequence[str],
    expected: str = "",
) -> RagasScores:
    return RagasScores(
        faithfulness=_faithfulness(answer, contexts),
        context_precision=_context_precision(question, contexts, expected),
        answer_relevancy=_answer_relevancy(question, answer),
    )


def _faithfulness(answer: str, contexts: Sequence[str]) -> float:
    statements = _statements(answer)
    if not statements:
        return 0.0
    blob = " ".join(ctx for ctx in contexts if ctx)
    if not blob.strip():
        return 0.0
    supported = sum(1 for stmt in statements if _overlap(stmt, blob) >= 0.45 or _subset(stmt, blob))
    return supported / float(len(statements))


def _context_precision(question: str, contexts: Sequence[str], expected: str) -> float:
    chunks = [ctx for ctx in contexts if str(ctx).strip()]
    if not chunks:
        return 0.0
    relevant = 0
    for ctx in chunks:
        if _overlap(question, ctx) >= 0.2 or (expected and _overlap(expected, ctx) >= 0.2):
            relevant += 1
    return relevant / float(len(chunks))


def _answer_relevancy(question: str, answer: str) -> float:
    if not answer.strip():
        return 0.0
    return max(_overlap(answer, question), _overlap(question, answer))


def _statements(answer: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", answer.strip())
    return [part.strip() for part in parts if part.strip()]


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if token not in _STOP and len(token) > 1
    }


def _overlap(left: str, right: str) -> float:
    source = _tokens(left)
    target = _tokens(right)
    if not source:
        return 0.0
    return len(source & target) / float(len(source))


def _subset(left: str, right: str) -> bool:
    source = _tokens(left)
    target = _tokens(right)
    return bool(source) and source <= target


def _try_live_ragas(
    question: str,
    answer: str,
    contexts: Sequence[str],
    expected: str,
) -> RagasScores | None:
    if evaluate is None or Dataset is None:
        return None
    if faithfulness is None or context_precision is None or answer_relevancy is None:
        return None
    dataset = Dataset.from_dict(
        {
            "question": [question],
            "answer": [answer],
            "contexts": [list(contexts)],
            "ground_truth": [expected or answer],
        }
    )
    try:
        result = evaluate(
            dataset,
            metrics=[faithfulness, context_precision, answer_relevancy],
        )
    except Exception:
        return None
    payload: dict[str, Any]
    if hasattr(result, "scores"):
        payload = dict(result.scores)
    else:
        payload = dict(result)
    return RagasScores(
        faithfulness=_metric(payload, "faithfulness"),
        context_precision=_metric(payload, "context_precision"),
        answer_relevancy=_metric(payload, "answer_relevancy", "answer_relevance"),
    )


def _metric(payload: dict[str, Any], *names: str) -> float:
    for name in names:
        if name in payload:
            value = payload[name]
            if isinstance(value, list) and value:
                value = value[0]
            return float(value)
    return 0.0
