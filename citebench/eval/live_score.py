"""Score a collected answers JSONL with live RAGAS (Groq judge + local nomic).

Runs in the EVAL env (`.venv-eval`, see apps/api/requirements-eval.txt) — never
the runtime env, because ragas pulls langchain/langgraph 1.x. The answers file
is produced by `python -m citebench.eval.answers` in the runtime env.

Keep the OpenAI SDK (a transitive ragas dep) out of the loop: the judge is
Groq and the embeddings are local nomic ONNX.

Usage:
    .venv-eval/bin/python -m citebench.eval.live_score \
        --answers /tmp/citebench-run/answers.jsonl --out evals/results/live.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

METHOD = "citebench.eval.ragas.v1.live"
METRIC_NAMES = ("faithfulness", "context_precision", "answer_relevancy")


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    try:
        if math.isnan(float(value)):
            return None
    except (TypeError, ValueError):
        return value
    return float(value)


class NomicEmbeddings:
    """langchain Embeddings backed by local nomic-embed-text-v1.5 ONNX."""

    def __init__(self, cache_dir: str) -> None:
        from fastembed import TextEmbedding

        self._model = TextEmbedding(
            model_name="nomic-ai/nomic-embed-text-v1.5", cache_dir=cache_dir
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [
            [float(x) for x in vector]
            for vector in self._model.embed([f"search_document: {text}" for text in texts])
        ]

    def embed_query(self, text: str) -> list[float]:
        vectors = list(self._model.embed([f"search_query: {text}"]))
        return [float(x) for x in vectors[0]]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live RAGAS scoring over collected answers.")
    parser.add_argument("--answers", required=True)
    parser.add_argument("--out", default="evals/results/live.json")
    parser.add_argument("--threshold", type=float, default=0.7)
    parser.add_argument("--chat-model", default=os.environ.get("GROQ_CHAT_MODEL", "openai/gpt-oss-20b"))
    args = parser.parse_args(argv)

    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        print("GROQ_API_KEY is required for live RAGAS", file=sys.stderr)
        return 2

    try:
        import ragas
        from langchain_groq import ChatGroq
        from ragas import EvaluationDataset, evaluate
        from ragas.dataset_schema import SingleTurnSample
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from ragas.llms import LangchainLLMWrapper
        from ragas.metrics import answer_relevancy, context_precision, faithfulness
        from ragas.run_config import RunConfig
    except Exception as exc:  # noqa: BLE001
        print(f"live RAGAS requires the eval venv (.venv-eval): {exc}", file=sys.stderr)
        return 3

    started = datetime.now(timezone.utc)
    rows = [json.loads(line) for line in Path(args.answers).read_text(encoding="utf-8").splitlines() if line.strip()]

    scorable = [
        row
        for row in rows
        if not row.get("abstained")
        and not row.get("abstain")
        and not row.get("known_bad")
        and row.get("contexts")
    ]

    metrics_mean: dict[str, float | None] = {name: None for name in METRIC_NAMES}
    per_row: dict[str, dict[str, float | None]] = {}
    judge_error: str | None = None

    if scorable:
        cache_dir = os.environ.get("NOMIC_CACHE_DIR", "/tmp/nomic-embed")
        judge = LangchainLLMWrapper(
            ChatGroq(
                model=args.chat_model,
                api_key=api_key,
                temperature=0.0,
                max_tokens=int(os.environ.get("RAGAS_JUDGE_MAX_TOKENS", "1024")),
                timeout=float(os.environ.get("RAGAS_JUDGE_TIMEOUT", "120")),
            )
        )
        run_config = RunConfig(
            max_workers=int(os.environ.get("RAGAS_MAX_WORKERS", "1")),
            timeout=int(os.environ.get("RAGAS_RUN_TIMEOUT", "600")),
            max_retries=int(os.environ.get("RAGAS_MAX_RETRIES", "6")),
        )
        embeddings = LangchainEmbeddingsWrapper(NomicEmbeddings(cache_dir))
        samples = [
            SingleTurnSample(
                user_input=row["question"],
                response=row["answer"],
                retrieved_contexts=row["contexts"],
                reference=row["expected"],
            )
            for row in scorable
        ]
        try:
            result = evaluate(
                EvaluationDataset(samples=samples),
                metrics=[faithfulness, context_precision, answer_relevancy],
                llm=judge,
                embeddings=embeddings,
                run_config=run_config,
            )
            frame = result.to_pandas()
            for name in METRIC_NAMES:
                if name in frame:
                    metrics_mean[name] = _jsonable(frame[name].mean())
            for index, row in enumerate(scorable):
                if index < len(frame):
                    entry = frame.iloc[index]
                    per_row[row["id"]] = {name: _jsonable(entry.get(name)) for name in METRIC_NAMES}
        except Exception as exc:  # noqa: BLE001
            judge_error = str(exc)

    known_bad_rows = [row for row in rows if row.get("known_bad")]
    known_bad_clean = all(row.get("abstained") for row in known_bad_rows) if known_bad_rows else True
    known_bad_failures = [row["id"] for row in known_bad_rows if not row.get("abstained")]

    split_rows = []
    for row in rows:
        if row.get("known_bad"):
            continue
        score = per_row.get(row["id"], {})
        abstained = bool(row.get("abstained"))
        if row.get("abstain"):
            passed = abstained
        else:
            cite_ok = (not row.get("must_cite")) or bool(row.get("citations"))
            faithful = score.get("faithfulness")
            passed = (not abstained) and cite_ok and (
                faithful is not None and faithful >= args.threshold
            )
        split_rows.append(
            {
                "id": row["id"],
                "faithfulness": score.get("faithfulness"),
                "context_precision": score.get("context_precision"),
                "answer_relevancy": score.get("answer_relevancy"),
                "abstained": abstained,
                "passed": passed,
            }
        )

    faithfulness = metrics_mean.get("faithfulness")
    if judge_error:
        gate_reason = f"ragas judge failed: {judge_error}"
        exit_code = 1
    elif not known_bad_clean:
        gate_reason = "known-bad phase unclean"
        exit_code = 1
    elif faithfulness is None:
        gate_reason = "no scorable rows"
        exit_code = 1
    elif faithfulness < args.threshold:
        gate_reason = f"faithfulness {faithfulness:.4f} < threshold {args.threshold}"
        exit_code = 1
    else:
        gate_reason = "ok"
        exit_code = 0

    finished = datetime.now(timezone.utc)
    artifact = {
        "run_id": f"live-{finished.strftime('%Y%m%dT%H%M%SZ')}",
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "split": "evals/splits/ci.jsonl",
        "known_bad_split": "evals/splits/known_bad.jsonl",
        "mode": "live",
        "framework": "ragas",
        "method": METHOD,
        "ragas_version": getattr(ragas, "__version__", ""),
        "judge_model": args.chat_model,
        "measured_at": finished.isoformat(),
        "threshold_faithfulness": args.threshold,
        "gate_passed": exit_code == 0,
        "gate_reason": gate_reason,
        "judge_error": judge_error,
        "n_scored": len(scorable),
        "metrics": {
            "faithfulness": metrics_mean.get("faithfulness"),
            "context_precision": metrics_mean.get("context_precision"),
            "answer_relevancy": metrics_mean.get("answer_relevancy"),
        },
        "known_bad": {"clean": known_bad_clean, "failing_run_ids": known_bad_failures},
        "split_rows": split_rows,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(
        f"live ragas exit={exit_code} judge={args.chat_model} "
        f"faithfulness={faithfulness} context_precision={metrics_mean.get('context_precision')} "
        f"answer_relevancy={metrics_mean.get('answer_relevancy')} n={len(scorable)} "
        f"known_bad_clean={known_bad_clean} reason={gate_reason}"
    )
    print(f"wrote {out}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
