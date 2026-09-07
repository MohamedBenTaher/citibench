"""Groq OpenAI-compatible chat completions. Sole generation provider."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import httpx

from settings import Settings, require_groq_key

log = logging.getLogger("citebench.chat")

_http_client: httpx.Client | None = None
_http_client_lock = threading.Lock()

# llama-3.1-8b-instant is enterprise-only after 2026-08-16. Developer/free
# keys get model_not_found; Groq's published replacement is gpt-oss-20b.
_CHAT_FALLBACKS = ("openai/gpt-oss-20b",)


class ChatError(RuntimeError):
    pass


class ChatResult:
    def __init__(self, content: str, prompt_tokens: int, completion_tokens: int) -> None:
        self.content = content
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


def reset_http_client() -> None:
    global _http_client
    with _http_client_lock:
        if _http_client is not None:
            _http_client.close()
            _http_client = None


def _get_http_client() -> httpx.Client:
    global _http_client
    with _http_client_lock:
        if _http_client is None:
            _http_client = httpx.Client(timeout=httpx.Timeout(60.0, connect=15.0))
        return _http_client


def groq_chat(
    messages: list[dict[str, str]],
    settings: Settings,
    *,
    temperature: float = 0.0,
) -> ChatResult:
    """One Groq /chat/completions call. Requires GROQ_API_KEY."""
    key = require_groq_key(settings)
    url = f"{settings.embed_api_base}/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    models = _chat_candidates(settings.chat_model)
    last_exc: Exception | None = None
    client = _get_http_client()
    for model in models:
        try:
            return _post_chat(client, url, headers, messages, model, temperature)
        except ChatError as exc:
            last_exc = exc
            if _is_model_missing(exc) and model != models[-1]:
                log.warning("Groq chat model %s unavailable (%s); trying %s", model, exc, models[-1])
                continue
            raise
    raise ChatError(f"Groq chat failed after retries: {last_exc}")


def _chat_candidates(configured: str) -> list[str]:
    ordered = [configured.strip()] if configured.strip() else []
    for alias in _CHAT_FALLBACKS:
        if alias not in ordered:
            ordered.append(alias)
    return ordered or list(_CHAT_FALLBACKS)


def _is_model_missing(exc: ChatError) -> bool:
    text = str(exc).lower()
    return "model_not_found" in text or "does not exist" in text or (
        "http 404" in text and "model" in text
    )


def _post_chat(
    client: httpx.Client,
    url: str,
    headers: dict[str, str],
    messages: list[dict[str, str]],
    model: str,
    temperature: float,
) -> ChatResult:
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    delay = 1.0
    last_exc: Exception | None = None
    for _attempt in range(5):
        try:
            response = client.post(url, headers=headers, json=body)
        except httpx.HTTPError as exc:
            last_exc = exc
            time.sleep(delay)
            delay *= 2
            continue
        if response.status_code == 429 or response.status_code >= 500:
            last_exc = ChatError(f"Groq chat HTTP {response.status_code}: {response.text[:300]}")
            time.sleep(delay)
            delay *= 2
            continue
        if response.status_code == 401:
            raise ChatError(
                "GROQ_API_KEY was rejected by Groq (HTTP 401). Check the key at "
                "https://console.groq.com/keys"
            )
        if response.status_code >= 400:
            raise ChatError(f"Groq chat HTTP {response.status_code}: {response.text[:400]}")
        payload = response.json()
        if not isinstance(payload, dict):
            raise ChatError("Groq chat returned a non-object payload")
        return _result_from_payload(payload)
    raise ChatError(f"Groq chat failed after retries: {last_exc}")


def _result_from_payload(payload: dict[str, Any]) -> ChatResult:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ChatError("Groq chat payload missing choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        raise ChatError("Groq chat payload missing message")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ChatError("Groq chat returned empty content")
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    prompt_tokens = _nonneg_int(usage.get("prompt_tokens"), 0)
    completion_tokens = _nonneg_int(usage.get("completion_tokens"), 0)
    return ChatResult(content=content, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)


def _nonneg_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default
