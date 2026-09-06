"""Known-bad anti-theater asserts.

A known_bad row must *fail* ``naive_success_assert``. If that assert passes,
the pipeline produced a concrete/cited answer and the CI known-bad phase is
unclean.
"""

from __future__ import annotations

from typing import Any

ABSTAIN_ANSWER = "I don't know"


def naive_success_assert(row: Any, result: Any) -> bool:
    """Return True when the run looks like a successful concrete answer."""
    answer = str(getattr(result, "answer", "") or "").strip()
    abstained = bool(getattr(result, "abstained", False))
    citations = list(getattr(result, "citations", None) or [])
    trace = getattr(result, "trace", None)
    if _generate_without_abstain(trace):
        return True
    if abstained and _is_abstain_text(answer) and not citations:
        return False
    if _looks_concrete(answer):
        return True
    if citations:
        return True
    return False


def required_assert_failed(row: Any, result: Any) -> bool:
    """Known-bad rows are required to fail the naive success assert."""
    return not naive_success_assert(row, result)


def _is_abstain_text(answer: str) -> bool:
    return answer == ABSTAIN_ANSWER or answer.lower() in {"i don't know", "i do not know"}


def _looks_concrete(answer: str) -> bool:
    if not answer or _is_abstain_text(answer):
        return False
    lowered = answer.lower()
    if any(token in lowered for token in ("password", "payroll", "innovx", "hunter", "token")):
        return True
    return len(answer.split()) >= 3


def _generate_without_abstain(trace: Any) -> bool:
    spans = list(getattr(trace, "spans", None) or [])
    if not spans:
        return False
    kinds = []
    for span in spans:
        kind = getattr(span, "kind", None)
        kinds.append(kind.value if hasattr(kind, "value") else str(kind or ""))
    return "generate" in kinds and "abstain" not in kinds
