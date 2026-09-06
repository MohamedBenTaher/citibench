import { useMemo } from "react";
import { createFileRoute, useNavigate, useRouter } from "@tanstack/react-router";
import { RouteError, RoutePending } from "../components/status";
import { getTrace, getTraces } from "../lib/server";
import type { Citation, JsonValue, SpanKind, SpanStatus, TraceList } from "../lib/types";

type TracesSearch = {
  run_id?: string;
};

function tracesSearch(search: Record<string, unknown>): TracesSearch {
  return {
    run_id:
      typeof search.run_id === "string" && search.run_id
        ? search.run_id
        : undefined,
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

  const orderedSpans = useMemo(() => {
    if (!detail) {
      return [];
    }
    const order: SpanKind[] = ["retrieve", "rerank", "generate", "abstain"];
    return [...detail.spans].sort(
      (a, b) => order.indexOf(a.kind) - order.indexOf(b.kind),
    );
  }, [detail]);

  function selectRun(runId: string) {
    void navigate({ search: { run_id: runId } });
  }

  return (
    <>
      <h1>Traces</h1>
      <p>
        One <code>RunTrace</code> per generate/ask run. Langfuse is the named
        backend (<code>citebench.run</code> + nested retrieve → rerank →
        generate|abstain). This tab is the local fallback view and stays
        available if Langfuse is down or unconfigured.
      </p>
      <BackendNote list={list} />

      <p className="actions">
        <button
          type="button"
          onClick={() => {
            void router.invalidate();
          }}
        >
          Refresh
        </button>
      </p>

      {!list || list.traces.length === 0 ? (
        <p>No runs yet. Ask a question on Playground, then refresh.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Query</th>
              <th>Outcome</th>
              <th>Model</th>
              <th>Tokens</th>
              <th>Latency</th>
              <th>Cost</th>
            </tr>
          </thead>
          <tbody>
            {list.traces.map((row) => (
              <tr
                key={row.run_id}
                className={selectedId === row.run_id ? "selected" : undefined}
                onClick={() => selectRun(row.run_id)}
              >
                <td>
                  <button
                    type="button"
                    className="linkish"
                    onClick={() => selectRun(row.run_id)}
                  >
                    {row.query.trim() || "(empty query)"}
                  </button>
                  <div className="muted">
                    <code>{row.run_id.slice(0, 8)}</code>
                    {row.langfuse_trace_id
                      ? ` · lf ${row.langfuse_trace_id.slice(0, 8)}`
                      : ""}
                  </div>
                </td>
                <td>
                  {row.failed ? "failed" : row.abstained ? "abstain" : "generate"}
                  {row.rerank_skipped ? " · rerank skipped" : ""}
                </td>
                <td>
                  <code>{row.model || "—"}</code>
                </td>
                <td>
                  {row.tokens_in} / {row.tokens_out}
                </td>
                <td>{row.latency_ms.toFixed(1)} ms</td>
                <td>${row.cost.usd_estimate.toFixed(6)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {selectedId ? (
        <section className="result" aria-live="polite">
          <h2>Run {selectedId.slice(0, 8)}</h2>
          {detailError ? <p className="error">{detailError}</p> : null}
          {detail ? (
            <>
              <dl className="stats">
                <div>
                  <dt>Query</dt>
                  <dd>{detail.query.trim() || "(empty)"}</dd>
                </div>
                <div>
                  <dt>Abstained</dt>
                  <dd>{detail.abstained ? "yes" : "no"}</dd>
                </div>
                <div>
                  <dt>Model</dt>
                  <dd>{detail.model || "—"}</dd>
                </div>
                <div>
                  <dt>Tokens in / out</dt>
                  <dd>
                    {detail.tokens_in} / {detail.tokens_out}
                  </dd>
                </div>
                <div>
                  <dt>Latency</dt>
                  <dd>{detail.latency_ms.toFixed(1)} ms</dd>
                </div>
                <div>
                  <dt>Cost</dt>
                  <dd>${detail.cost.usd_estimate.toFixed(6)}</dd>
                </div>
              </dl>
              <p className="muted">
                Method <code>{detail.cost_method || "—"}</code>
                {detail.langfuse_trace_id
                  ? ` · Langfuse ${detail.langfuse_trace_id}`
                  : " · local fallback (no langfuse_trace_id)"}
                {detail.rerank_skipped ? " · rerank_skipped=true" : ""}
              </p>

              <h2>Spans</h2>
              <p className="muted">retrieve → rerank → generate | abstain</p>
              {orderedSpans.map((span) => (
                <article key={span.span_id} className="span">
                  <h3>
                    {kindLabel(span.kind)}{" "}
                    <span className={span.status === "error" ? "error" : "muted"}>
                      {statusLabel(span.status)}
                    </span>
                  </h3>
                  <p className="muted">
                    {span.parent_id
                      ? `child of ${span.parent_id.slice(0, 12)}`
                      : "root"}{" "}
                    · {span.started_at} → {span.finished_at}
                  </p>
                  {span.kind === "retrieve" || span.kind === "rerank" ? (
                    <ChunkTable refs={chunkRefsFromAttributes(span.attributes)} />
                  ) : null}
                  {span.kind === "generate" || span.kind === "abstain" ? (
                    <pre className="attrs">{JSON.stringify(span.attributes, null, 2)}</pre>
                  ) : null}
                  {typeof span.attributes.rerank_skipped === "boolean" ? (
                    <p className="muted">
                      rerank_skipped={String(span.attributes.rerank_skipped)}
                    </p>
                  ) : null}
                </article>
              ))}

              <h2>Citations</h2>
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
    <p className="muted">
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
    return <p>{empty}</p>;
  }
  return (
    <table>
      <thead>
        <tr>
          <th>chunk_id</th>
          <th>text_ref</th>
          <th>rank</th>
        </tr>
      </thead>
      <tbody>
        {refs.map((row) => (
          <tr key={`${row.chunk_id}-${row.rank ?? "x"}`}>
            <td>
              <code>{row.chunk_id}</code>
            </td>
            <td>
              <code>{row.text_ref}</code>
            </td>
            <td>{row.rank ?? "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
