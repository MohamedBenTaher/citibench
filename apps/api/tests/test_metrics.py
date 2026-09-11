"""C7: GET /metrics from traces + last eval artifact."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from generate import COST_METHOD_NAME
from manifest import parse_manifest
from metrics import collect_metrics, percentile, render_prometheus
from settings import load_settings
from test_trace import valid_trace
from trace import emit_trace


def _manifest_doc_count() -> int:
    return len(parse_manifest(load_settings().manifest_path))


@pytest.fixture
def eval_store(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Path:
    store = tmp_path / "eval-results"
    store.mkdir()
    monkeypatch.setenv("EVAL_STORE_DIR", str(store))
    return store


def _write_eval(store: Path, *, faithfulness: float = 0.81, precision: float = 0.66) -> None:
    payload = {
        "run_id": "eval-test",
        "mode": "mock",
        "split": "evals/splits/ci.jsonl",
        "metrics": {
            "faithfulness": faithfulness,
            "context_precision": precision,
            "answer_relevancy": 0.5,
        },
        "split_rows": [
            {"id": "ci-001", "faithfulness": faithfulness},
            {"id": "ci-002", "faithfulness": faithfulness},
        ],
    }
    (store / "latest.json").write_text(json.dumps(payload), encoding="utf-8")


def test_percentile_linear_interpolation() -> None:
    assert percentile([], 50) is None
    assert percentile([12.0], 95) == pytest.approx(12.0)
    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert percentile(values, 50) == pytest.approx(30.0)
    assert percentile(values, 95) == pytest.approx(48.0)
    assert percentile(values, 0) == pytest.approx(10.0)
    assert percentile(values, 100) == pytest.approx(50.0)
    with pytest.raises(ValueError):
        percentile(values, 101)


def test_metrics_null_when_no_traces_or_eval(eval_store: Path) -> None:
    snapshot = collect_metrics()
    assert snapshot.latency_ms.p50 is None
    assert snapshot.latency_ms.p95 is None
    assert snapshot.latency_ms.n == 0
    assert snapshot.cost_per_1k_queries_usd.usd is None
    assert snapshot.cost_per_1k_queries_usd.n == 0
    assert snapshot.faithfulness.present is False
    assert snapshot.faithfulness.value is None
    assert snapshot.corpus.docs == _manifest_doc_count()


def test_metrics_percentiles_and_cost_from_traces(eval_store: Path) -> None:
    settings = load_settings()
    latencies = [10.0, 20.0, 30.0, 40.0, 100.0]
    usd_values = [0.001, 0.002, 0.003, 0.004, 0.005]
    for index, (latency, usd) in enumerate(zip(latencies, usd_values, strict=True)):
        emit_trace(
            valid_trace(
                run_id=f"run-{index}",
                latency_ms=latency,
                cost=valid_trace().cost.model_copy(update={"usd_estimate": usd}),
            )
        )
    emit_trace(
        valid_trace(
            run_id="eval-zero",
            latency_ms=0.0,
            cost=valid_trace().cost.model_copy(
                update={
                    "usd_estimate": 0.0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "embed_tokens": 0,
                }
            ),
        )
    )
    snapshot = collect_metrics(settings=settings)
    assert snapshot.latency_ms.n == 5
    assert snapshot.latency_ms.p50 == pytest.approx(30.0)
    assert snapshot.latency_ms.p95 == pytest.approx(88.0)
    assert snapshot.cost_per_1k_queries_usd.n == 5
    assert snapshot.cost_per_1k_queries_usd.usd == pytest.approx(3.0)
    assert COST_METHOD_NAME in snapshot.cost_per_1k_queries_usd.cost_method


def test_metrics_reads_last_eval_artifact(eval_store: Path) -> None:
    _write_eval(eval_store, faithfulness=0.82, precision=0.71)
    snapshot = collect_metrics()
    assert snapshot.faithfulness.present is True
    assert snapshot.faithfulness.value == pytest.approx(0.82)
    assert snapshot.faithfulness.context_precision == pytest.approx(0.71)
    assert snapshot.faithfulness.mode == "mock"
    assert snapshot.faithfulness.run_id == "eval-test"
    assert snapshot.faithfulness.n_scored == 2
    assert "latest.json" in (snapshot.faithfulness.source or "")


def test_metrics_endpoint_json_and_prometheus(eval_store: Path) -> None:
    _write_eval(eval_store, faithfulness=0.9, precision=0.8)
    emit_trace(valid_trace(run_id="prom-1", latency_ms=25.0))
    from main import app

    client = TestClient(app)
    json_response = client.get("/metrics")
    assert json_response.status_code == 200
    body = json_response.json()
    assert body["latency_ms"]["n"] == 1
    assert body["latency_ms"]["p50"] == pytest.approx(25.0)
    assert body["latency_ms"]["p95"] == pytest.approx(25.0)
    assert body["faithfulness"]["value"] == pytest.approx(0.9)
    assert body["cost_per_1k_queries_usd"]["usd"] is not None
    assert "method" in body["latency_ms"]

    prom = client.get("/metrics", params={"format": "prometheus"})
    assert prom.status_code == 200
    assert "text/plain" in prom.headers["content-type"]
    text = prom.text
    assert 'citebench_latency_ms{quantile="0.95"} 25.0' in text
    assert "citebench_cost_per_1k_usd" in text
    assert 'citebench_faithfulness{mode="mock"} 0.9' in text
    assert "citebench_latency_sample_n 1" in text
    assert f"citebench_corpus_docs {_manifest_doc_count()}" in text


def test_prometheus_omits_null_gauges(eval_store: Path) -> None:
    snapshot = collect_metrics()
    text = render_prometheus(snapshot)
    assert "citebench_latency_sample_n 0" in text
    assert 'quantile="0.95"' not in text
    assert "citebench_faithfulness{" not in text
    assert not any(line.startswith("citebench_cost_per_1k_usd ") for line in text.splitlines())


def test_metrics_rejects_unknown_format(eval_store: Path) -> None:
    from main import app

    response = TestClient(app).get("/metrics", params={"format": "csv"})
    assert response.status_code == 400


def test_corpus_measure_from_local_html(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from corpus_measure import measure_corpus
    from manifest import parse_manifest

    settings = load_settings()
    docs = parse_manifest(settings.manifest_path)
    raw = tmp_path / "raw"
    html = "<html><body><main>" + ("scheduler filters and scores nodes. " * 80) + "</main></body></html>"
    for doc in docs:
        dest = raw / doc.id
        dest.mkdir(parents=True)
        (dest / "page.html").write_text(html, encoding="utf-8")

    payload = measure_corpus(settings=settings, fetch_missing=False, raw_root=raw)
    assert payload["docs"] == len(docs)
    assert payload["pages"] == len(docs)
    assert payload["chunks"] is not None and payload["chunks"] >= len(docs)
    assert payload["missing"] == []
    assert payload["measured_under"] == "local-snapshots"
