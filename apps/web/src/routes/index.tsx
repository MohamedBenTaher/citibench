import { ArrowRight01Icon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import { createFileRoute, Link } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { CitebenchMark } from "@/components/citebench-mark";
import { CornerBrackets } from "@/components/corner-brackets";
import { ErrorAlert } from "@/components/error-alert";
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
        loadError: error instanceof Error ? error.message : "failed to load bench status",
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
  const faithfulness = hasEval ? (latest?.metrics?.faithfulness ?? null) : null;
  const gateLabel = hasEval ? (latest?.gate_passed ? "passed" : "failed") : "unmeasured";
  const gateTone: StatusTone = hasEval ? (latest?.gate_passed ? "success" : "danger") : "neutral";
  const faithTone: StatusTone =
    faithfulness == null ? "neutral" : faithfulness >= threshold ? "success" : "danger";
  const recent = [...traces.traces]
    .sort((a, b) => runSeverity(a) - runSeverity(b) || b.started_at.localeCompare(a.started_at))
    .slice(0, 6);

  return (
    <>
      <section className="grid min-w-0 border border-border lg:grid-cols-12">
        <div className="relative min-w-0 bg-card px-5 py-7 sm:px-8 sm:py-9 lg:col-span-7">
          <CornerBrackets />
          <div className="flex flex-col gap-5">
            <div className="flex items-center gap-3">
              <CitebenchMark className="size-9" />
              <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-muted-foreground">
                Research gym · citation bench
              </p>
            </div>
            <div className="max-w-xl space-y-3">
              <h1 className="font-heading text-balance text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
                A bench for <span className="text-success">grounded</span> retrieve.
              </h1>
              <p className="max-w-prose text-pretty text-[15px] leading-relaxed text-muted-foreground">
                Frozen corpus, hybrid retrieve, then generate or abstain by policy. The score that
                matters is whether the answer stayed on retrieved chunks.
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
                <HugeiconsIcon
                  icon={ArrowRight01Icon}
                  size={14}
                  className="transition-transform duration-150 ease-standard group-hover:translate-x-0.5 motion-reduce:transition-none"
                  aria-hidden="true"
                />
              </Link>
            </div>
          </div>
        </div>

        <dl
          className="flex min-w-0 flex-col divide-y divide-border border-t border-border bg-background lg:col-span-5 lg:border-l lg:border-t-0"
          aria-label="Circuit status"
        >
          <StatusCell
            term="Freeze"
            value={String(stats.doc_count)}
            unit="docs"
            hint={
              stats.freeze_date
                ? `freeze ${stats.freeze_date} · ${stats.chunk_count.toLocaleString()} chunks`
                : `${stats.chunk_count.toLocaleString()} chunks`
            }
          />
          <StatusCell term="Last ingest" value={formatWhen(stats.last_index_time)} mono compact />
          <StatusCell term="Gate" value={gateLabel} tone={gateTone}>
            <span className="font-mono text-[11px] text-muted-foreground">
              threshold {threshold.toFixed(1)}
            </span>
          </StatusCell>
          <StatusCell
            term="Faithfulness"
            value={faithfulness != null ? faithfulness.toFixed(3) : "unmeasured"}
            tone={faithTone}
          >
            {latest?.mode ? (
              <span className="font-mono text-[11px] text-muted-foreground">{latest.mode}</span>
            ) : null}
          </StatusCell>
        </dl>
      </section>

      {loadError ? <ErrorAlert title="Bench board" message={loadError} /> : null}

      <section aria-labelledby="circuit-heading">
        <SectionHeading id="circuit-heading">Circuit</SectionHeading>
        <ol className="mt-4 border-y border-border">
          {CIRCUIT.map((step) => (
            <li key={step.to} className="border-b border-border last:border-b-0">
              <Link
                to={step.to}
                preload="intent"
                className="group grid min-w-0 grid-cols-[2.75rem_minmax(0,1fr)] items-baseline gap-x-4 py-3.5 transition-colors duration-150 ease-standard hover:bg-card focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-inset focus-visible:ring-ring/50 motion-reduce:transition-none sm:grid-cols-[2.75rem_minmax(0,1fr)_minmax(0,14rem)] sm:gap-x-6"
              >
                <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
                  {step.n}
                </span>
                <span className="font-heading text-lg font-medium tracking-tight text-foreground sm:text-xl">
                  {step.title}
                </span>
                <span className="col-start-2 text-xs text-muted-foreground sm:col-start-3 sm:text-right">
                  {step.body}
                </span>
              </Link>
            </li>
          ))}
        </ol>
      </section>

      <section className="space-y-3" aria-labelledby="runs-heading">
        <div className="flex items-baseline justify-between gap-3">
          <SectionHeading id="runs-heading">Recent runs</SectionHeading>
          <span className="text-xs text-muted-foreground">failures and abstains surface first</span>
        </div>
        {recent.length === 0 ? (
          <div className="border border-border bg-card px-4 py-6 text-sm text-muted-foreground">
            No runs yet.{" "}
            <Link to="/playground" className="underline underline-offset-4 hover:text-foreground">
              Ask one question
            </Link>{" "}
            to write the first trace.
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
  unit,
  tone,
  mono,
  compact,
  children,
}: {
  term: string;
  value: string;
  hint?: string;
  unit?: string;
  tone?: StatusTone;
  mono?: boolean;
  compact?: boolean;
  children?: ReactNode;
}) {
  return (
    <div className="min-w-0 px-4 py-3.5 sm:px-5">
      <dt className="text-[11px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
        {term}
      </dt>
      <dd className="mt-1.5 flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-1">
        {tone ? (
          <StatusPill tone={tone} withIcon={false} className="font-mono">
            {value}
          </StatusPill>
        ) : (
          <span
            className={cn(
              "min-w-0 truncate font-heading font-semibold tracking-tight text-foreground",
              compact ? "text-base sm:text-lg" : "text-xl tabular-nums sm:text-2xl",
              mono && "font-mono text-sm font-medium sm:text-base",
            )}
          >
            {value}
          </span>
        )}
        {unit ? <span className="text-xs text-muted-foreground">{unit}</span> : null}
        {children}
      </dd>
      {hint ? (
        <p className="mt-1 truncate font-mono text-[11px] text-muted-foreground" title={hint}>
          {hint}
        </p>
      ) : null}
    </div>
  );
}
