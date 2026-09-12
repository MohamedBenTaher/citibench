import { Link, createFileRoute, useRouter } from "@tanstack/react-router";
import { ErrorAlert } from "@/components/error-alert";
import { PageHeader } from "@/components/page-header";
import { StatCards } from "@/components/stat-cards";
import { RouteError, RoutePending } from "@/components/status";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { getMetrics } from "@/lib/server";
import type { MetricsSnapshot } from "@/lib/types";

function measured(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "unmeasured";
  }
  return value.toFixed(digits);
}

function formatAsOf(iso: string | undefined): string {
  if (!iso) {
    return "—";
  }
  return iso.replace("T", " ").slice(0, 19);
}

export const Route = createFileRoute("/metrics")({
  head: () => ({
    meta: [{ title: "Metrics · Citebench" }],
  }),
  loader: async () => {
    try {
      return { snapshot: await getMetrics(), loadError: null as string | null };
    } catch (error: unknown) {
      return {
        snapshot: null as MetricsSnapshot | null,
        loadError: error instanceof Error ? error.message : "failed to load metrics",
      };
    }
  },
  pendingComponent: () => <RoutePending label="Loading scoreboard…" />,
  errorComponent: RouteError,
  component: MetricsPage,
});

function MetricsPage() {
  const router = useRouter();
  const { snapshot, loadError } = Route.useLoaderData();
  const latency = snapshot?.latency_ms;
  const cost = snapshot?.cost_per_1k_queries_usd;
  const faith = snapshot?.faithfulness;
  const corpus = snapshot?.corpus;
  const noAsks = !latency || latency.n === 0;
  const noEval = !faith?.present;

  return (
    <>
      <PageHeader
        eyebrow="Scoreboard"
        title="Metrics"
        description="The same C7 scrape the README quotes: ask latency, cost per 1k, last-eval faithfulness, freeze size. Null stays unmeasured."
      />

      {loadError ? <ErrorAlert title="Metrics" message={loadError} /> : null}

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
        <Link to="/evals" preload="intent" className={buttonVariants({ variant: "outline" })}>
          Weigh-in
        </Link>
        <Link to="/traces" preload="intent" className={buttonVariants({ variant: "outline" })}>
          Log
        </Link>
        <Link
          to="/playground"
          preload="intent"
          className={buttonVariants({ variant: "outline" })}
        >
          Run a set
        </Link>
      </div>

      {snapshot ? (
        <p className="text-xs text-muted-foreground">
          As of {formatAsOf(snapshot.as_of)}
          {faith?.mode ? ` · faithfulness ${faith.mode}` : ""}
        </p>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Ask cost</CardTitle>
          <CardDescription>
            p50/p95 over RunTrace.latency_ms where latency_ms &gt; 0. Cost is mean
            usd_estimate × 1000. Empty store is unmeasured, not $0.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {noAsks ? (
            <p className="text-sm text-muted-foreground">
              No billed asks yet. Run a set in Playground, then refresh. Do not treat
              missing p95 as zero.
            </p>
          ) : null}
          <StatCards
            items={[
              {
                label: "p50 latency",
                value:
                  latency?.p50 == null
                    ? "unmeasured"
                    : `${measured(latency.p50, 1)} ms`,
                hint: latency ? `n=${latency.n}` : undefined,
              },
              {
                label: "p95 latency",
                value:
                  latency?.p95 == null
                    ? "unmeasured"
                    : `${measured(latency.p95, 1)} ms`,
                hint: latency ? `n=${latency.n}` : undefined,
              },
              {
                label: "Cost / 1k asks",
                value: cost?.usd == null ? "unmeasured" : `$${cost.usd.toFixed(4)}`,
                hint: cost ? `n=${cost.n} · ${cost.cost_method}` : undefined,
              },
            ]}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Last weigh-in</CardTitle>
          <CardDescription>
            Faithfulness from evals/results/latest.json. The CI gate is 0.7; that is
            not a published Citebench score. Companion metrics are logged only.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {noEval ? (
            <p className="text-sm text-muted-foreground">
              No eval artifact yet. Open Evals after CI writes latest.json. Charts stay
              empty rather than inventing scores.
            </p>
          ) : null}
          <StatCards
            items={[
              {
                label: "Faithfulness",
                value: measured(faith?.value ?? null),
                hint: faith?.present
                  ? [faith.mode, faith.split, faith.run_id]
                      .filter(Boolean)
                      .join(" · ")
                  : "missing latest.json",
              },
              {
                label: "Context precision",
                value: measured(faith?.context_precision ?? null),
                hint: "logged only; does not gate CI",
              },
              {
                label: "Rows scored",
                value:
                  faith?.n_scored == null ? "unmeasured" : String(faith.n_scored),
                hint: faith?.source ?? undefined,
              },
            ]}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Floor</CardTitle>
          <CardDescription>
            Freeze size. Docs come from MANIFEST. Pages and chunks prefer live
            /corpus/stats after ingest.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <StatCards
            items={[
              {
                label: "Docs",
                value: corpus?.docs == null ? "unmeasured" : String(corpus.docs),
                hint: corpus?.source,
              },
              {
                label: "Pages",
                value: corpus?.pages == null ? "unmeasured" : String(corpus.pages),
              },
              {
                label: "Chunks",
                value: corpus?.chunks == null ? "unmeasured" : String(corpus.chunks),
                hint: corpus?.measured_under ?? undefined,
              },
            ]}
          />
        </CardContent>
      </Card>

      <details className="text-sm text-muted-foreground">
        <summary className="cursor-pointer font-medium text-foreground">
          How these are computed
        </summary>
        <ul className="mt-2 space-y-2">
          <li>Latency: {latency?.method ?? "—"}</li>
          <li>Cost: {cost?.method ?? "—"}</li>
          <li>Faithfulness: {faith?.method ?? "—"}</li>
        </ul>
        <p className="mt-2">
          Machine scrape remains <code>GET /metrics</code> and{" "}
          <code>GET /metrics?format=prometheus</code>. This page does not add a second
          formula.
        </p>
      </details>
    </>
  );
}
