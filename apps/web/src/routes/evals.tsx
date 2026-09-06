import { Link, createFileRoute, useRouter } from "@tanstack/react-router";
import { RouteError, RoutePending } from "../components/status";
import { getEvalLatest, getRedteamLatest } from "../lib/server";
import type { MetricName, RedteamCase } from "../lib/types";

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

export const Route = createFileRoute("/evals")({
  loader: async () => {
    const [latest, redteam] = await Promise.all([
      getEvalLatest(),
      getRedteamLatest(),
    ]);
    return { latest, redteam };
  },
  pendingComponent: () => <RoutePending label="Loading last eval run…" />,
  errorComponent: RouteError,
  component: EvalsPage,
});

function EvalsPage() {
  const router = useRouter();
  const { latest, redteam } = Route.useLoaderData();
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
                      <Link
                        to="/traces"
                        search={{ run_id: row.run_id }}
                        preload="intent"
                      >
                        trace
                      </Link>
                    </>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p>
          No redteam cases loaded. Check <code>evals/redteam.jsonl</code>.
        </p>
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
          onClick={() => {
            void router.invalidate();
          }}
        >
          Refresh
        </button>
      </p>

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

