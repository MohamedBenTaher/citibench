"""Groq OpenAI-compatible embeddings for nomic-embed-text-v1.5 (768-d)."""

from __future__ import annotations

import time

import httpx

from settings import Settings, require_groq_key

# Groq lists the same model as nomic-embed-text-v1_5 in some SDK stubs.
_MODEL_ALIASES = ("nomic-embed-text-v1.5", "nomic-embed-text-v1_5")


class EmbedError(RuntimeError):
    pass


def embed_texts(texts: list[str], settings: Settings, *, batch_size: int = 32) -> list[list[float]]:
    """Embed passages with the document prefix. Empty input returns []."""
    if not texts:
        return []
    key = require_groq_key(settings)
    prefixed = [settings.embed_document_prefix + text for text in texts]
    vectors: list[list[float]] = []
    with httpx.Client(timeout=httpx.Timeout(60.0, connect=15.0)) as client:
        for start in range(0, len(prefixed), batch_size):
            batch = prefixed[start : start + batch_size]
            vectors.extend(_embed_batch(client, batch, settings, key))
    if len(vectors) != len(texts):
        raise EmbedError(f"expected {len(texts)} embeddings, got {len(vectors)}")
    return vectors


def _embed_batch(
    client: httpx.Client,
    batch: list[str],
    settings: Settings,
    key: str,
) -> list[list[float]]:
    models = _model_candidates(settings.embed_model)
    last_error: Exception | None = None
    for model in models:
        try:
            payload = _post_embeddings(client, settings.embed_api_base, key, model, batch)
            return _vectors_from_payload(payload, settings.embed_dimensions, len(batch))
        except EmbedError as exc:
            last_error = exc
            if "model" in str(exc).lower() and "not" in str(exc).lower() and model != models[-1]:
                continue
            raise
    raise EmbedError(str(last_error) if last_error else "embed failed")


def _model_candidates(configured: str) -> list[str]:
    ordered = [configured]
    for alias in _MODEL_ALIASES:
        if alias not in ordered:
            ordered.append(alias)
    return ordered


def _post_embeddings(
    client: httpx.Client,
    api_base: str,
    key: str,
    model: str,
    batch: list[str],
) -> dict:
    url = f"{api_base}/embeddings"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    body = {"model": model, "input": batch, "encoding_format": "float"}
    delay = 1.0
    last_exc: Exception | None = None
    for attempt in range(5):
        try:
            response = client.post(url, headers=headers, json=body)
        except httpx.HTTPError as exc:
            last_exc = exc
            time.sleep(delay)
            delay *= 2
            continue
        if response.status_code == 429 or response.status_code >= 500:
            last_exc = EmbedError(f"Groq embeddings HTTP {response.status_code}: {response.text[:300]}")
            time.sleep(delay)
            delay *= 2
            continue
        if response.status_code == 401:
            raise EmbedError(
                "GROQ_API_KEY was rejected by Groq (HTTP 401). Check the key at "
                "https://console.groq.com/keys"
            )
        if response.status_code >= 400:
            raise EmbedError(f"Groq embeddings HTTP {response.status_code}: {response.text[:400]}")
        data = response.json()
        if not isinstance(data, dict):
            raise EmbedError("Groq embeddings returned a non-object payload")
        return data
    raise EmbedError(f"Groq embeddings failed after retries: {last_exc}")


def _vectors_from_payload(payload: dict, dimensions: int, expected: int) -> list[list[float]]:
    rows = payload.get("data")
    if not isinstance(rows, list) or len(rows) != expected:
        raise EmbedError(f"Groq embeddings data length {getattr(rows, '__len__', lambda: 'missing')()} != {expected}")
    ordered = sorted(rows, key=lambda row: int(row.get("index", 0)))
    vectors: list[list[float]] = []
    for row in ordered:
        embedding = row.get("embedding")
        if not isinstance(embedding, list) or len(embedding) != dimensions:
            got = len(embedding) if isinstance(embedding, list) else type(embedding).__name__
            raise EmbedError(f"expected {dimensions}-d embedding, got {got}")
        vectors.append([float(x) for x in embedding])
    return vectors
