"use client";

import { useCallback, useEffect, useState } from "react";

type MetricName = "faithfulness" | "context_precision" | "answer_relevancy";

type Metrics = {
  faithfulness: number;
  context_precision: number;
  answer_relevancy: number;
};

type EvalLatest = {
  present?: boolean;
  run_id?: string;
  started_at?: string;
  finished_at?: string;
  mode?: string;
  framework?: string;
  threshold_faithfulness?: number;
  gate_passed?: boolean;
  gate_reason?: string | null;
  metrics: Metrics | null;
  previous: Metrics | null;
  diff: Metrics | null;
  known_bad?: { clean: boolean; rows: { id: string; required_assert_failed: boolean }[] };
  failing_run_ids?: string[];
  detail?: string;
};

const METRICS: { key: MetricName; label: string }[] = [
  { key: "faithfulness", label: "Faithfulness" },
  { key: "context_precision", label: "Context precision" },
  { key: "answer_relevancy", label: "Answer relevancy" },
];

function metricLabel(key: MetricName): string {
  switch (key) {
    case "faithfulness":
      return "Faithfulness";
    case "context_precision":
      return "Context precision";
    case "answer_relevancy":
      return "Answer relevancy";
    default: {
      const _exhaustive: never = key;
      return _exhaustive;
    }
  }
}

function formatScore(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return value.toFixed(3);
}

function formatDiff(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "n/a";
  }
  const abs = Math.abs(value).toFixed(3);
  if (value > 0) {
    return `+${abs}`;
  }
  if (value < 0) {
    return `-${abs}`;
  }
  return "0.000";
}

export default function EvalsPage() {
  const [latest, setLatest] = useState<EvalLatest | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const response = await fetch("/api/evals/latest", { cache: "no-store" });
    const data = (await response.json()) as EvalLatest;
    if (!response.ok) {
      throw new Error(data.detail || `evals HTTP ${response.status}`);
    }
    setLatest(data);
    setLoadError(null);
  }, []);

  useEffect(() => {
    refresh().catch((error: unknown) => {
      setLoadError(error instanceof Error ? error.message : "failed to load last eval run");
    });
  }, [refresh]);

  const metrics = latest?.metrics;
  const hasRun = Boolean(latest?.present && metrics);

  return (
    <>
      <h1>Evals</h1>
      <p>
        Last CI run of the RAGAS gate. Faithfulness 0.7 is the CI threshold, not a
        published Citebench score. Companion metrics are logged only. See{" "}
        <code>evals/splits/ci.jsonl</code>, <code>evals/splits/known_bad.jsonl</code>,
        and <code>docs/contracts/eval-jsonl.md</code>.
      </p>
      <p className="muted">
        Command:{" "}
        <code>
          python -m citebench.eval.ci --split evals/splits/ci.jsonl --known-bad
          evals/splits/known_bad.jsonl --threshold-faithfulness 0.7
        </code>
      </p>

      <p className="actions">
        <button
          type="button"
          onClick={() =>
            refresh().catch((error: unknown) => {
              setLoadError(error instanceof Error ? error.message : "failed to load last eval run");
            })
          }
        >
          Refresh
        </button>
      </p>
      {loadError ? <p className="error">{loadError}</p> : null}

      {!hasRun ? (
        <p>No CI run artifact yet. Run the eval harness, then refresh.</p>
      ) : (
        <>
          <p className="muted">
            Run <code>{latest?.run_id}</code>
            {latest?.mode ? ` · ${latest.mode}` : ""}
            {latest?.framework ? ` · ${latest.framework}` : ""}
            {latest?.finished_at ? ` · ${latest.finished_at}` : ""}
            {latest?.gate_passed ? " · gate passed" : " · gate failed"}
            {latest?.gate_reason ? ` · ${latest.gate_reason}` : ""}
          </p>
          <dl className="stats">
            {METRICS.map((metric) => (
              <div key={metric.key}>
                <dt>{metricLabel(metric.key)}</dt>
                <dd>{formatScore(metrics?.[metric.key])}</dd>
                <p className="muted">
                  vs previous: {formatDiff(latest?.diff?.[metric.key])}
                  {latest?.previous
                    ? ` (${formatScore(latest.previous[metric.key])})`
                    : " (no previous run)"}
                </p>
              </div>
            ))}
          </dl>
          <p className="muted">
            Known-bad phase:{" "}
            <code>{latest?.known_bad?.clean ? "clean" : "unclean"}</code>
            {latest?.failing_run_ids && latest.failing_run_ids.length > 0
              ? ` · failing traces: ${latest.failing_run_ids.join(", ")}`
              : ""}
            . Threshold {formatScore(latest?.threshold_faithfulness ?? 0.7)} gates
            faithfulness only.
          </p>
        </>
      )}
    </>
  );
}
