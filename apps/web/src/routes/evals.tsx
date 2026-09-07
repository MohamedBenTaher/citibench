import { createFileRoute, useRouter } from "@tanstack/react-router";
import { RefreshCwIcon } from "lucide-react";
import { ErrorAlert } from "@/components/error-alert";
import { MetricStrip } from "@/components/metric-strip";
import { PageHeader } from "@/components/page-header";
import { RouteError } from "@/components/status";
import { TraceLink } from "@/components/trace-link";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatUtc } from "@/lib/format";
import { getEvalLatest, getRedteamLatest } from "@/lib/server";
import type { RedteamCase } from "@/lib/types";

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

function redteamResult(row: RedteamCase): "blocked" | "failed" | "allowed" | "not run" {
  if (row.passed === true) {
    return row.blocked ? "blocked" : "allowed";
  }
  if (row.passed === false) {
    return "failed";
  }
  return "not run";
}

function knownBadResult(row: {
  required_assert_failed: boolean;
  abstained?: boolean;
}): "abstained" | "failed" {
  return row.required_assert_failed ? "abstained" : "failed";
}

export const Route = createFileRoute("/evals")({
  loader: async () => {
    const [latest, redteam] = await Promise.all([getEvalLatest(), getRedteamLatest()]);
    return { latest, redteam };
  },
  pendingComponent: EvalsPending,
  errorComponent: RouteError,
  component: EvalsPage,
});

function EvalsPending() {
  return (
    <div className="space-y-6" aria-live="polite">
      <p className="text-sm text-muted-foreground">Loading last eval run…</p>
      <div className="grid gap-3 sm:grid-cols-3">
        <Skeleton className="h-28" />
        <Skeleton className="h-28" />
        <Skeleton className="h-28" />
      </div>
      <Skeleton className="h-36" />
      <Skeleton className="h-64" />
    </div>
  );
}

function EvalsPage() {
  const router = useRouter();
  const { latest, redteam } = Route.useLoaderData();
  const hasRun = Boolean(latest?.present && latest.metrics);
  const threshold = latest?.threshold_faithfulness ?? 0.7;
  const redteamCases = redteam?.cases ?? [];
  const redteamRun = redteam?.run;
  const knownBadRows = latest?.known_bad?.rows ?? [];
  const failingRunIds = latest?.failing_run_ids ?? [];
  const redteamFailures = redteamCases.filter((row) => row.passed === false);
  const knownBadLeaks = knownBadRows.filter((row) => !row.required_assert_failed);
  const hasFailures =
    latest?.gate_passed === false ||
    latest?.known_bad?.clean === false ||
    failingRunIds.length > 0 ||
    redteamFailures.length > 0;

  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <PageHeader
          title="Evals"
          description="Measurable RAG, not a chat. CI fails when faithfulness drops below 0.7. Every hop is a receipt."
        />
        <Button
          type="button"
          onClick={() => {
            void router.invalidate();
          }}
        >
          <RefreshCwIcon data-icon="inline-start" />
          Refresh last scores
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={latest?.mode === "live" ? "default" : "secondary"}>
          {latest?.mode || "no run"}
        </Badge>
        {hasRun ? (
          <Badge variant={latest?.gate_passed ? "secondary" : "destructive"}>
            {latest?.gate_passed ? "gate passed" : "gate failed"}
          </Badge>
        ) : null}
        {latest?.framework ? <Badge variant="outline">{latest.framework}</Badge> : null}
        <span className="text-sm text-muted-foreground">
          Last run {formatUtc(latest?.finished_at)}
        </span>
      </div>

      {latest?.gate_passed === false ? (
        <Alert variant="destructive">
          <AlertTitle>Faithfulness gate failed</AlertTitle>
          <AlertDescription>
            {latest.gate_reason || "Mean faithfulness is below the 0.7 CI threshold."}
          </AlertDescription>
        </Alert>
      ) : null}

      {!hasRun ? (
        <Alert>
          <AlertTitle>No CI run artifact yet</AlertTitle>
          <AlertDescription>
            Run the local eval harness, then refresh last scores. Threshold 0.7 gates
            faithfulness only.
          </AlertDescription>
        </Alert>
      ) : null}

      <MetricStrip
        metrics={latest?.metrics ?? null}
        diff={latest?.diff ?? null}
        previous={latest?.previous ?? null}
        threshold={threshold}
      />

      <Card>
        <CardHeader>
          <CardTitle>Receipts</CardTitle>
          <CardDescription>
            Known-bad abstentions and any CI or redteam failures. Open a trace to
            inspect the hop.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {hasFailures ? (
            <Alert variant="destructive">
              <AlertTitle>Failing cases</AlertTitle>
              <AlertDescription>
                {failingRunIds.length > 0
                  ? `${failingRunIds.length} RAGAS failing trace${failingRunIds.length === 1 ? "" : "s"}. `
                  : null}
                {knownBadLeaks.length > 0
                  ? `${knownBadLeaks.length} known-bad leak${knownBadLeaks.length === 1 ? "" : "s"}. `
                  : null}
                {redteamFailures.length > 0
                  ? `${redteamFailures.length} redteam failure${redteamFailures.length === 1 ? "" : "s"}.`
                  : null}
              </AlertDescription>
            </Alert>
          ) : hasRun ? (
            <p className="text-sm text-muted-foreground">
              Known-bad phase is {latest?.known_bad?.clean ? "clean" : "unclean"}. These
              abstentions are the anti-theater receipts.
            </p>
          ) : (
            <p className="text-sm text-muted-foreground">
              Receipts appear after the known-bad phase writes run ids.
            </p>
          )}

          {knownBadRows.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>id</TableHead>
                  <TableHead>result</TableHead>
                  <TableHead>trace</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {knownBadRows.map((row) => {
                  const result = knownBadResult(row);
                  return (
                    <TableRow
                      key={row.id}
                      data-state={result === "failed" ? "selected" : undefined}
                    >
                      <TableCell>
                        <code>{row.id}</code>
                      </TableCell>
                      <TableCell>
                        <Badge variant={result === "failed" ? "destructive" : "secondary"}>
                          {result}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {row.run_id ? <TraceLink runId={row.run_id} /> : "—"}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          ) : null}

          {failingRunIds.length > 0 ? (
            <p className="text-sm">
              Failing RAGAS traces:{" "}
              {failingRunIds.map((runId, index) => (
                <span key={runId}>
                  {index > 0 ? ", " : null}
                  <TraceLink runId={runId}>{runId.slice(0, 8)}</TraceLink>
                </span>
              ))}
            </p>
          ) : null}

          {redteamFailures.length > 0 ? (
            <p className="text-sm">
              Redteam leaks:{" "}
              {redteamFailures.map((row, index) => (
                <span key={row.id}>
                  {index > 0 ? ", " : null}
                  {row.run_id ? (
                    <TraceLink runId={row.run_id}>{row.id}</TraceLink>
                  ) : (
                    <code>{row.id}</code>
                  )}
                </span>
              ))}
            </p>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Redteam</CardTitle>
          <CardDescription>
            Ten cases. A pass is a block: abstain, no cite, no leak.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {redteamRun ? (
            <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <Badge variant={redteamRun.mode === "live" ? "default" : "secondary"}>
                {redteamRun.mode || "mock"}
              </Badge>
              <Badge variant={redteamRun.gate_passed ? "secondary" : "destructive"}>
                {redteamRun.gate_passed ? "gate passed" : "gate failed"}
              </Badge>
              <span>
                blocked {redteamRun.blocked ?? "—"}/{redteam?.case_count ?? redteamCases.length}
              </span>
              <span>Last run {formatUtc(redteamRun.finished_at)}</span>
            </div>
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
                  <TableHead>attack_type</TableHead>
                  <TableHead>result</TableHead>
                  <TableHead>trace</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {redteamCases.map((row) => {
                  const result = redteamResult(row);
                  return (
                    <TableRow
                      key={row.id}
                      data-state={result === "failed" ? "selected" : undefined}
                    >
                      <TableCell>
                        <code>{row.id}</code>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">{attackLabel(row.attack_type)}</Badge>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={
                            result === "failed"
                              ? "destructive"
                              : result === "blocked"
                                ? "secondary"
                                : "outline"
                          }
                        >
                          {result}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {row.run_id ? <TraceLink runId={row.run_id} /> : "—"}
                      </TableCell>
                    </TableRow>
                  );
                })}
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
