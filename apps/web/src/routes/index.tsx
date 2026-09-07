import { Link, createFileRoute } from "@tanstack/react-router";
import { ErrorAlert } from "@/components/error-alert";
import { PageHeader } from "@/components/page-header";
import { RouteError, RoutePending } from "@/components/status";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { publicApiBase } from "@/lib/client-api";
import { getCorpusStats, getEvalLatest } from "@/lib/server";
import type { CorpusStats, EvalLatest } from "@/lib/types";
import { cn } from "@/lib/utils";

const EMPTY_STATS: CorpusStats = {
  doc_count: 0,
  page_count: 0,
  chunk_count: 0,
  last_index_time: null,
  failures: [],
};

const surfaces = [
  {
    to: "/corpus" as const,
    title: "Corpus",
    body: "Frozen 14-doc index counts (docs, pages, chunks, last index, failures).",
  },
  {
    to: "/playground" as const,
    title: "Playground",
    body: "Single-ask generate; not a chat surface.",
  },
  {
    to: "/traces" as const,
    title: "Traces",
    body: "RunTrace list (Langfuse + local fallback).",
  },
  {
    to: "/evals" as const,
    title: "Evals",
    body: "Public RAGAS last-run plus 10 redteam cases. Start demo screenshots here, not on Playground.",
  },
  {
    to: "/about" as const,
    title: "About",
    body: "What Citebench is (and is not): frozen corpus, local nomic embed, Groq chat, public evals.",
  },
] as const;

function formatFaithfulness(latest: EvalLatest | null): string {
  if (!latest?.present || !latest.metrics) {
    return "unmeasured";
  }
  const value = latest.metrics.faithfulness;
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "unmeasured";
  }
  return value.toFixed(3);
}

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [{ title: "Citebench" }],
  }),
  loader: async () => {
    try {
      const [stats, latest] = await Promise.all([getCorpusStats(), getEvalLatest()]);
      return { stats, latest, loadError: null as string | null };
    } catch (error: unknown) {
      return {
        stats: EMPTY_STATS,
        latest: null as EvalLatest | null,
        loadError: error instanceof Error ? error.message : "failed to load bench status",
      };
    }
  },
  pendingComponent: () => <RoutePending label="Loading bench status…" />,
  errorComponent: RouteError,
  component: IndexPage,
});

function IndexPage() {
  const { stats, latest, loadError } = Route.useLoaderData();
  const hasEval = Boolean(latest?.present && latest.metrics);
  const faithfulness = formatFaithfulness(latest);
  const threshold = latest?.threshold_faithfulness ?? 0.7;
  const metricsUrl = `${publicApiBase()}/metrics`;

  return (
    <>
      <PageHeader
        title="Citebench"
        description="Citation-grounded retrieve over a frozen 14-doc Kubernetes + Azure corpus. Abstain when the freeze cannot support the question."
      />

      {loadError ? <ErrorAlert title="Bench status" message={loadError} /> : null}

      <Card>
        <CardContent className="flex flex-wrap items-center gap-x-6 gap-y-3 py-4 text-sm">
          <div>
            <span className="text-muted-foreground">Corpus</span>
            <span className="ml-2 font-mono tabular-nums">
              {stats.doc_count} docs · {stats.chunk_count} chunks
            </span>
          </div>
          <div>
            <span className="text-muted-foreground">Faithfulness</span>
            <span className="ml-2 font-mono tabular-nums">{faithfulness}</span>
            {hasEval && latest?.mode ? (
              <Badge variant="outline" className="ml-2">{latest.mode}</Badge>
            ) : null}
          </div>
          <div>
            <span className="text-muted-foreground">CI gate</span>
            <span className="ml-2">
              {hasEval
                ? latest?.gate_passed
                  ? "passed"
                  : "failed"
                : "unmeasured"}
              {" · "}
              threshold {threshold.toFixed(1)}
            </span>
            {hasEval && latest?.gate_reason ? (
              <span className="ml-2 text-muted-foreground">({latest.gate_reason})</span>
            ) : null}
          </div>
          <div>
            <span className="text-muted-foreground">p95 / cost</span>
            <span className="ml-2 text-muted-foreground">— unmeasured here</span>
          </div>
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center gap-2">
        <Link to="/evals" preload="intent" className={buttonVariants()}>
          Evals
        </Link>
        <Link to="/playground" preload="intent" className={buttonVariants()}>
          Playground
        </Link>
        <Link to="/corpus" preload="intent" className={buttonVariants({ variant: "outline" })}>
          Corpus
        </Link>
        <Link to="/traces" preload="intent" className={buttonVariants({ variant: "outline" })}>
          Traces
        </Link>
        <Link to="/about" preload="intent" className={buttonVariants({ variant: "outline" })}>
          About
        </Link>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Metrics</CardTitle>
          <CardDescription>
            Scrape <code>GET /metrics</code> on the API for p50/p95 latency, cost per 1k tokens,
            and last-eval faithfulness. This is not a dashboard.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <p>
            <a
              href={metricsUrl}
              target="_blank"
              rel="noopener noreferrer"
              className={cn(buttonVariants({ variant: "link" }), "h-auto px-0")}
            >
              Open metrics JSON
            </a>
            {" "}
            at <code>{metricsUrl}</code>
          </p>
        </CardContent>
      </Card>

      <section className="space-y-2">
        <h2 className="font-heading text-sm font-medium tracking-tight">Surfaces</h2>
        <ul className="space-y-2 text-sm text-muted-foreground">
          {surfaces.map((surface) => (
            <li key={surface.to}>
              <Link
                to={surface.to}
                preload="intent"
                className={cn(buttonVariants({ variant: "link" }), "h-auto px-0 font-medium")}
              >
                {surface.title}
              </Link>
              {" — "}
              {surface.body}
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}
