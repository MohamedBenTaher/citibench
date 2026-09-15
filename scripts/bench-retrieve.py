#!/usr/bin/env python
"""Retrieve-only latency bench at corpus scale.

Local and manual (needs Postgres + the nomic cache); not run in CI. Records
p50/p95 retrieve latency with the corpus size and the active retrieve config so
the "no ANN index yet" decision stays measured.

    .venv/bin/python scripts/bench-retrieve.py --n 50
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "api"))

from citebench_api.persistence.db import connect, corpus_stats, ensure_schema  # noqa: E402
from citebench_api.tracing.metrics import percentile  # noqa: E402
from citebench_api.retrieval.retrieve import (  # noqa: E402
    _default_embed,
    flashrank_rerank,
    retrieve,
    retrieve_config_from_settings,
    rrf_fuse,
    search_fts,
    search_vector,
)
from citebench_api.config import load_settings  # noqa: E402

DEFAULT_SPLIT = ROOT / "evals" / "splits" / "ci.jsonl"
DEFAULT_OUT = ROOT / "evals" / "results" / "retrieve-bench.json"
FALLBACK_QUERIES = [
    "kubernetes pods",
    "azure managed identity",
    "postgresql write ahead log",
    "fastapi path parameters",
]


def _load_queries(path: Path) -> list[str]:
    if not path.is_file():
        return list(FALLBACK_QUERIES)
    questions: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        question = str(payload.get("question") or "").strip()
        if question:
            questions.append(question)
    return questions or list(FALLBACK_QUERIES)


def _stage_breakdown(settings, config, queries: list[str], reps: int = 4) -> dict[str, float]:
    """Mean ms per retrieve sub-stage, warmed. Isolates the ANN decision."""

    def timed(fn) -> float:
        fn()
        started = time.perf_counter()
        for _ in range(reps):
            fn()
        return (time.perf_counter() - started) / reps * 1000.0

    embed = _default_embed(settings)
    query = queries[0]
    mean_embed = timed(lambda: embed(query))
    with connect(settings.database_url) as conn:
        vec = embed(query)
        mean_vector = timed(lambda: search_vector(conn, vec, config.dense_k, config.filters))
        mean_fts = timed(lambda: search_fts(conn, query, config.lexical_k, config.filters))
        dense = search_vector(conn, vec, config.dense_k, config.filters)
        lexical = search_fts(conn, query, config.lexical_k, config.filters)
        pool = rrf_fuse(dense, lexical, k=config.rrf_k)[: config.rerank_pool]
        mean_rerank = (
            timed(lambda: flashrank_rerank(query, pool)) if config.rerank_enabled else 0.0
        )
    return {
        "embed_ms": round(mean_embed, 3),
        "vector_ms": round(mean_vector, 3),
        "fts_ms": round(mean_fts, 3),
        "rerank_ms": round(mean_rerank, 3),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Retrieve latency bench.")
    parser.add_argument("--split", default=str(DEFAULT_SPLIT))
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument(
        "--variant",
        default=None,
        metavar="JSON",
        help="RetrieveConfig overrides to bench (e.g. '{\"rerank_pool\": 20}'); written into the artifact.",
    )
    args = parser.parse_args(argv)

    settings = load_settings()
    queries = _load_queries(Path(args.split))
    config = retrieve_config_from_settings(settings)
    variant_overrides: dict[str, Any] | None = None
    if args.variant:
        variant_overrides = json.loads(args.variant)
        if not isinstance(variant_overrides, dict):
            raise SystemExit("--variant must be a JSON object")
        for key, value in variant_overrides.items():
            setattr(config, key, value)

    with connect(settings.database_url) as conn:
        ensure_schema(conn)
        stats = corpus_stats(conn)
    chunk_count = int(stats["chunk_count"])
    if chunk_count <= 0:
        print("corpus is empty; ingest first", file=sys.stderr)
        return 2

    # Warm the embed/rerank path once so the sample is steady-state.
    retrieve(queries[0], config, settings=settings)

    latencies: list[float] = []
    for index in range(args.n):
        question = queries[index % len(queries)]
        started = time.perf_counter()
        retrieve(question, config, settings=settings)
        latencies.append((time.perf_counter() - started) * 1000.0)

    stages = _stage_breakdown(settings, config, queries)

    payload = {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "measured_under": f"retrieve-bench-{datetime.now(timezone.utc).date().isoformat()}",
        "n": len(latencies),
        "doc_count": int(stats["doc_count"]),
        "page_count": int(stats["page_count"]),
        "chunk_count": chunk_count,
        "mean_ms": round(sum(latencies) / len(latencies), 3),
        "p50_ms": round(float(percentile(latencies, 50) or 0.0), 3),
        "p95_ms": round(float(percentile(latencies, 95) or 0.0), 3),
        "min_ms": round(min(latencies), 3),
        "max_ms": round(max(latencies), 3),
        "stage_mean_ms": stages,
        "config": {
            "top_k": config.top_k,
            "dense_k": config.dense_k,
            "lexical_k": config.lexical_k,
            "rerank_pool": config.rerank_pool,
            "retrieval_mode": config.retrieval_mode,
            "rerank_enabled": config.rerank_enabled,
            "rerank_max_length": config.rerank_max_length,
        },
        "variant_overrides": variant_overrides,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"retrieve n={payload['n']} chunks={chunk_count} "
        f"p50={payload['p50_ms']}ms p95={payload['p95_ms']}ms"
    )
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
