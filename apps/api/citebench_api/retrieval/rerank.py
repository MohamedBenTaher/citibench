"""FlashRank loader for Contract C (`ms-marco-TinyBERT-L-2-v2`)."""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path
from threading import Lock
from typing import Any

try:
    from flashrank import Ranker, RerankRequest
except ImportError:  # optional at import time; retrieve falls back if load fails
    Ranker = None
    RerankRequest = None

DEFAULT_RERANK_MODEL = "ms-marco-TinyBERT-L-2-v2"
DEFAULT_CACHE_DIR = "/tmp/flashrank"

_lock = Lock()
_ranker: Any = None
_ranker_model: str | None = None
_ranker_max_length: int = 512


class RerankError(RuntimeError):
    pass


def reset_ranker_cache() -> None:
    global _ranker, _ranker_model, _ranker_max_length
    with _lock:
        _ranker = None
        _ranker_model = None
        _ranker_max_length = 512


def warmup_ranker(model_name: str = DEFAULT_RERANK_MODEL, max_length: int = 512) -> None:
    load_ranker(model_name, max_length=max_length)


def load_ranker(model_name: str = DEFAULT_RERANK_MODEL, max_length: int = 512) -> Any:
    """Load FlashRank once per process per (model, max_length) pair."""
    global _ranker, _ranker_model, _ranker_max_length
    if Ranker is None:
        raise RerankError("FlashRank is not installed")
    with _lock:
        if (
            _ranker is not None
            and _ranker_model == model_name
            and _ranker_max_length == max_length
        ):
            return _ranker
        cache_dir = Path(os.environ.get("FLASHRANK_CACHE_DIR", DEFAULT_CACHE_DIR))
        cache_dir.mkdir(parents=True, exist_ok=True)
        _ranker = Ranker(model_name=model_name, cache_dir=str(cache_dir), max_length=max_length)
        _ranker_model = model_name
        _ranker_max_length = max_length
        return _ranker


def flashrank_rerank(
    query: str,
    hits: Sequence[Any],
    *,
    model_name: str = DEFAULT_RERANK_MODEL,
    max_length: int = 512,
) -> list[float]:
    """Score fused hits in input order. Raises RerankError on load/score failure."""
    if not hits:
        return []
    ranker = load_ranker(model_name, max_length=max_length)
    if RerankRequest is None:
        raise RerankError("FlashRank is not installed")
    passages = [
        {"id": index, "text": hit.text, "meta": {"chunk_id": hit.chunk_id}}
        for index, hit in enumerate(hits)
    ]
    results = ranker.rerank(RerankRequest(query=query, passages=passages))
    by_index: dict[int, float] = {}
    for row in results:
        if isinstance(row, dict):
            by_index[int(row["id"])] = float(row["score"])
        else:
            by_index[int(row.id)] = float(row.score)
    missing = [index for index in range(len(hits)) if index not in by_index]
    if missing:
        raise RerankError(f"FlashRank omitted scores for input indexes {missing}")
    return [by_index[index] for index in range(len(hits))]
