"""Optional single query rewrite (plan 019): one Groq call, never raises.

The rewrite broadens a terse question into a better *retrieval* query. It must
not inject corpus terms that fabricate grounding, and it never changes filters
or product terms: helper questions keep any explicit "about X" prefix intact.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Protocol

from citebench_api.generation.chat import ChatError, ChatResult, groq_chat
from citebench_api.config import Settings

log = logging.getLogger("citebench.rewrite")

MAX_REWRITE_WORDS = 40

_PROMPT = (
    "You rewrite user questions for a keyword+vector retrieval search over a "
    "documentation corpus (Kubernetes, Azure, PostgreSQL, FastAPI, xv6). "
    "Return a single improved search query: keep the user's language and topic, "
    "expand terse questions with likely search keywords, never answer the "
    "question, and never add terms the user did not imply. "
    'Return {"query": "..."} only.'
)


class ChatFn(Protocol):
    def __call__(self, messages: list[dict[str, str]], settings: Settings) -> ChatResult: ...


def parse_rewrite(content: str) -> str | None:
    """Extract the rewritten query from a JSON reply; None when unusable."""
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    query = payload.get("query")
    if not isinstance(query, str):
        return None
    return query.strip() or None


def clamp_max_words(query: str, max_words: int = MAX_REWRITE_WORDS) -> str:
    return " ".join(query.split()[:max_words])


def rewrite_query(
    query: str,
    settings: Settings,
    *,
    chat_fn: Callable[..., Any] | None = None,
) -> str:
    """One Groq call -> a single retrieval query. Returns `query` on any failure."""
    original = (query or "").strip()
    if not original:
        return original
    if getattr(settings, "groq_api_key", "") == "":
        # An unusable key means generate would abstain anyway; do not bill a call.
        return original
    try:
        result = (chat_fn or groq_chat)(
            [
                {"role": "system", "content": _PROMPT},
                {"role": "user", "content": original},
            ],
            settings,
        )
    except ChatError as exc:
        log.warning("query rewrite failed; using the original query: %s", exc)
        return original
    except Exception as exc:  # noqa: BLE001 - a rewrite must never break the ask
        log.warning("query rewrite failed; using the original query: %s", exc)
        return original
    rewritten = parse_rewrite(result.content)
    if not rewritten:
        log.warning("query rewrite returned an unusable reply; using the original query")
        return original
    return clamp_max_words(rewritten)
