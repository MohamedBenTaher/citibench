import { createFileRoute, useNavigate, useRouter } from "@tanstack/react-router";
import { type FormEvent, useEffect, useMemo, useState } from "react";
import { ErrorAlert } from "@/components/error-alert";
import { PageHeader } from "@/components/page-header";
import { StatCards } from "@/components/stat-cards";
import { RouteError, RoutePending } from "@/components/status";
import { StatusPill } from "@/components/status-pill";
import { TraceCharts } from "@/components/trace-charts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getTrace, getTraces } from "@/lib/server";
import type { Citation, JsonValue, SpanKind, SpanStatus, TraceList } from "@/lib/types";

const EMPTY_LIST: TraceList = {
  langfuse_configured: false,
  backend: "local",
  count: 0,
  traces: [],
};

type TracesSearch = {
  run_id?: string;
};

function tracesSearch(search: Record<string, unknown>): TracesSearch {
  return {
    run_id: typeof search.run_id === "string" && search.run_id ? search.run_id : undefined,
  };
}

export const Route = createFileRoute("/traces")({
  validateSearch: tracesSearch,
  loaderDeps: ({ search }) => ({ run_id: search.run_id }),
  loader: async ({ deps }) => {
    let list: TraceList = EMPTY_LIST;
    let loadError: string | null = null;
    try {
      list = await getTraces();
    } catch (error: unknown) {
      loadError = error instanceof Error ? error.message : "failed to load traces";
    }
    if (!deps.run_id) {
      return { list, detail: null, detailError: null as string | null, loadError };
    }
    try {
      const detail = await getTrace(deps.run_id);
      return { list, detail, detailError: null as string | null, loadError };
    } catch (error: unknown) {
      return {
        list,
        detail: null,
        detailError: error instanceof Error ? error.message : "failed to load trace",
        loadError,
      };
    }
  },
  pendingComponent: () => <RoutePending label="Loading traces…" />,
  errorComponent: RouteError,
  component: TracesPage,
});

function backendLabel(externalId: string | null): string {
  return externalId ? "external tracing" : "local store";
}

function kindLabel(kind: SpanKind): string {
  switch (kind) {
    case "retrieve":
      return "retrieve";
    case "rerank":
      return "rerank";
    case "generate":
      return "generate";
    case "abstain":
      return "abstain";
    default: {
      const _exhaustive: never = kind;
      return _exhaustive;
    }
  }
}

function statusLabel(status: SpanStatus): string {
  switch (status) {
    case "ok":
      return "ok";
    case "error":
      return "error";
    default: {
      const _exhaustive: never = status;
      return _exhaustive;
    }
  }
}

function chunkRefsFromAttributes(attributes: { [key: string]: JsonValue }): Citation[] {
  const raw = attributes.chunks;
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.flatMap((item) => {
    if (!item || typeof item !== "object") {
      return [];
    }
    const row = item as { [key: string]: JsonValue };
    const chunkId = String(row.chunk_id || "");
    const docId = String(row.doc_id || "");
    const textRef = String(row.text_ref || "");
    if (!chunkId || !textRef) {
      return [];
    }
    return [
      {
        chunk_id: chunkId,
        doc_id: docId,
        text_ref: textRef,
        score: typeof row.score === "number" ? row.score : null,
        rank: typeof row.rank === "number" ? row.rank : null,
      },
    ];
  });
}

function formatSpanTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso.slice(0, 19);
  }
  return date.toLocaleString();
}

function TracesPage() {
  const router = useRouter();
  const navigate = useNavigate({ from: "/traces" });
  const { run_id: selectedId } = Route.useSearch();
  const { list, detail, detailError, loadError } = Route.useLoaderData();
  const [runInput, setRunInput] = useState(selectedId ?? "");

  useEffect(() => {
    setRunInput(selectedId ?? "");
  }, [selectedId]);

  const orderedSpans = useMemo(() => {
    if (!detail) {
      return [];
    }
    const order: SpanKind[] = ["retrieve", "rerank", "generate", "abstain"];
    return [...detail.spans].sort((a, b) => order.indexOf(a.kind) - order.indexOf(b.kind));
  }, [detail]);

  function selectRun(runId: string) {
    void navigate({ search: { run_id: runId } });
  }

  return (
    <>
      <PageHeader
        eyebrow="Log"
        title="Traces"
        description="One trace per ask: retrieve → rerank → generate or abstain, with per-span detail, scores, and citations."
      />
      <BackendNote list={list} />
      {loadError ? <ErrorAlert title="Traces" message={loadError} /> : null}

      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(event: FormEvent) => {
          event.preventDefault();
          const runId = runInput.trim();
          if (runId) {
            selectRun(runId);
          }
        }}
      >
        <div className="space-y-2">
          <Label htmlFor="trace-run-id">Run id</Label>
          <Input
            id="trace-run-id"
            name="run_id"
            value={runInput}
            onChange={(event) => setRunInput(event.target.value)}
            placeholder={selectedId ?? "Open a run id"}
            autoComplete="off"
          />
        </div>
        <Button type="submit" variant="outline">
          Open
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            void router.invalidate();
          }}
        >
          Refresh
        </Button>
      </form>

      {!list || list.traces.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No runs yet. Ask a question on Playground, then refresh. Charts stay empty until a
          RunTrace exists — they do not invent latency or cost.
        </p>
      ) : (
        <TraceCharts traces={list.traces} />
      )}

      {list && list.traces.length > 0 ? (
        <Card>
          <CardContent className="pt-4">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Query</TableHead>
                  <TableHead>Outcome</TableHead>
                  <TableHead>Model</TableHead>
                  <TableHead>Tokens</TableHead>
                  <TableHead>Latency</TableHead>
                  <TableHead>Cost</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {[...list.traces]
                  .sort(
                    (a, b) =>
                      (a.failed ? 0 : a.abstained ? 1 : 2) - (b.failed ? 0 : b.abstained ? 1 : 2) ||
                      b.started_at.localeCompare(a.started_at),
                  )
                  .map((row) => (
                    <TableRow
                      key={row.run_id}
                      data-state={selectedId === row.run_id ? "selected" : undefined}
                    >
                      <TableCell className="whitespace-normal">
                        <Button
                          type="button"
                          variant="link"
                          className="h-auto px-0"
                          onClick={() => selectRun(row.run_id)}
                        >
                          {row.query.trim() || "(empty query)"}
                        </Button>
                        <div className="text-xs text-muted-foreground">
                          <code>{row.run_id.slice(0, 8)}</code>
                          {row.langfuse_trace_id
                            ? ` · lf ${row.langfuse_trace_id.slice(0, 8)}`
                            : ""}
                        </div>
                      </TableCell>
                      <TableCell>
                        <StatusPill
                          tone={row.failed ? "danger" : row.abstained ? "warning" : "success"}
                        >
                          {row.failed ? "failed" : row.abstained ? "abstain" : "generate"}
                        </StatusPill>
                        {row.rerank_skipped ? (
                          <span className="ml-1 text-xs text-muted-foreground">
                            · rerank skipped
                          </span>
                        ) : null}
                      </TableCell>
                      <TableCell>
                        <code>{row.model || "—"}</code>
                      </TableCell>
                      <TableCell>
                        {row.tokens_in} / {row.tokens_out}
                      </TableCell>
                      <TableCell>{row.latency_ms.toFixed(1)} ms</TableCell>
                      <TableCell>${row.cost.usd_estimate.toFixed(6)}</TableCell>
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      ) : null}

      {selectedId ? (
        <section className="space-y-4" aria-live="polite">
          <PageHeader title={`Run ${selectedId.slice(0, 8)}`} description="" />
          {detailError ? <ErrorAlert title="Trace" message={detailError} /> : null}
          {detail ? (
            <>
              <StatCards
                items={[
                  { label: "Query", value: detail.query.trim() || "(empty)" },
                  { label: "Abstained", value: detail.abstained ? "yes" : "no" },
                  { label: "Model", value: detail.model || "—" },
                  { label: "Tokens in / out", value: `${detail.tokens_in} / ${detail.tokens_out}` },
                  { label: "Latency", value: `${detail.latency_ms.toFixed(1)} ms` },
                  { label: "Cost", value: `$${detail.cost.usd_estimate.toFixed(6)}` },
                ]}
              />
              <p className="text-sm text-muted-foreground">
                Method <code>{detail.cost_method || "—"}</code>
                {detail.langfuse_trace_id
                  ? ` · external ${detail.langfuse_trace_id}`
                  : " · local store"}
                {detail.rerank_skipped ? " · rerank_skipped=true" : ""}
              </p>

              <h2 className="font-heading text-lg font-medium">Spans</h2>
              <p className="text-sm text-muted-foreground">
                retrieve → rerank → generate | abstain
              </p>
              {orderedSpans.map((span) => (
                <Card key={span.span_id}>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      {kindLabel(span.kind)}
                      <Badge variant={span.status === "error" ? "destructive" : "outline"}>
                        {statusLabel(span.status)}
                      </Badge>
                    </CardTitle>
                    <CardDescription>
                      {span.parent_id ? `child of ${span.parent_id.slice(0, 12)}` : "root"} ·{" "}
                      <span title={span.started_at}>{formatSpanTime(span.started_at)}</span>
                      {" → "}
                      <span title={span.finished_at}>{formatSpanTime(span.finished_at)}</span>
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {span.kind === "retrieve" || span.kind === "rerank" ? (
                      <ChunkTable refs={chunkRefsFromAttributes(span.attributes)} />
                    ) : null}
                    {span.kind === "generate" || span.kind === "abstain" ? (
                      <details className="text-sm">
                        <summary className="cursor-pointer font-medium">Span attributes</summary>
                        <pre className="mt-2 overflow-auto rounded-lg bg-muted/50 p-3 text-xs">
                          {JSON.stringify(span.attributes, null, 2)}
                        </pre>
                      </details>
                    ) : null}
                    {typeof span.attributes.rerank_skipped === "boolean" ? (
                      <p className="text-sm text-muted-foreground">
                        rerank_skipped={String(span.attributes.rerank_skipped)}
                      </p>
                    ) : null}
                  </CardContent>
                </Card>
              ))}

              <h2 className="font-heading text-lg font-medium">Citations</h2>
              <ChunkTable refs={detail.citations} empty="None (empty on abstain)." />
            </>
          ) : null}
        </section>
      ) : null}
    </>
  );
}

function BackendNote({ list }: { list: TraceList | null }) {
  return (
    <p className="text-sm text-muted-foreground">
      Storage:{" "}
      <code>
        {list ? backendLabel(list.traces.some((row) => row.langfuse_trace_id) ? "set" : null) : "—"}
      </code>
      . Every span is kept; chunks are referenced by pointer, not copied into the trace.
    </p>
  );
}

function ChunkTable({ refs, empty = "None." }: { refs: Citation[]; empty?: string }) {
  if (refs.length === 0) {
    return <p className="text-sm text-muted-foreground">{empty}</p>;
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>chunk_id</TableHead>
          <TableHead>text_ref</TableHead>
          <TableHead>rank</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {refs.map((row) => (
          <TableRow key={`${row.chunk_id}-${row.rank ?? "x"}`}>
            <TableCell>
              <code>{row.chunk_id}</code>
            </TableCell>
            <TableCell>
              <code>{row.text_ref}</code>
            </TableCell>
            <TableCell>{row.rank ?? "—"}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
