import { useMemo, useState, type FormEvent } from "react";
import { createFileRoute, useNavigate, useRouter } from "@tanstack/react-router";
import { ErrorAlert } from "@/components/error-alert";
import { PageHeader } from "@/components/page-header";
import { StatCards } from "@/components/stat-cards";
import { RouteError, RoutePending } from "@/components/status";
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

type TracesSearch = {
  run_id?: string;
};

function tracesSearch(search: Record<string, unknown>): TracesSearch {
  return {
    run_id:
      typeof search.run_id === "string" && search.run_id ? search.run_id : undefined,
  };
}

export const Route = createFileRoute("/traces")({
  validateSearch: tracesSearch,
  loaderDeps: ({ search }) => ({ run_id: search.run_id }),
  loader: async ({ deps }) => {
    const list = await getTraces();
    if (!deps.run_id) {
      return { list, detail: null, detailError: null as string | null };
    }
    try {
      const detail = await getTrace({ data: deps.run_id });
      return { list, detail, detailError: null as string | null };
    } catch (error: unknown) {
      return {
        list,
        detail: null,
        detailError: error instanceof Error ? error.message : "failed to load trace",
      };
    }
  },
  pendingComponent: () => <RoutePending label="Loading traces…" />,
  errorComponent: RouteError,
  component: TracesPage,
});

function backendLabel(configured: boolean, langfuseId: string | null): string {
  if (langfuseId) {
    return "langfuse";
  }
  return configured ? "local (Langfuse down)" : "local";
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

function TracesPage() {
  const router = useRouter();
  const navigate = useNavigate({ from: "/traces" });
  const { run_id: selectedId } = Route.useSearch();
  const { list, detail, detailError } = Route.useLoaderData();
  const [runInput, setRunInput] = useState(selectedId ?? "");

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
        title="Traces"
        description="One RunTrace per generate/ask run. Langfuse is the named backend (citebench.run + nested retrieve → rerank → generate|abstain). This tab is the local fallback view and stays available if Langfuse is down or unconfigured."
      />
      <BackendNote list={list} />

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
          No runs yet. Ask a question on Playground, then refresh.
        </p>
      ) : (
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
                {list.traces.map((row) => (
                  <TableRow
                    key={row.run_id}
                    data-state={selectedId === row.run_id ? "selected" : undefined}
                    className="cursor-pointer"
                    onClick={() => selectRun(row.run_id)}
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
                      <Badge variant={row.failed ? "destructive" : "secondary"}>
                        {row.failed ? "failed" : row.abstained ? "abstain" : "generate"}
                      </Badge>
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
      )}

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
                  ? ` · Langfuse ${detail.langfuse_trace_id}`
                  : " · local fallback (no langfuse_trace_id)"}
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
                      {span.parent_id
                        ? `child of ${span.parent_id.slice(0, 12)}`
                        : "root"}{" "}
                      · {span.started_at} → {span.finished_at}
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {span.kind === "retrieve" || span.kind === "rerank" ? (
                      <ChunkTable refs={chunkRefsFromAttributes(span.attributes)} />
                    ) : null}
                    {span.kind === "generate" || span.kind === "abstain" ? (
                      <pre className="overflow-auto rounded-lg bg-muted/50 p-3 text-xs">
                        {JSON.stringify(span.attributes, null, 2)}
                      </pre>
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
      Backend:{" "}
      <code>
        {list
          ? backendLabel(
              list.langfuse_configured,
              list.traces.some((row) => row.langfuse_trace_id) ? "set" : null,
            )
          : "—"}
      </code>
      {list?.langfuse_configured
        ? " · LANGFUSE_PUBLIC_KEY/SECRET_KEY are set"
        : " · no Langfuse keys; local store only"}
      . Chunks are <code>text_ref</code> pointers, not corpus dumps.
    </p>
  );
}

function ChunkTable({
  refs,
  empty = "None.",
}: {
  refs: Citation[];
  empty?: string;
}) {
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
