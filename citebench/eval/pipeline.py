"""Eval answer pipeline: fixture (CI mock) or injected / live generate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol
from uuid import uuid4

import citebench.eval.paths  # noqa: F401

from citebench.eval.paths import REPO_ROOT
from generate import ABSTAIN_ANSWER, generate
from retrieve import ChunkHit
from settings import Settings, load_settings

AnswerFn = Callable[[str, str], "EvalAnswer"]


@dataclass
class EvalAnswer:
    row_id: str
    question: str
    answer: str
    abstained: bool
    citations: list[Any]
    contexts: list[str]
    run_id: str
    emit_trace: bool = True
    trace: Any | None = None


class SupportsAnswer(Protocol):
    def __call__(self, question: str, row_id: str) -> EvalAnswer: ...


CI_FIXTURES: dict[str, dict[str, Any]] = {
    "ci-001": {
        "answer": (
            "The kube-scheduler assigns unscheduled Pods to nodes using filters "
            "and scoring plugins."
        ),
        "contexts": [
            "kube-scheduler assigns unscheduled Pods to nodes using filters and scoring plugins.",
            "A Pod is the smallest deployable unit in Kubernetes. The control plane schedules each Pod onto a node.",
        ],
        "citations": [
            {
                "chunk_id": "k8s-scheduler:0",
                "doc_id": "k8s-scheduler",
                "text_ref": "k8s-scheduler#k8s-scheduler:0",
            }
        ],
    },
    "ci-002": {
        "answer": (
            "A Pod is the smallest deployable unit in Kubernetes. The control "
            "plane schedules each Pod onto a node."
        ),
        "contexts": [
            "A Pod is the smallest deployable unit in Kubernetes. The control plane schedules each Pod onto a node."
        ],
        "citations": [
            {
                "chunk_id": "k8s-pods:0",
                "doc_id": "k8s-pods",
                "text_ref": "k8s-pods#k8s-pods:0",
            }
        ],
    },
    "ci-003": {
        "answer": (
            "A Service exposes a set of Pods. It does not schedule workloads onto nodes."
        ),
        "contexts": [
            "A Service exposes a set of Pods. It does not schedule workloads onto nodes."
        ],
        "citations": [
            {
                "chunk_id": "k8s-services:0",
                "doc_id": "k8s-services",
                "text_ref": "k8s-services#k8s-services:0",
            }
        ],
    },
}


def fixture_for_row(row_id: str, question: str) -> dict[str, Any] | None:
    if row_id in CI_FIXTURES:
        return CI_FIXTURES[row_id]
    lowered = question.lower()
    if "kube-scheduler" in lowered or "scheduler" in lowered:
        return CI_FIXTURES["ci-001"]
    if "service" in lowered:
        return CI_FIXTURES["ci-003"]
    if "pod" in lowered:
        return CI_FIXTURES["ci-002"]
    return None


def default_mock_answer(question: str, row_id: str, *, known_bad: bool = False) -> EvalAnswer:
    """Known-bad uses real generate() empty-retrieve abstain (no Groq). CI rows use fixtures."""
    if known_bad or row_id.startswith("bad-"):
        return _abstain_via_generate(question, row_id)
    fixture = fixture_for_row(row_id, question)
    if fixture is None:
        return _abstain_via_generate(question, row_id)
    return EvalAnswer(
        row_id=row_id,
        question=question,
        answer=str(fixture["answer"]),
        abstained=False,
        citations=list(fixture["citations"]),
        contexts=list(fixture["contexts"]),
        run_id=f"eval-{row_id}-{uuid4().hex[:8]}",
        emit_trace=True,
    )


def mock_answer_fn_for_rows(rows: list[Any]) -> AnswerFn:
    by_id = {row.id: row for row in rows}

    def _fn(question: str, row_id: str) -> EvalAnswer:
        row = by_id.get(row_id)
        known_bad = bool(row.known_bad or row.abstain) if row is not None else row_id.startswith("bad-")
        return default_mock_answer(question, row_id, known_bad=known_bad)

    return _fn


def live_answer(question: str, row_id: str) -> EvalAnswer:
    settings = load_settings()
    result = generate(question, settings=settings)
    contexts = _contexts_from_result(result)
    return EvalAnswer(
        row_id=row_id,
        question=question,
        answer=result.answer,
        abstained=result.abstained,
        citations=[ref.model_dump() for ref in result.citations],
        contexts=contexts,
        run_id=result.run_id,
        emit_trace=False,
    )


def eval_settings() -> Settings:
    return load_settings()


def _abstain_via_generate(question: str, row_id: str) -> EvalAnswer:
    settings = _soft_settings()
    result = generate(
        question,
        retrieve_fn=_empty_retrieve,
        chat_fn=_unused_chat,
        settings=settings,
    )
    return EvalAnswer(
        row_id=row_id,
        question=question,
        answer=result.answer or ABSTAIN_ANSWER,
        abstained=True,
        citations=[],
        contexts=[],
        run_id=result.run_id,
        emit_trace=False,
        trace=None,
    )


def _empty_retrieve(_query: str) -> list[ChunkHit]:
    return []


def _unused_chat(_messages: list[dict[str, str]]) -> Any:
    raise RuntimeError("known-bad empty retrieve must not call chat")


def _soft_settings() -> Settings:
    try:
        return load_settings()
    except FileNotFoundError:
        return Settings(
            provider="groq",
            embed_model="nomic-embed-text-v1.5",
            embed_dimensions=768,
            embed_api_base="https://api.groq.com/openai/v1",
            embed_document_prefix="search_document: ",
            chunk_size=512,
            chunk_overlap=64,
            tokenizer="cl100k_base",
            database_url="postgresql://citebench:citebench@127.0.0.1:5432/citebench",
            corpus_dir=REPO_ROOT / "corpus",
            manifest_path=REPO_ROOT / "corpus" / "MANIFEST.md",
            groq_api_key="",
        )


def _contexts_from_result(result: Any) -> list[str]:
    texts: list[str] = []
    for item in getattr(result, "retrieved_chunk_ids", None) or []:
        texts.append(str(item))
    return texts
