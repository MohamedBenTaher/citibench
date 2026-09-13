import type { ReactNode } from "react";
import { Link, createFileRoute } from "@tanstack/react-router";
import { ArrowRightIcon } from "lucide-react";
import { CitebenchMark } from "@/components/citebench-mark";
import { CornerBrackets } from "@/components/corner-brackets";
import { ErrorAlert } from "@/components/error-alert";
import { PageHeader } from "@/components/page-header";
import { RouteError, RoutePending } from "@/components/status";
import { StatusPill, type StatusTone } from "@/components/status-pill";
import { buttonVariants } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getCorpusStats, getEvalLatest, getTraces } from "@/lib/server";
import type { CorpusStats, EvalLatest, TraceList, TraceRow } from "@/lib/types";
import { cn } from "@/lib/utils";

const EMPTY_STATS: CorpusStats = {
  doc_count: 0,
  page_count: 0,
  chunk_count: 0,
  last_index_time: null,
  freeze_date: null,
  failures: [],
};

const EMPTY_TRACES: TraceList = {
  langfuse_configured: false,
  backend: "local",
  count: 0,
  traces: [],
};

const CIRCUIT = [
  { n: "01", to: "/corpus" as const, title: "Corpus", body: "Index the freeze" },
  { n: "02", to: "/playground" as const, title: "Ask", body: "Retrieve → generate | abstain" },
  { n: "03", to: "/traces" as const, title: "Traces", body: "Inspect the circuit log" },
  { n: "04", to: "/evals" as const, title: "Evals", body: "Score faithfulness" },
] as const;

function formatWhen(iso: string | null | undefined): string {
  if (!iso) {
    return "—";
  }
  return iso.slice(0, 16).replace("T", " ");
}

function outcomeTone(row: TraceRow): { tone: StatusTone; label: string } {
  if (row.failed) {
    return { tone: "danger", label: "failed" };
  }
  if (row.abstained) {
    return { tone: "warning", label: "abstain" };
  }
  return { tone: "success", label: "grounded" };
}

function runSeverity(row: TraceRow): number {
  if (row.failed) {
    return 0;
  }
  if (row.abstained) {
    return 1;
  }
  return 2;
}

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Citebench · Research gym" },
      {
        name: "description",
        content:
          "A citation-grounded retrieval bench: frozen corpus, hybrid retrieve, abstain by policy, public evals.",
      },
    ],
  }),
  loader: async () => {
    try {
      const [stats, latest, traces] = await Promise.all([
        getCorpusStats(),
        getEvalLatest(),
        getTraces(),
      ]);
      return { stats, latest, traces, loadError: null as string | null };
    } catch (error: unknown) {
      return {
        stats: EMPTY_STATS,
        latest: null as EvalLatest | null,
        traces: EMPTY_TRACES,
        loadError:
          error instanceof Error ? error.message : "failed to load bench status",
      };
    }
  },
  pendingComponent: () => <RoutePending label="Loading the bench board…" />,
  errorComponent: RouteError,
  component: IndexPage,
});

function IndexPage() {
  const { stats, latest, traces, loadError } = Route.useLoaderData();
  const hasEval = Boolean(latest?.present && latest.metrics);
  const threshold = latest?.threshold_faithfulness ?? 0.7;
  const faithfulness = hasEval ? latest?.metrics?.faithfulness ?? null : null;
  const recent = [...traces.traces]
    .sort((a, b) => runSeverity(a) - runSeverity(b) || b.started_at.localeCompare(a.started_at))
    .slice(0, 6);

  return (
    <>
      <section className="relative border border-border bg-card px-5 py-6 sm:px-8 sm:py-8">
        <CornerBrackets />
        <div className="flex flex-col gap-5">
          <div className="flex items-center gap-3">
            <CitebenchMark className="size-9" />
            <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-muted-foreground">
              Research gym · citation bench
            </p>
          </div>
          <div className="max-w-3xl space-y-3">
            <h1 className="font-heading text-balance text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
              A bench for grounded retrieve.
            </h1>
            <p className="max-w-2xl text-pretty text-[15px] leading-relaxed text-muted-foreground">
              Frozen corpus, hybrid retrieve, then generate or abstain by policy.
              No chat thread. The score that matters is whether the answer stayed on
              retrieved chunks.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
            <Link
              to="/playground"
              preload="intent"
              className={cn(buttonVariants({ size: "lg" }), "min-h-11 px-5")}
            >
              Run a single Ask
            </Link>
            <Link
              to="/evals"
              preload="intent"
              className="group inline-flex min-h-11 items-center gap-1.5 text-sm font-medium text-foreground underline-offset-4 hover:underline focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
            >
              View latest Evals
              <ArrowRightIcon
                className="size-3.5 transition-transform duration-150 ease-standard group-hover:translate-x-0.5 motion-reduce:transition-none"
                aria-hidden="true"
              />
            </Link>
          </div>
        </div>
      </section>

      {loadError ? <ErrorAlert title="Bench board" message={loadError} /> : null}

      <section className="space-y-3" aria-labelledby="status-heading">
        <SectionHeading id="status-heading">Circuit status</SectionHeading>
        <dl className="grid gap-px overflow-hidden border border-border bg-border sm:grid-cols-2 lg:grid-cols-4">
          <StatusCell
            term="Freeze"
            value={`${stats.doc_count} docs`}
            hint={
              stats.freeze_date
                ? `freeze ${stats.freeze_date} · ${stats.chunk_count.toLocaleString()} chunks`
                : `${stats.chunk_count.toLocaleString()} chunks`
            }
          />
          <StatusCell term="Last ingest" value={formatWhen(stats.last_index_time)} mono />
          <StatusCell term="CI gate" value={hasEval ? (latest?.gate_passed ? "passed" : "failed") : "unmeasured"} tone={hasEval ? (latest?.gate_passed ? "success" : "danger") : "neutral"}>
            <span className="font-mono text-[11px] text-muted-foreground">
              threshold {threshold.toFixed(1)}
            </span>
          </StatusCell>
          <StatusCell
            term="Faithfulness"
            value={faithfulness != null ? faithfulness.toFixed(3) : "unmeasured"}
            tone={faithfulness == null ? "neutral" : faithfulness >= threshold ? "success" : "danger"}
          >
            {latest?.mode ? (
              <span className="font-mono text-[11px] text-muted-foreground">{latest.mode}</span>
            ) : null}
          </StatusCell>
        </dl>
      </section>

      <section className="space-y-3" aria-labelledby="circuit-heading">
        <SectionHeading id="circuit-heading">Circuit</SectionHeading>
        <ol className="grid gap-px overflow-hidden border border-border bg-border sm:grid-cols-2 lg:grid-cols-4">
          {CIRCUIT.map((step) => (
            <li key={step.to} className="bg-background">
              <Link
                to={step.to}
                preload="intent"
                className="group flex h-full flex-col gap-1 px-4 py-3.5 transition-colors duration-150 ease-standard hover:bg-card focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-inset focus-visible:ring-ring/50 motion-reduce:transition-none"
              >
                <span className="flex items-center gap-2 font-mono text-[11px] tabular-nums text-muted-foreground">
                  <span className="h-3.5 w-1 border-y-2 border-l-2 border-foreground/60" aria-hidden="true" />
                  {step.n}
                </span>
                <span className="font-heading text-sm font-medium tracking-tight">
                  {step.title}
                </span>
                <span className="text-xs text-muted-foreground">{step.body}</span>
              </Link>
            </li>
          ))}
        </ol>
      </section>

      <section className="space-y-3" aria-labelledby="runs-heading">
        <div className="flex items-baseline justify-between gap-3">
          <SectionHeading id="runs-heading">Recent runs</SectionHeading>
          <span className="text-xs text-muted-foreground">
            failures and abstains surface first
          </span>
        </div>
        {recent.length === 0 ? (
          <div className="border border-border bg-card px-4 py-6 text-sm text-muted-foreground">
            No runs yet. <Link to="/playground" className="underline underline-offset-4 hover:text-foreground">Ask one question</Link> to write the first trace.
          </div>
        ) : (
          <div className="overflow-hidden border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Query</TableHead>
                  <TableHead className="w-28">Outcome</TableHead>
                  <TableHead className="hidden text-right sm:table-cell">Latency</TableHead>
                  <TableHead className="hidden text-right md:table-cell">When</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {recent.map((row) => {
                  const outcome = outcomeTone(row);
                  return (
                    <TableRow key={row.run_id}>
                      <TableCell>
                        <Link
                          to="/traces"
                          search={{ run_id: row.run_id }}
                          preload="intent"
                          className="line-clamp-1 text-sm text-foreground underline-offset-4 hover:underline"
                        >
                          {row.query.trim() || "(empty query)"}
                        </Link>
                      </TableCell>
                      <TableCell>
                        <StatusPill tone={outcome.tone}>{outcome.label}</StatusPill>
                      </TableCell>
                      <TableCell className="hidden text-right font-mono text-xs tabular-nums text-muted-foreground sm:table-cell">
                        {row.latency_ms.toFixed(0)} ms
                      </TableCell>
                      <TableCell className="hidden text-right font-mono text-xs tabular-nums text-muted-foreground md:table-cell">
                        {formatWhen(row.started_at)}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </section>
    </>
  );
}

function SectionHeading({ id, children }: { id: string; children: ReactNode }) {
  return (
    <h2 id={id} className="font-heading text-sm font-medium tracking-tight text-foreground">
      {children}
    </h2>
  );
}

function StatusCell({
  term,
  value,
  hint,
  tone,
  mono,
  children,
}: {
  term: string;
  value: string;
  hint?: string;
  tone?: StatusTone;
  mono?: boolean;
  children?: ReactNode;
}) {
  return (
    <div className="bg-background px-4 py-3">
      <dt className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
        <span className="h-2.5 w-0.5 bg-foreground/50" aria-hidden="true" />
        {term}
      </dt>
      <dd className="mt-1.5 flex flex-wrap items-center gap-2">
        {tone ? (
          <StatusPill tone={tone} withIcon={false} className="font-mono">
            {value}
          </StatusPill>
        ) : (
          <span className={cn("text-sm text-foreground", mono && "font-mono tabular-nums")}>
            {value}
          </span>
        )}
        {children}
      </dd>
      {hint ? (
        <p className="mt-1 font-mono text-[11px] text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  );
}
