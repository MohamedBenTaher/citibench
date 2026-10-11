import { createFileRoute, Link, useRouter } from "@tanstack/react-router";
import { useState } from "react";
import { toast } from "sonner";
import { ErrorAlert } from "@/components/error-alert";
import { EvalMetricChart, RedteamChart } from "@/components/eval-charts";
import { PageHeader } from "@/components/page-header";
import { RetrievalPanel } from "@/components/retrieval-panel";
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
import { clientApiJson } from "@/lib/client-api";
import { formatNumber, metricLabel } from "@/lib/format";
import { getEvalLatest, getRedteamLatest, getRetrievalLatest } from "@/lib/server";
import type { MetricName, RedteamCase, RetrievalReport } from "@/lib/types";
import { cn } from "@/lib/utils";

const METRICS: { key: MetricName; label: string }[] = [
  { key: "faithfulness", label: "Faithfulness" },
  { key: "context_precision", label: "Context precision" },
  { key: "answer_relevancy", label: "Answer relevancy" },
];

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
  head: () => ({
    meta: [{ title: "Evals · Citebench" }],
  }),
  loader: async () => {
    try {
      const [latest, redteam, retrieval] = await Promise.all([
        getEvalLatest(),
        getRedteamLatest(),
        getRetrievalLatest(),
      ]);
      return { latest, redteam, retrieval, loadError: null as string | null };
    } catch (error: unknown) {
      return {
        latest: null,
        redteam: null,
        retrieval: null as RetrievalReport | null,
        loadError: error instanceof Error ? error.message : "failed to load evals",
      };
    }
  },
  pendingComponent: () => <RoutePending label="Loading last eval run…" />,
  errorComponent: RouteError,
  component: EvalsPage,
});

function EvalsPage() {
  const router = useRouter();
  const { latest, redteam, retrieval, loadError } = Route.useLoaderData();
  const metrics = latest?.metrics;
  const hasRun = Boolean(latest?.present && metrics);
  const redteamCases = redteam?.cases ?? [];
  const redteamRun = redteam?.run;
  const threshold = latest?.threshold_faithfulness ?? 0.7;
  const [runningRetrieval, setRunningRetrieval] = useState(false);

  async function runRetrieval() {
    setRunningRetrieval(true);
    try {
      await clientApiJson("/evals/retrieval/run", { method: "POST" });
      toast.success("Retrieval comparison updated");
      await router.invalidate();
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "retrieval run failed");
    } finally {
      setRunningRetrieval(false);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Weigh-in"
        title="Evals"
        description="How well answers stay grounded in retrieved chunks, plus redteam refusals. Public — no login."
      />

      {loadError ? <ErrorAlert title="Evals" message={loadError} /> : null}

      <Card>
        <CardHeader>
          <CardTitle>Retrieval quality</CardTitle>
          <CardDescription>
            Hand-labeled questions with a known source document. Recall@k, MRR, and nDCG measure
            whether retrieval finds the evidence; the matrix separates answering from abstaining.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-muted-foreground">
              Runs locally against the indexed corpus — no LLM judge.
            </p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={runningRetrieval}
              aria-busy={runningRetrieval}
              onClick={() => void runRetrieval()}
            >
              {runningRetrieval ? "Running…" : "Run comparison"}
            </Button>
          </div>
          <RetrievalPanel report={retrieval} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Answer quality</CardTitle>
          <CardDescription>
            Latest faithfulness, context precision, and answer relevancy over the frozen evaluation
            set. The {threshold.toFixed(1)} gate applies to faithfulness.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div className="space-y-1">
              <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                Faithfulness
              </p>
              <p className="font-mono text-4xl font-semibold tabular-nums">
                {hasRun ? formatNumber(metrics?.faithfulness) : "unmeasured"}
              </p>
              {hasRun && latest?.mode ? <Badge variant="outline">{latest.mode}</Badge> : null}
            </div>
            <div className="space-y-1 text-sm text-muted-foreground">
              <p>Gate: {hasRun ? (latest?.gate_passed ? "passed" : "failed") : "unmeasured"}</p>
              {hasRun && latest?.gate_reason ? <p>{latest.gate_reason}</p> : null}
              <p>The {threshold.toFixed(1)} gate applies to faithfulness.</p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                void router.invalidate();
              }}
            >
              Refresh
            </Button>
          </div>

          {!hasRun ? (
            <p className="text-sm text-muted-foreground">
              No eval run yet. Scores appear here once an evaluation has completed; nothing is
              estimated.
            </p>
          ) : (
            <>
              <EvalMetricChart latest={latest} />
              <p className="text-sm text-muted-foreground">
                Run <code>{latest?.run_id}</code>
                {latest?.mode ? ` · ${latest.mode}` : ""}
                {latest?.finished_at ? ` · ${latest.finished_at}` : ""}
                {latest?.gate_passed ? " · gate passed" : " · gate failed"}
                {latest?.gate_reason && latest.gate_reason !== "ok"
                  ? ` · ${latest.gate_reason}`
                  : ""}
              </p>
              <StatCards
                items={METRICS.map((metric) => ({
                  label: metricLabel(metric.key),
                  value: formatNumber(metrics?.[metric.key]),
                  hint: `vs previous: ${formatDiff(latest?.diff?.[metric.key])}${
                    latest?.previous
                      ? ` (${formatNumber(latest.previous[metric.key])})`
                      : " (no previous run)"
                  }`,
                }))}
              />
              <p className="text-sm text-muted-foreground">
                Out-of-corpus refusal checks:{" "}
                <code>{latest?.known_bad?.clean ? "clean" : "unclean"}</code>
                {latest?.failing_run_ids && latest.failing_run_ids.length > 0
                  ? ` · failing cases: ${latest.failing_run_ids.join(", ")}`
                  : ""}
                .
              </p>
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Redteam</CardTitle>
          <CardDescription>
            Ten attack cases across prompt injection, PII leaks, and jailbreaks. A pass is a refusal
            — no answer, no citation, no leak.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
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
              {redteam?.detail ? "" : " · not run yet"}.
            </p>
          )}
          <RedteamChart cases={redteamCases} />
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
                  <TableRow key={row.id} data-state={row.passed === false ? "selected" : undefined}>
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
    </>
  );
}
