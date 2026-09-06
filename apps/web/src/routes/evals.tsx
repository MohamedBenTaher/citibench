import { Link, createFileRoute, useRouter } from "@tanstack/react-router";
import { ErrorAlert } from "@/components/error-alert";
import { PageHeader } from "@/components/page-header";
import { StatCards } from "@/components/stat-cards";
import { RouteError, RoutePending } from "@/components/status";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { getEvalLatest, getRedteamLatest } from "@/lib/server";
import type { MetricName, RedteamCase } from "@/lib/types";

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
    const [latest, redteam] = await Promise.all([getEvalLatest(), getRedteamLatest()]);
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
      <PageHeader
        title="Evals"
        description="Public scores and traces. There is no login wall on this tab. Demo screenshots should start here (or on a failing RunTrace), not on a Playground chat bubble."
      />

      <Card>
        <CardHeader>
          <CardTitle>Redteam</CardTitle>
          <CardDescription>
            Ten Contract A cases in <code>evals/redteam.jsonl</code> (<code>tags</code>{" "}
            include <code>redteam</code>, plus <code>attack_type</code> and{" "}
            <code>expect_block</code>). Mix is injection / pii_leak / jailbreak. The
            runner reuses generate → abstain.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">
            Command:{" "}
            <code>python -m citebench.eval.redteam --split evals/redteam.jsonl --mock</code>
          </p>
          {redteamRun ? (
            <p className="text-sm text-muted-foreground">
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
            <p className="text-sm text-muted-foreground">
              {redteamCases.length} cases loaded
              {redteam?.detail ? ` · ${redteam.detail}` : " · no runner artifact yet"}.
            </p>
          )}
          {redteamCases.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>id</TableHead>
                  <TableHead>attack</TableHead>
                  <TableHead>expect_block</TableHead>
                  <TableHead>result</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {redteamCases.map((row) => (
                  <TableRow
                    key={row.id}
                    data-state={row.passed === false ? "selected" : undefined}
                  >
                    <TableCell>
                      <code>{row.id}</code>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{attackLabel(row.attack_type)}</Badge>
                    </TableCell>
                    <TableCell>{row.expect_block ? "true" : "false"}</TableCell>
                    <TableCell className="whitespace-normal">
                      <Badge variant={row.passed === false ? "destructive" : "secondary"}>
                        {resultLabel(row)}
                      </Badge>
                      {row.run_id ? (
                        <>
                          {" "}
                          <Link
                            to="/traces"
                            search={{ run_id: row.run_id }}
                            preload="intent"
                            className={cn(buttonVariants({ variant: "link" }), "h-auto px-0")}
                          >
                            trace
                          </Link>
                        </>
                      ) : null}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <ErrorAlert
              title="Redteam"
              message="No redteam cases loaded. Check evals/redteam.jsonl."
            />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>RAGAS CI</CardTitle>
          <CardDescription>
            Last CI run of the RAGAS gate. Faithfulness 0.7 is the CI threshold, not a
            published Citebench score. Companion metrics are logged only. See{" "}
            <code>evals/splits/ci.jsonl</code>, <code>evals/splits/known_bad.jsonl</code>,
            and <code>docs/contracts/eval-jsonl.md</code>.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Command:{" "}
            <code>
              python -m citebench.eval.ci --split evals/splits/ci.jsonl --known-bad
              evals/splits/known_bad.jsonl --threshold-faithfulness 0.7
            </code>
          </p>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              void router.invalidate();
            }}
          >
            Refresh
          </Button>

          {!hasRun ? (
            <p className="text-sm text-muted-foreground">
              No CI run artifact yet. Run the eval harness, then refresh.
            </p>
          ) : (
            <>
              <p className="text-sm text-muted-foreground">
                Run <code>{latest?.run_id}</code>
                {latest?.mode ? ` · ${latest.mode}` : ""}
                {latest?.framework ? ` · ${latest.framework}` : ""}
                {latest?.finished_at ? ` · ${latest.finished_at}` : ""}
                {latest?.gate_passed ? " · gate passed" : " · gate failed"}
                {latest?.gate_reason ? ` · ${latest.gate_reason}` : ""}
              </p>
              <StatCards
                items={METRICS.map((metric) => ({
                  label: metricLabel(metric.key),
                  value: formatScore(metrics?.[metric.key]),
                  hint: `vs previous: ${formatDiff(latest?.diff?.[metric.key])}${
                    latest?.previous
                      ? ` (${formatScore(latest.previous[metric.key])})`
                      : " (no previous run)"
                  }`,
                }))}
              />
              <p className="text-sm text-muted-foreground">
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
        </CardContent>
      </Card>
    </>
  );
}
