"""nomic-embed-text-v1.5 embeddings (768-d).

Groq hosted this model, then removed it (`model_not_found` on both
`nomic-embed-text-v1.5` and `nomic-embed-text-v1_5`). Citebench still
uses those open 768-d weights: try Groq `/embeddings` when a key is
present, then fall back to local ONNX via fastembed. That is not a
second billed embed provider. Prefixes stay `search_document:` /
`search_query:`.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from threading import Lock
from typing import Any

import httpx

from settings import Settings

try:
    from fastembed import TextEmbedding
except ImportError:  # optional at import time; local fallback raises EmbedError
    TextEmbedding = None

log = logging.getLogger("citebench.embed")

# Groq SDK stubs used an underscore id for the same weights.
_MODEL_ALIASES = ("nomic-embed-text-v1.5", "nomic-embed-text-v1_5")
_LOCAL_NOMIC = "nomic-ai/nomic-embed-text-v1.5"
_DEFAULT_CACHE = Path("/tmp/nomic-embed")

_lock = Lock()
_local_model: Any = None
_groq_model_missing = False


class EmbedError(RuntimeError):
    pass


def reset_embed_cache() -> None:
    global _local_model, _groq_model_missing
    with _lock:
        _local_model = None
        _groq_model_missing = False


def embed_texts(
    texts: list[str],
    settings: Settings,
    *,
    batch_size: int = 32,
    prefix: str | None = None,
) -> list[list[float]]:
    """Embed passages. Default prefix is the document prefix. Empty input returns []."""
    if not texts:
        return []
    used_prefix = settings.embed_document_prefix if prefix is None else prefix
    prefixed = [used_prefix + text for text in texts]
    if (
        settings.embed_backend == "groq_then_local"
        and settings.groq_api_key
        and not _groq_model_missing
    ):
        try:
            return _embed_via_groq(prefixed, settings, batch_size=batch_size)
        except EmbedError as exc:
            if _should_fallback_local(exc, settings):
                log.warning(
                    "Groq no longer hosts %s (%s); using local ONNX %s",
                    settings.embed_model,
                    exc,
                    _LOCAL_NOMIC,
                )
                _mark_groq_missing()
            else:
                raise
    return _embed_local(prefixed, settings.embed_dimensions, batch_size=batch_size)


def embed_query(query: str, settings: Settings) -> list[float]:
    """Embed one query with the nomic `search_query:` prefix."""
    vectors = embed_texts([query], settings, prefix=settings.embed_query_prefix)
    if len(vectors) != 1:
        raise EmbedError(f"expected 1 query embedding, got {len(vectors)}")
    return vectors[0]


def _should_fallback_local(exc: EmbedError, settings: Settings) -> bool:
    if "api.groq.com" not in settings.embed_api_base:
        return False
    text = str(exc).lower()
    return "model_not_found" in text or "does not exist" in text or (
        "http 404" in text and "model" in text
    )


def _mark_groq_missing() -> None:
    global _groq_model_missing
    _groq_model_missing = True


def _embed_via_groq(
    prefixed: list[str],
    settings: Settings,
    *,
    batch_size: int,
) -> list[list[float]]:
    key = settings.groq_api_key
    vectors: list[list[float]] = []
    with httpx.Client(timeout=httpx.Timeout(60.0, connect=15.0)) as client:
        for start in range(0, len(prefixed), batch_size):
            batch = prefixed[start : start + batch_size]
            vectors.extend(_embed_batch(client, batch, settings, key))
    if len(vectors) != len(prefixed):
        raise EmbedError(f"expected {len(prefixed)} embeddings, got {len(vectors)}")
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
    for _attempt in range(5):
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


def _cache_dir() -> Path:
    raw = os.environ.get("NOMIC_CACHE_DIR") or os.environ.get("FASTEMBED_CACHE_PATH") or str(_DEFAULT_CACHE)
    path = Path(raw)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_local_model() -> Any:
    global _local_model
    with _lock:
        if _local_model is not None:
            return _local_model
        if TextEmbedding is None:
            raise EmbedError(
                "fastembed is required for local nomic-embed-text-v1.5. "
                "Install apps/api/requirements.txt"
            )
        _local_model = TextEmbedding(model_name=_LOCAL_NOMIC, cache_dir=str(_cache_dir()))
        return _local_model


def _embed_local(
    prefixed: list[str],
    dimensions: int,
    *,
    batch_size: int,
) -> list[list[float]]:
    model = _load_local_model()
    vectors: list[list[float]] = []
    for item in model.embed(prefixed, batch_size=batch_size):
        row = [float(x) for x in item]
        if len(row) != dimensions:
            raise EmbedError(f"expected {dimensions}-d embedding, got {len(row)}")
        vectors.append(row)
    if len(vectors) != len(prefixed):
        raise EmbedError(f"expected {len(prefixed)} embeddings, got {len(vectors)}")
    return vectors


def _vectors_from_payload(payload: dict, dimensions: int, expected: int) -> list[list[float]]:
    rows = payload.get("data")
    if not isinstance(rows, list) or len(rows) != expected:
        raise EmbedError(f"expected {expected} embeddings, got {getattr(rows, '__len__', lambda: 'missing')()}")
    ordered = sorted(rows, key=lambda row: int(row.get("index", 0)))
    vectors: list[list[float]] = []
    for row in ordered:
        embedding = row.get("embedding")
        if not isinstance(embedding, list) or len(embedding) != dimensions:
            got = len(embedding) if isinstance(embedding, list) else type(embedding).__name__
            raise EmbedError(f"expected {dimensions}-d embedding, got {got}")
        vectors.append([float(x) for x in embedding])
    return vectors
