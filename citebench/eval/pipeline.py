"""Eval answer pipeline: fixture (CI mock) or injected / live generate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol
from uuid import uuid4

import citebench.eval.paths  # noqa: F401

from citebench.eval.paths import REPO_ROOT
from citebench_api.generation.generate import ABSTAIN_ANSWER, generate
from citebench_api.retrieval.retrieve import ChunkHit
from citebench_api.config import Settings, load_settings

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


def _fixture(answer: str, doc_ids: list[str]) -> dict[str, Any]:
    return {
        "answer": answer,
        "contexts": [answer],
        "citations": [
            {"chunk_id": f"{doc}:0", "doc_id": doc, "text_ref": f"{doc}#{doc}:0"}
            for doc in doc_ids
        ],
    }


# Grounded mock answers for evals/splits/ci.jsonl (C6 mock CI). Live mode (015)
# calls the real generate() and ignores these.
CI_FIXTURES: dict[str, dict[str, Any]] = {
    "ci-001": _fixture(
        "The kube-scheduler assigns unscheduled Pods to nodes using filtering and scoring plugins.",
        ["k8s-docs-reference-command-line-tools-reference-kube-scheduler"],
    ),
    "ci-002": _fixture(
        "A Pod is the smallest deployable unit, one or more containers scheduled together onto a node.",
        ["k8s-docs-concepts-workloads-pods"],
    ),
    "ci-003": _fixture(
        "A Service exposes a set of Pods behind a stable virtual IP and endpoint, and does not schedule them.",
        ["k8s-docs-concepts-services-networking-service"],
    ),
    "ci-004": _fixture(
        "Ingress manages external HTTP(S) access to Services in a cluster using rules.",
        ["k8s-docs-concepts-services-networking-ingress"],
    ),
    "ci-005": _fixture(
        "Secrets hold sensitive data such as passwords and tokens, kept separately from Pod specs and mounted or exposed to containers.",
        ["k8s-docs-concepts-configuration-secret"],
    ),
    "ci-006": _fixture(
        "Changes are written to the PostgreSQL write-ahead log before the data files, so the database can recover after a crash.",
        ["postgres-docs-current-wal.html"],
    ),
    "ci-007": _fixture(
        "Path parameters are declared as function arguments with Python type hints, and FastAPI validates and converts them.",
        ["fastapi-tutorial-path-params"],
    ),
    "ci-008": _fixture(
        "AKS is a managed Kubernetes service that runs the control plane on Azure.",
        ["azure-en-us-azure-aks-what-is-aks"],
    ),
    "ci-009": _fixture(
        "Managed identities give Azure resources an identity in Microsoft Entra ID so code can authenticate without storing credentials.",
        ["azure-en-us-entra-identity-managed-identities-azure-resources-overview"],
    ),
    "ci-010": _fixture(
        "A trap transfers control from user space to the kernel, where usertrap and syscall dispatch handle the request.",
        ["xv6-6.828-2024-xv6-book-riscv-rev4.pdf"],
    ),
    "ci-020": _fixture(
        "ConfigMaps hold non-confidential configuration, while Secrets hold sensitive data such as credentials and tokens.",
        ["k8s-docs-concepts-configuration-configmap", "k8s-docs-concepts-configuration-secret"],
    ),
    "ci-021": _fixture(
        "A Service exposes Pods on a stable endpoint inside the cluster, while Ingress routes external HTTP(S) traffic to Services.",
        ["k8s-docs-concepts-services-networking-service", "k8s-docs-concepts-services-networking-ingress"],
    ),
    "ci-022": _fixture(
        "Path parameters are part of the URL path and required, while query parameters follow ?key=value and are optional by default.",
        ["fastapi-tutorial-path-params", "fastapi-tutorial-query-params"],
    ),
    "ci-023": _fixture(
        "xv6 logs file-system operations for crash consistency, and PostgreSQL writes changes to the write-ahead log before data files for recovery.",
        ["xv6-6.828-2024-xv6-book-riscv-rev4.pdf", "postgres-docs-current-wal.html"],
    ),
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
