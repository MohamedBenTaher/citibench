"""Groq OpenAI-compatible chat completions. Sole generation provider."""

from __future__ import annotations

import time
from typing import Any

import httpx

from settings import Settings, require_groq_key


class ChatError(RuntimeError):
    pass


class ChatResult:
    def __init__(self, content: str, prompt_tokens: int, completion_tokens: int) -> None:
        self.content = content
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


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
    body: dict[str, Any] = {
        "model": settings.chat_model,
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    delay = 1.0
    last_exc: Exception | None = None
    with httpx.Client(timeout=httpx.Timeout(60.0, connect=15.0)) as client:
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
