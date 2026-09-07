"""C7 scrape metrics: latency percentiles, cost/1k, last-eval faithfulness."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from citebench.eval.store import read_latest, resolve_eval_store_dir
from db import connect, corpus_stats
from generate import COST_METHOD_NAME, cost_method_string
from manifest import parse_manifest
from settings import Settings, load_settings
from trace import RunTrace, list_traces

LATENCY_METHOD = (
    "linear interpolation over RunTrace.latency_ms for traces with latency_ms > 0; "
    "p50=quantile 0.50, p95=quantile 0.95; n=0 yields null"
)
COST_PER_1K_METHOD = (
    "mean(CostEstimate.usd_estimate)*1000 over traces with usd_estimate > 0 "
    f"or any billed token count > 0; rates from {COST_METHOD_NAME} / config.yaml"
)
FAITHFULNESS_METHOD = (
    "metrics.faithfulness from the last evals/results/latest.json artifact "
    "(C6 RAGAS CI). Null when the file is missing. mode is recorded (mock|live)"
)
CORPUS_DOCS_METHOD = "count of pinned URLs in corpus/MANIFEST.md"
CORPUS_PAGES_METHOD = (
    "HTML snapshot = 1 page (parse_doc._parse_html); PDF = PdfReader page count"
)
CORPUS_CHUNKS_METHOD = (
    "tiktoken cl100k_base windows of 512 tokens / 64 overlap after parse_doc"
)


class LatencyMetrics(BaseModel):
    p50: float | None
    p95: float | None
    n: int
    method: str = LATENCY_METHOD


class CostPer1kMetrics(BaseModel):
    usd: float | None
    n: int
    method: str
    cost_method: str = COST_METHOD_NAME


class FaithfulnessMetrics(BaseModel):
    value: float | None
    context_precision: float | None = None
    present: bool = False
    mode: str | None = None
    source: str | None = None
    run_id: str | None = None
    split: str | None = None
    n_scored: int | None = None
    method: str = FAITHFULNESS_METHOD


class CorpusMetrics(BaseModel):
    docs: int | None
    pages: int | None
    chunks: int | None
    source: str
    method: dict[str, str] = Field(
        default_factory=lambda: {
            "docs": CORPUS_DOCS_METHOD,
            "pages": CORPUS_PAGES_METHOD,
            "chunks": CORPUS_CHUNKS_METHOD,
        }
    )
    measured_under: str | None = None


class MetricsSnapshot(BaseModel):
    as_of: datetime
    latency_ms: LatencyMetrics
    cost_per_1k_queries_usd: CostPer1kMetrics
    faithfulness: FaithfulnessMetrics
    corpus: CorpusMetrics


def percentile(values: list[float], q: float) -> float | None:
    """Inclusive linear interpolation. q is 0–100. Empty input is null."""
    if not values:
        return None
    if q < 0 or q > 100:
        raise ValueError("quantile must be in [0, 100]")
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (q / 100.0) * (len(ordered) - 1)
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    if lo == hi:
        return float(ordered[lo])
    frac = rank - lo
    return float(ordered[lo] * (1.0 - frac) + ordered[hi] * frac)


def collect_metrics(*, settings: Settings | None = None) -> MetricsSnapshot:
    resolved = settings if settings is not None else load_settings()
    traces = list_traces(settings=resolved)
    latencies = [item.latency_ms for item in traces if item.latency_ms > 0]
    cost_rows = [item for item in traces if _has_billed_cost(item)]
    mean_usd = (
        sum(item.cost.usd_estimate for item in cost_rows) / len(cost_rows) if cost_rows else None
    )
    cost_per_1k = None if mean_usd is None else round(mean_usd * 1000.0, 8)
    try:
        method_string = cost_method_string(resolved)
    except Exception:
        method_string = COST_PER_1K_METHOD
    return MetricsSnapshot(
        as_of=datetime.now(timezone.utc),
        latency_ms=LatencyMetrics(
            p50=_round_ms(percentile(latencies, 50)),
            p95=_round_ms(percentile(latencies, 95)),
            n=len(latencies),
        ),
        cost_per_1k_queries_usd=CostPer1kMetrics(
            usd=cost_per_1k,
            n=len(cost_rows),
            method=COST_PER_1K_METHOD,
            cost_method=method_string,
        ),
        faithfulness=_faithfulness_from_artifact(),
        corpus=_corpus_metrics(resolved),
    )


def render_prometheus(snapshot: MetricsSnapshot) -> str:
    """Prometheus text 0.0.4. Null gauges are omitted so scrapers do not read 0."""
    lines: list[str] = [
        "# HELP citebench_latency_ms Generate/ask latency percentiles in milliseconds.",
        "# TYPE citebench_latency_ms gauge",
    ]
    if snapshot.latency_ms.p50 is not None:
        lines.append(f'citebench_latency_ms{{quantile="0.5"}} {snapshot.latency_ms.p50}')
    if snapshot.latency_ms.p95 is not None:
        lines.append(f'citebench_latency_ms{{quantile="0.95"}} {snapshot.latency_ms.p95}')
    lines.extend(
        [
            "# HELP citebench_latency_sample_n Traces with latency_ms > 0.",
            "# TYPE citebench_latency_sample_n gauge",
            f"citebench_latency_sample_n {snapshot.latency_ms.n}",
            "# HELP citebench_cost_per_1k_usd Mean citebench.cost.v1 USD * 1000.",
            "# TYPE citebench_cost_per_1k_usd gauge",
        ]
    )
    if snapshot.cost_per_1k_queries_usd.usd is not None:
        lines.append(f"citebench_cost_per_1k_usd {snapshot.cost_per_1k_queries_usd.usd}")
    lines.extend(
        [
            "# HELP citebench_cost_sample_n Traces included in cost/1k.",
            "# TYPE citebench_cost_sample_n gauge",
            f"citebench_cost_sample_n {snapshot.cost_per_1k_queries_usd.n}",
            "# HELP citebench_faithfulness Last eval artifact faithfulness (may be mock).",
            "# TYPE citebench_faithfulness gauge",
        ]
    )
    if snapshot.faithfulness.value is not None:
        mode = snapshot.faithfulness.mode or "unknown"
        lines.append(f'citebench_faithfulness{{mode="{_prom_label(mode)}"}} {snapshot.faithfulness.value}')
    if snapshot.faithfulness.context_precision is not None:
        lines.extend(
            [
                "# HELP citebench_context_precision Last eval artifact context precision.",
                "# TYPE citebench_context_precision gauge",
                (
                    f"citebench_context_precision{{mode="
                    f'"{_prom_label(snapshot.faithfulness.mode or "unknown")}"}} '
                    f"{snapshot.faithfulness.context_precision}"
                ),
            ]
        )
    lines.extend(
        [
            "# HELP citebench_corpus_docs Pinned MANIFEST documents.",
            "# TYPE citebench_corpus_docs gauge",
        ]
    )
    if snapshot.corpus.docs is not None:
        lines.append(f"citebench_corpus_docs {snapshot.corpus.docs}")
    if snapshot.corpus.pages is not None:
        lines.extend(
            [
                "# HELP citebench_corpus_pages Indexed or measured pages.",
                "# TYPE citebench_corpus_pages gauge",
                f"citebench_corpus_pages {snapshot.corpus.pages}",
            ]
        )
    if snapshot.corpus.chunks is not None:
        lines.extend(
            [
                "# HELP citebench_corpus_chunks Indexed or measured chunks.",
                "# TYPE citebench_corpus_chunks gauge",
                f"citebench_corpus_chunks {snapshot.corpus.chunks}",
            ]
        )
    return "\n".join(lines) + "\n"


def load_corpus_artifact(path: Path | None = None) -> dict[str, Any] | None:
    dest = path if path is not None else _default_corpus_artifact()
    if not dest.is_file():
        return None
    try:
        payload = json.loads(dest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _faithfulness_from_artifact() -> FaithfulnessMetrics:
    store = resolve_eval_store_dir()
    payload = read_latest(store)
    if not payload:
        return FaithfulnessMetrics(value=None, present=False)
    metrics = payload.get("metrics")
    if not isinstance(metrics, dict):
        return FaithfulnessMetrics(value=None, present=False, source=str(store / "latest.json"))
    faith = _optional_float(metrics.get("faithfulness"))
    precision = _optional_float(metrics.get("context_precision"))
    split_rows = payload.get("split_rows")
    n_scored = None
    if isinstance(split_rows, list):
        n_scored = sum(1 for row in split_rows if isinstance(row, dict) and row.get("faithfulness") is not None)
    return FaithfulnessMetrics(
        value=faith,
        context_precision=precision,
        present=faith is not None,
        mode=str(payload.get("mode") or "") or None,
        source=str(store / "latest.json"),
        run_id=str(payload.get("run_id") or "") or None,
        split=str(payload.get("split") or "") or None,
        n_scored=n_scored,
    )


def _corpus_metrics(settings: Settings) -> CorpusMetrics:
    manifest_docs = _manifest_doc_count(settings)
    db_stats = _try_corpus_stats(settings)
    if db_stats and int(db_stats.get("doc_count") or 0) > 0:
        return CorpusMetrics(
            docs=int(db_stats["doc_count"]),
            pages=_optional_int(db_stats.get("page_count")),
            chunks=_optional_int(db_stats.get("chunk_count")),
            source="database",
            measured_under=None,
        )
    artifact = load_corpus_artifact()
    if artifact:
        return CorpusMetrics(
            docs=_optional_int(artifact.get("docs")) or manifest_docs,
            pages=_optional_int(artifact.get("pages")),
            chunks=_optional_int(artifact.get("chunks")),
            source="evals/results/corpus.json",
            measured_under=str(artifact.get("measured_under") or "") or None,
        )
    pages = manifest_docs
    return CorpusMetrics(
        docs=manifest_docs,
        pages=pages,
        chunks=None,
        source="manifest",
        measured_under=None,
    )


def _manifest_doc_count(settings: Settings) -> int | None:
    try:
        return len(parse_manifest(settings.manifest_path))
    except Exception:
        return None


def _try_corpus_stats(settings: Settings) -> dict[str, Any] | None:
    try:
        with connect(settings.database_url) as conn:
            return corpus_stats(conn)
    except Exception:
        return None


def _has_billed_cost(trace: RunTrace) -> bool:
    cost = trace.cost
    if cost.usd_estimate > 0:
        return True
    return any(
        count > 0
        for count in (cost.prompt_tokens, cost.completion_tokens, cost.embed_tokens)
    )


def _default_corpus_artifact() -> Path:
    return resolve_eval_store_dir() / "corpus.json"


def _round_ms(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 3)


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _prom_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", " ").replace('"', '\\"')
