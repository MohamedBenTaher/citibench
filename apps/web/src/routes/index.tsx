import type { ReactNode } from "react";
import { Link, createFileRoute } from "@tanstack/react-router";
import { CitebenchMark } from "@/components/citebench-mark";
import { CornerBrackets } from "@/components/corner-brackets";
import { ErrorAlert } from "@/components/error-alert";
import { RouteError, RoutePending } from "@/components/status";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
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

const stations = [
  {
    n: "01",
    to: "/corpus" as const,
    station: "Floor",
    title: "Corpus",
    body: "The freeze: 14 Kubernetes and Azure docs. Counts, last index, failures.",
  },
  {
    n: "02",
    to: "/playground" as const,
    station: "Set",
    title: "Playground",
    body: "One ask. Citations or abstain. Not a chat thread.",
  },
  {
    n: "03",
    to: "/traces" as const,
    station: "Log",
    title: "Traces",
    body: "Every set writes a RunTrace. Open a run id from Playground.",
  },
  {
    n: "04",
    to: "/evals" as const,
    station: "Weigh-in",
    title: "Evals",
    body: "Public RAGAS gate and redteam. Screenshot destination for reviewers.",
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

function gateLabel(hasEval: boolean, passed: boolean | undefined): string {
  if (!hasEval) {
    return "unmeasured";
  }
  return passed ? "passed" : "failed";
}

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Citebench · Research gym" },
      {
        name: "description",
        content:
          "A research gym for citation-grounded retrieve: freeze, one ask, trace, then a public weigh-in.",
      },
    ],
  }),
  loader: async () => {
    try {
      const [stats, latest] = await Promise.all([
        getCorpusStats(),
        getEvalLatest(),
      ]);
      return { stats, latest, loadError: null as string | null };
    } catch (error: unknown) {
      return {
        stats: EMPTY_STATS,
        latest: null as EvalLatest | null,
        loadError:
          error instanceof Error
            ? error.message
            : "failed to load bench status",
      };
    }
  },
  pendingComponent: () => <RoutePending label="Loading gym board…" />,
  errorComponent: RouteError,
  component: IndexPage,
});

function IndexPage() {
  const { stats, latest, loadError } = Route.useLoaderData();
  const hasEval = Boolean(latest?.present && latest.metrics);
  const faithfulness = formatFaithfulness(latest);
  const threshold = latest?.threshold_faithfulness ?? 0.7;
  const metricsUrl = `${publicApiBase()}/metrics`;
  const gate = gateLabel(hasEval, latest?.gate_passed);

  return (
    <>
      <section className="relative border border-border px-5 py-8 sm:px-8 sm:py-10">
        <CornerBrackets />
        <div className="flex flex-col gap-6">
          <div className="flex items-center gap-3">
            <CitebenchMark className="size-10" title="Citebench mark" />
            <p className="text-[11px] font-medium uppercase tracking-[0.2em] text-muted-foreground">
              Research gym
            </p>
          </div>
          <div className="max-w-3xl space-y-4">
            <h1 className="font-heading text-balance text-4xl font-medium tracking-tighter text-foreground sm:text-5xl">
              Where we test research.
            </h1>
            <p className="max-w-2xl text-pretty text-base leading-relaxed text-muted-foreground">
              Citebench is a gym for grounded retrieve: a frozen corpus, one
              ask, then citations or abstain. We do not keep a chat thread. The
              score that matters is whether the answer stayed on retrieved
              chunks.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Link
              to="/evals"
              preload="intent"
              className={cn(buttonVariants({ size: "lg" }), "min-h-11 px-4")}
            >
              Open the weigh-in
            </Link>
            <Link
              to="/playground"
              preload="intent"
              className={cn(
                buttonVariants({ variant: "outline", size: "lg" }),
                "min-h-11 px-4",
              )}
            >
              Run a set
            </Link>
            <Link
              to="/about"
              preload="intent"
              className={cn(
                buttonVariants({ variant: "link" }),
                "h-9 px-2 text-muted-foreground",
              )}
            >
              What this is not
            </Link>
          </div>
        </div>
      </section>

      {loadError ? (
        <ErrorAlert title="Gym board" message={loadError} />
      ) : null}

      <section className="space-y-3" aria-labelledby="board-heading">
        <h2
          id="board-heading"
          className="font-heading text-sm font-medium tracking-tight"
        >
          Today&apos;s board
        </h2>
        <p className="text-sm text-muted-foreground">
          Live counts from this instance. Empty or failed loads stay{" "}
          <span className="font-mono">unmeasured</span> — we do not invent
          scores.
        </p>
        <dl className="grid gap-px overflow-hidden border border-border bg-border sm:grid-cols-2 lg:grid-cols-4">
          <BoardCell
            term="Floor"
            value={`${stats.doc_count} docs · ${stats.chunk_count} chunks`}
          />
          <BoardCell term="Faithfulness" value={faithfulness} mono>
            {hasEval && latest?.mode ? (
              <Badge variant="outline">{latest.mode}</Badge>
            ) : null}
          </BoardCell>
          <BoardCell term="CI gate" value={gate} mono>
            <span className="text-muted-foreground">
              threshold {threshold.toFixed(1)}
            </span>
          </BoardCell>
          <BoardCell term="p95 / cost" value="—" muted>
            <span className="text-muted-foreground">unmeasured here</span>
          </BoardCell>
        </dl>
        {hasEval && latest?.gate_reason ? (
          <p className="text-sm text-muted-foreground">{latest.gate_reason}</p>
        ) : null}
      </section>

      <section className="space-y-3" aria-labelledby="circuit-heading">
        <h2
          id="circuit-heading"
          className="font-heading text-sm font-medium tracking-tight"
        >
          Circuit
        </h2>
        <p className="text-sm text-muted-foreground">
          Four stations. Walk them in order, or jump to the weigh-in.
        </p>
        <ul className="grid gap-3 sm:grid-cols-2">
          {stations.map((station) => (
            <li key={station.to}>
              <Link
                to={station.to}
                preload="intent"
                className={cn(
                  "flex min-h-28 flex-col gap-2 border border-border bg-card p-4",
                  "transition-colors duration-200 ease-out",
                  "hover:border-foreground",
                  "focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none",
                  "motion-reduce:transition-none",
                )}
              >
                <div className="flex items-baseline justify-between gap-3">
                  <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
                    {station.n} {station.station}
                  </span>
                  <span className="font-heading text-sm font-medium tracking-tight">
                    {station.title}
                  </span>
                </div>
                <p className="text-pretty text-sm leading-relaxed text-muted-foreground">
                  {station.body}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <details className="text-sm text-muted-foreground">
        <summary className="cursor-pointer font-medium text-foreground">
          Metrics scrape
        </summary>
        <p className="mt-2">
          JSON only — not a dashboard.{" "}
          <a
            href={metricsUrl}
            target="_blank"
            rel="noopener noreferrer"
            className={cn(buttonVariants({ variant: "link" }), "h-auto px-0")}
          >
            Open GET /metrics
          </a>{" "}
          at <code>{metricsUrl}</code>
        </p>
      </details>
    </>
  );
}

function BoardCell({
  term,
  value,
  mono,
  muted,
  children,
}: {
  term: string;
  value: string;
  mono?: boolean;
  muted?: boolean;
  children?: ReactNode;
}) {
  return (
    <div className="bg-background px-4 py-3">
      <dt className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        {term}
      </dt>
      <dd className="mt-1 flex flex-wrap items-center gap-2">
        <span
          className={cn(
            "text-sm text-foreground",
            mono && "font-mono tabular-nums",
            muted && "text-muted-foreground",
          )}
        >
          {value}
        </span>
        {children}
      </dd>
    </div>
  );
}
