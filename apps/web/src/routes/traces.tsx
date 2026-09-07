import { useMemo, useState, type KeyboardEvent } from "react";
import { Link, createFileRoute, useNavigate, useRouter } from "@tanstack/react-router";
import { RefreshCwIcon } from "lucide-react";
import { ErrorAlert } from "@/components/error-alert";
import { PageHeader } from "@/components/page-header";
import { RouteError } from "@/components/status";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatLatency, formatUsd, formatUtc, snippet } from "@/lib/format";
import { getTrace, getTraces } from "@/lib/server";
import { cn } from "@/lib/utils";
import type { Citation, JsonValue, RunTrace, Span, SpanKind, SpanStatus, TraceRow } from "@/lib/types";

type TracesSearch = {
  run_id?: string;
};

type PathFilter = "all" | "generate" | "abstain" | "error";
type RunPath = Exclude<PathFilter, "all">;

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
  pendingComponent: TracesPending,
  errorComponent: RouteError,
  component: TracesPage,
});

function TracesPending() {
  return (
    <div className="space-y-4" aria-live="polite">
      <p className="text-sm text-muted-foreground">Loading traces…</p>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
        <Skeleton className="h-80" />
        <Skeleton className="h-80" />
      </div>
    </div>
  );
}

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

function runPath(row: Pick<TraceRow, "failed" | "abstained">): RunPath {
  if (row.failed) {
    return "error";
  }
  if (row.abstained) {
    return "abstain";
  }
  return "generate";
}

function pathLabel(path: RunPath): string {
  switch (path) {
    case "generate":
      return "generate";
    case "abstain":
      return "abstain";
    case "error":
      return "error";
    default: {
      const _exhaustive: never = path;
      return _exhaustive;
    }
  }
}

function filterLabel(filter: PathFilter): string {
  switch (filter) {
    case "all":
      return "All";
    case "generate":
      return "Generate";
    case "abstain":
      return "Abstain";
    case "error":
      return "Error";
    default: {
      const _exhaustive: never = filter;
      return _exhaustive;
    }
  }
}

function pathBadgeVariant(path: RunPath): "secondary" | "destructive" | "outline" {
  switch (path) {
    case "error":
      return "destructive";
    case "abstain":
      return "outline";
    case "generate":
      return "secondary";
    default: {
      const _exhaustive: never = path;
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

function textRefsFromAttributes(attributes: { [key: string]: JsonValue }): string[] {
  const raw = attributes.citation_text_refs;
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.flatMap((item) => (typeof item === "string" && item ? [item] : []));
}

function spanTree(spans: Span[]): { span: Span; depth: number }[] {
  const children = new Map<string | null, Span[]>();
  const ids = new Set(spans.map((span) => span.span_id));
  for (const span of spans) {
    const parentId = span.parent_id && ids.has(span.parent_id) ? span.parent_id : null;
    const list = children.get(parentId) ?? [];
    list.push(span);
    children.set(parentId, list);
  }
  const order: SpanKind[] = ["retrieve", "rerank", "generate", "abstain"];
  function walk(parentId: string | null, depth: number): { span: Span; depth: number }[] {
    const kids = [...(children.get(parentId) ?? [])].sort(
      (a, b) => order.indexOf(a.kind) - order.indexOf(b.kind),
    );
    return kids.flatMap((kid) => [{ span: kid, depth }, ...walk(kid.span_id, depth + 1)]);
  }
  return walk(null, 0);
}

function attrPreview(value: JsonValue): string {
  if (value === null) {
    return "null";
  }
  switch (typeof value) {
    case "string":
    case "number":
    case "boolean":
      return String(value);
    default:
      return JSON.stringify(value);
  }
}

function TracesPage() {
  const router = useRouter();
  const navigate = useNavigate({ from: "/traces" });
  const { run_id: selectedId } = Route.useSearch();
  const { list, detail, detailError } = Route.useLoaderData();
  const [filter, setFilter] = useState<PathFilter>("all");
  const [runInput, setRunInput] = useState(selectedId ?? "");

  const tree = useMemo(() => (detail ? spanTree(detail.spans) : []), [detail]);

  const filtered = useMemo(() => {
    const rows = list?.traces ?? [];
    if (filter === "all") {
      return rows;
    }
    return rows.filter((row) => runPath(row) === filter);
  }, [list, filter]);

  function selectRun(runId: string) {
    setRunInput(runId);
    void navigate({ search: { run_id: runId } });
  }

  function onRowKey(event: KeyboardEvent<HTMLTableRowElement>, runId: string) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      selectRun(runId);
    }
  }

  const filters: PathFilter[] = ["all", "generate", "abstain", "error"];

  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <PageHeader
          title="Traces"
          description="Inspect every hop: retrieve → rerank → generate|abstain. Citations are text_ref pointers, not corpus dumps."
        />
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            void router.invalidate();
          }}
        >
          <RefreshCwIcon data-icon="inline-start" />
          Refresh
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">
          {list
            ? backendLabel(
                list.langfuse_configured,
                list.traces.some((row) => row.langfuse_trace_id) ? "set" : null,
              )
            : "—"}
        </Badge>
        <span className="text-sm text-muted-foreground">
          {list ? `${list.count} run${list.count === 1 ? "" : "s"}` : "—"}
        </span>
      </div>

      {!list || list.traces.length === 0 ? (
        <Alert>
          <AlertTitle>No runs yet</AlertTitle>
          <AlertDescription>
            Ask a question on{" "}
            <Link
              to="/playground"
              preload="intent"
              className={cn(buttonVariants({ variant: "link" }), "h-auto px-0")}
            >
              Playground
            </Link>{" "}
            to create a RunTrace. Playground is not the homepage.
          </AlertDescription>
        </Alert>
      ) : null}

      {list && list.traces.length > 0 ? (
        <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,24rem)_minmax(0,1fr)]">
          <Card className="min-w-0">
            <CardHeader className="gap-3">
              <CardTitle>Runs</CardTitle>
              <div className="flex flex-wrap gap-1">
                {filters.map((item) => (
                  <Button
                    key={item}
                    type="button"
                    size="xs"
                    variant={filter === item ? "secondary" : "outline"}
                    aria-pressed={filter === item}
                    onClick={() => setFilter(item)}
                  >
                    {filterLabel(item)}
                  </Button>
                ))}
              </div>
            </CardHeader>
            <CardContent className="max-h-[70vh] overflow-y-auto px-0">
              {filtered.length === 0 ? (
                <p className="px-(--card-spacing) text-sm text-muted-foreground">
                  No runs match this filter.
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Query</TableHead>
                      <TableHead>Path</TableHead>
                      <TableHead>Latency</TableHead>
                      <TableHead>Cost</TableHead>
                      <TableHead>Time</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filtered.map((row) => {
                      const path = runPath(row);
                      return (
                        <TableRow
                          key={row.run_id}
                          data-state={selectedId === row.run_id ? "selected" : undefined}
                          className="cursor-pointer"
                          tabIndex={0}
                          onClick={() => selectRun(row.run_id)}
                          onKeyDown={(event) => onRowKey(event, row.run_id)}
                        >
                          <TableCell className="max-w-[12rem] whitespace-normal">
                            <div className="font-medium">{snippet(row.query, 64)}</div>
                            <div className="text-xs text-muted-foreground">
                              <code>{row.run_id.slice(0, 8)}</code>
                            </div>
                          </TableCell>
                          <TableCell>
                            <Badge variant={pathBadgeVariant(path)}>{pathLabel(path)}</Badge>
                          </TableCell>
                          <TableCell className="tabular-nums">
                            {formatLatency(row.latency_ms)}
                          </TableCell>
                          <TableCell className="tabular-nums">
                            {formatUsd(row.cost.usd_estimate)}
                          </TableCell>
                          <TableCell className="whitespace-normal text-xs text-muted-foreground">
                            {formatUtc(row.finished_at)}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>

          <TraceDetail
            selectedId={selectedId}
            runInput={runInput}
            setRunInput={setRunInput}
            onOpen={(runId) => selectRun(runId)}
            detail={detail}
            detailError={detailError}
            tree={tree}
          />
        </div>
      ) : selectedId ? (
        <TraceDetail
          selectedId={selectedId}
          runInput={runInput}
          setRunInput={setRunInput}
          onOpen={(runId) => selectRun(runId)}
          detail={detail}
          detailError={detailError}
          tree={tree}
        />
      ) : null}
    </>
  );
}

function TraceDetail({
  selectedId,
  runInput,
  setRunInput,
  onOpen,
  detail,
  detailError,
  tree,
}: {
  selectedId: string | undefined;
  runInput: string;
  setRunInput: (value: string) => void;
  onOpen: (runId: string) => void;
  detail: RunTrace | null;
  detailError: string | null;
  tree: { span: Span; depth: number }[];
}) {
  const path = detail
    ? runPath({ failed: detail.spans.some((span) => span.status === "error"), abstained: detail.abstained })
    : null;

  return (
    <div className="min-w-0 space-y-4 lg:sticky lg:top-20">
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          const runId = runInput.trim();
          if (runId) {
            onOpen(runId);
          }
        }}
      >
        <div className="min-w-[12rem] flex-1 space-y-1">
          <Label htmlFor="trace-run-id" className="text-xs text-muted-foreground">
            Deep link run id
          </Label>
          <Input
            id="trace-run-id"
            name="run_id"
            value={runInput}
            onChange={(event) => setRunInput(event.target.value)}
            placeholder={selectedId ?? "Paste a run id"}
            autoComplete="off"
          />
        </div>
        <Button type="submit" variant="outline">
          Open
        </Button>
      </form>

      {!selectedId ? (
        <Alert>
          <AlertTitle>Select a run</AlertTitle>
          <AlertDescription>
            Choose a row to inspect retrieve → rerank → generate|abstain. Evals
            receipts deep-link here with <code>?run_id=</code>.
          </AlertDescription>
        </Alert>
      ) : null}

      {detailError ? <ErrorAlert title="Trace" message={detailError} /> : null}

      {detail ? (
        <>
          <Card>
            <CardHeader>
              <CardTitle className="flex flex-wrap items-center gap-2">
                Run <code className="text-sm font-normal">{detail.run_id.slice(0, 8)}</code>
                {path ? (
                  <Badge variant={pathBadgeVariant(path)}>{pathLabel(path)}</Badge>
                ) : null}
              </CardTitle>
              <CardDescription className="whitespace-normal">
                {detail.query.trim() || "(empty query)"}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <dl className="grid grid-cols-2 gap-x-3 gap-y-2 sm:grid-cols-3">
                <div>
                  <dt className="text-xs text-muted-foreground">Latency</dt>
                  <dd className="tabular-nums">{formatLatency(detail.latency_ms)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Cost</dt>
                  <dd className="tabular-nums">{formatUsd(detail.cost.usd_estimate, 6)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Method</dt>
                  <dd>
                    <code>{detail.cost_method || "—"}</code>
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Model</dt>
                  <dd>
                    <code>{detail.model || "—"}</code>
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Tokens</dt>
                  <dd className="tabular-nums">
                    {detail.tokens_in} / {detail.tokens_out}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Finished</dt>
                  <dd>{formatUtc(detail.finished_at)}</dd>
                </div>
              </dl>
              {detail.rerank_skipped ? (
                <p className="text-xs text-muted-foreground">rerank_skipped=true</p>
              ) : null}
            </CardContent>
          </Card>

          <div className="space-y-2">
            <h2 className="font-heading text-lg font-medium">Spans</h2>
            {tree.map(({ span, depth }) => (
              <Card
                key={span.span_id}
                size="sm"
                className={cn(depth > 0 && "border-l-2", depth === 1 && "ml-4", depth >= 2 && "ml-8")}
              >
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    {depth > 0 ? (
                      <span className="text-muted-foreground" aria-hidden="true">
                        └
                      </span>
                    ) : null}
                    {kindLabel(span.kind)}
                    <Badge variant={span.status === "error" ? "destructive" : "outline"}>
                      {statusLabel(span.status)}
                    </Badge>
                  </CardTitle>
                  <CardDescription>
                    {formatUtc(span.started_at)} → {formatUtc(span.finished_at)}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  {span.kind === "retrieve" || span.kind === "rerank" ? (
                    <ChunkTable refs={chunkRefsFromAttributes(span.attributes)} />
                  ) : null}
                  {span.kind === "generate" ? (
                    <TextRefList refs={textRefsFromAttributes(span.attributes)} />
                  ) : null}
                  {span.kind === "abstain" && typeof span.attributes.reason === "string" ? (
                    <p className="text-sm">
                      reason <code>{span.attributes.reason}</code>
                    </p>
                  ) : null}
                  <AttrDetails attributes={span.attributes} />
                </CardContent>
              </Card>
            ))}
          </div>

          <div className="space-y-2">
            <h2 className="font-heading text-lg font-medium">Citations</h2>
            <ChunkTable refs={detail.citations} empty="None (empty on abstain)." />
          </div>
        </>
      ) : null}
    </div>
  );
}

function TextRefList({ refs }: { refs: string[] }) {
  if (refs.length === 0) {
    return <p className="text-sm text-muted-foreground">No citation text_refs on this span.</p>;
  }
  return (
    <ul className="flex flex-wrap gap-1">
      {refs.map((ref) => (
        <li key={ref}>
          <Badge variant="outline">
            <code>{ref}</code>
          </Badge>
        </li>
      ))}
    </ul>
  );
}

function AttrDetails({ attributes }: { attributes: { [key: string]: JsonValue } }) {
  const entries = Object.entries(attributes).filter(
    ([key]) => key !== "chunks" && key !== "citation_text_refs",
  );
  if (entries.length === 0) {
    return null;
  }
  return (
    <details className="text-sm">
      <summary className="cursor-pointer text-muted-foreground">Attributes</summary>
      <dl className="mt-2 grid gap-1">
        {entries.map(([key, value]) => (
          <div key={key} className="grid grid-cols-[8rem_minmax(0,1fr)] gap-2">
            <dt className="text-muted-foreground">
              <code>{key}</code>
            </dt>
            <dd className="min-w-0 break-all">
              <code>{attrPreview(value)}</code>
            </dd>
          </div>
        ))}
      </dl>
    </details>
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
          <TableHead>text_ref</TableHead>
          <TableHead>rank</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {refs.map((row) => (
          <TableRow key={`${row.chunk_id}-${row.rank ?? "x"}`}>
            <TableCell className="whitespace-normal">
              <code>{row.text_ref}</code>
            </TableCell>
            <TableCell>{row.rank ?? "—"}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
