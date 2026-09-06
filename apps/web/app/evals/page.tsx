"use client";

import { useCallback, useEffect, useState } from "react";

type MetricName = "faithfulness" | "context_precision" | "answer_relevancy";
type AttackType = "injection" | "pii_leak" | "jailbreak";

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

type RedteamCase = {
  id: string;
  question: string;
  expected: string;
  attack_type: AttackType | string | null;
  expect_block: boolean | null;
  tags: string[];
  run_id?: string;
  blocked?: boolean;
  passed?: boolean;
  abstained?: boolean;
};

type RedteamLatest = {
  present?: boolean;
  split?: string;
  case_count?: number;
  cases: RedteamCase[];
  run?: {
    run_id?: string;
    mode?: string;
    gate_passed?: boolean;
    gate_reason?: string | null;
    passed?: number;
    failed?: number;
    blocked?: number;
    finished_at?: string;
    failing_run_ids?: string[];
  } | null;
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

function attackLabel(value: string | null): string {
  switch (value) {
    case "injection":
      return "injection";
    case "pii_leak":
      return "pii_leak";
    case "jailbreak":
      return "jailbreak";
    case null:
      return "—";
    default:
      return value;
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

function resultLabel(row: RedteamCase): string {
  if (row.passed === true) {
    return row.blocked ? "blocked" : "allowed (ok)";
  }
  if (row.passed === false) {
    return "leaked";
  }
  return "not run";
}

export default function EvalsPage() {
  const [latest, setLatest] = useState<EvalLatest | null>(null);
  const [redteam, setRedteam] = useState<RedteamLatest | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [evalResponse, redteamResponse] = await Promise.all([
      fetch("/api/evals/latest", { cache: "no-store" }),
      fetch("/api/evals/redteam", { cache: "no-store" }),
    ]);
    const evalData = (await evalResponse.json()) as EvalLatest;
    const redteamData = (await redteamResponse.json()) as RedteamLatest;
    if (!evalResponse.ok) {
      throw new Error(evalData.detail || `evals HTTP ${evalResponse.status}`);
    }
    if (!redteamResponse.ok) {
      throw new Error(redteamData.detail || `redteam HTTP ${redteamResponse.status}`);
    }
    setLatest(evalData);
    setRedteam(redteamData);
    setLoadError(null);
  }, []);

  useEffect(() => {
    refresh().catch((error: unknown) => {
      setLoadError(error instanceof Error ? error.message : "failed to load last eval run");
    });
  }, [refresh]);

  const metrics = latest?.metrics;
  const hasRun = Boolean(latest?.present && metrics);
  const redteamCases = redteam?.cases ?? [];
  const redteamRun = redteam?.run;

  return (
    <>
      <h1>Evals</h1>
      <p>
        Public scores and traces. There is no login wall on this tab. Demo
        screenshots should start here (or on a failing RunTrace), not on a
        Playground chat bubble.
      </p>

      <h2>Redteam</h2>
      <p>
        Ten Contract A cases in <code>evals/redteam.jsonl</code> (
        <code>tags</code> include <code>redteam</code>, plus{" "}
        <code>attack_type</code> and <code>expect_block</code>). Mix is
        injection / pii_leak / jailbreak. The runner reuses generate → abstain.
      </p>
      <p className="muted">
        Command:{" "}
        <code>python -m citebench.eval.redteam --split evals/redteam.jsonl --mock</code>
      </p>
      {redteamRun ? (
        <p className="muted">
          Run <code>{redteamRun.run_id}</code>
          {redteamRun.mode ? ` · ${redteamRun.mode}` : ""}
          {redteamRun.finished_at ? ` · ${redteamRun.finished_at}` : ""}
          {redteamRun.gate_passed ? " · gate passed" : " · gate failed"}
          {redteamRun.gate_reason ? ` · ${redteamRun.gate_reason}` : ""}
          {typeof redteamRun.blocked === "number"
            ? ` · blocked ${redteamRun.blocked}/${redteam?.case_count ?? redteamCases.length}`
            : ""}
        </p>
      ) : (
        <p className="muted">
          {redteamCases.length} cases loaded
          {redteam?.detail ? ` · ${redteam.detail}` : " · no runner artifact yet"}.
        </p>
      )}
      {redteamCases.length > 0 ? (
        <table>
          <thead>
            <tr>
              <th>id</th>
              <th>attack</th>
              <th>expect_block</th>
              <th>result</th>
            </tr>
          </thead>
          <tbody>
            {redteamCases.map((row) => (
              <tr key={row.id} className={row.passed === false ? "selected" : undefined}>
                <td>
                  <code>{row.id}</code>
                </td>
                <td>{attackLabel(row.attack_type)}</td>
                <td>{row.expect_block ? "true" : "false"}</td>
                <td>
                  {resultLabel(row)}
                  {row.run_id ? (
                    <>
                      {" "}
                      <a href={`/traces?run_id=${encodeURIComponent(row.run_id)}`}>trace</a>
                    </>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p>No redteam cases loaded. Check <code>evals/redteam.jsonl</code>.</p>
      )}

      <h2>RAGAS CI</h2>
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
