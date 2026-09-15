"""Corpus-grounded question suggestions.

Primary path: one Groq call over a compact summary of the corpus (products +
sample document titles). Fallback: the deterministic title templates in db.
No product-name matching in code — the model sees the macro content and writes
the questions.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from typing import Any

from citebench_api.generation.chat import groq_chat
from citebench_api.persistence.db import corpus_macro, corpus_suggestions
from citebench_api.config import Settings

log = logging.getLogger("citebench.suggestions")

_TTL_SECONDS = 1800.0
_CACHE: dict[str, Any] = {"key": None, "at": 0.0, "payload": None}
_LOCK = threading.Lock()

SYSTEM_PROMPT = (
    "You propose example questions for a citation-grounded retrieval bench. "
    "You are given a summary of a frozen document corpus. Write the requested "
    "number of distinct, specific questions that a curious engineer would ask and "
    "that are answerable from the listed material. Mix single-topic questions with "
    "a few comparison questions. Never invent topics that are not in the material. "
    'Return JSON exactly as {"questions": ["...", "..."]}.'
)

_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", flags=re.DOTALL)


def parse_questions(content: str, limit: int) -> list[str]:
    """Extract a clean, deduped question list from a model JSON response."""
    text = (content or "").strip()
    fenced = _FENCE_RE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []
    items = payload.get("questions") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return []
    questions: list[str] = []
    seen: set[str] = set()
    for item in items:
        base = re.sub(r"[.!\s]+$", "", str(item).strip()).rstrip("?").strip()
        if not base:
            continue
        question = f"{base}?"
        if not (8 <= len(question) <= 180) or question in seen:
            continue
        seen.add(question)
        questions.append(question)
        if len(questions) >= limit:
            break
    return questions


def _macro_text(macro: dict[str, Any]) -> str:
    lines = [
        f"Corpus: {macro.get('docs', 0)} documents, {macro.get('chunks', 0)} chunks.",
        "Coverage by product:",
    ]
    for product, topics in (macro.get("products") or {}).items():
        lines.append(f"- {product}: " + "; ".join(topics))
    return "\n".join(lines)


def generate_suggestions(
    settings: Settings,
    conn,
    *,
    limit: int = 6,
) -> dict[str, Any]:
    limit = max(1, min(limit, 12))
    macro = corpus_macro(conn)
    key = (macro.get("docs"), macro.get("chunks"))

    with _LOCK:
        cached = _CACHE["payload"]
        if (
            cached is not None
            and _CACHE["key"] == key
            and (time.time() - float(_CACHE["at"])) < _TTL_SECONDS
        ):
            return cached

    if settings.groq_api_key:
        try:
            result = groq_chat(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"{_macro_text(macro)}\n\nWrite {limit} questions.",
                    },
                ],
                settings,
                temperature=0.5,
            )
            questions = parse_questions(result.content, limit)
            if questions:
                payload = {
                    "suggestions": [
                        {"question": question, "product": "", "doc_id": ""}
                        for question in questions
                    ],
                    "source": "llm",
                    "model": result.model,
                }
                with _LOCK:
                    _CACHE.update(key=key, at=time.time(), payload=payload)
                return payload
        except Exception as exc:  # noqa: BLE001 - fall back to templates
            log.warning("LLM question generation failed; using templates: %s", exc)

    fallback = corpus_suggestions(conn, limit)
    with _LOCK:
        _CACHE.update(key=key, at=time.time(), payload=fallback)
    return fallback
