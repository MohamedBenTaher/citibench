"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type CostEstimate = {
  prompt_tokens: number;
  completion_tokens: number;
  embed_tokens: number;
  rerank_tokens: number;
  usd_estimate: number;
};

type TraceRow = {
  run_id: string;
  query: string;
  started_at: string;
  finished_at: string;
  abstained: boolean;
  model: string;
  tokens_in: number;
  tokens_out: number;
  latency_ms: number;
  cost: CostEstimate;
  cost_method: string;
  langfuse_trace_id: string | null;
  rerank_skipped: boolean;
  citation_count: number;
  failed: boolean;
};

type TraceList = {
  langfuse_configured: boolean;
  backend: "langfuse" | "local";
  count: number;
  traces: TraceRow[];
  detail?: string;
};

type ChunkRef = {
  chunk_id: string;
  doc_id: string;
  text_ref: string;
  score: number | null;
  rank: number | null;
};

type SpanKind = "retrieve" | "rerank" | "generate" | "abstain";
type SpanStatus = "ok" | "error";

type Span = {
  span_id: string;
  parent_id: string | null;
  kind: SpanKind;
  started_at: string;
  finished_at: string;
  status: SpanStatus;
  attributes: Record<string, unknown>;
};

type RunTrace = {
  run_id: string;
  query: string;
  started_at: string;
  finished_at: string;
  spans: Span[];
  citations: ChunkRef[];
  abstained: boolean;
  cost: CostEstimate;
  langfuse_trace_id: string | null;
  rerank_skipped: boolean;
  model: string;
  tokens_in: number;
  tokens_out: number;
  latency_ms: number;
  cost_method: string;
  detail?: string;
};

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

function chunkRefsFromAttributes(attributes: Record<string, unknown>): ChunkRef[] {
  const raw = attributes.chunks;
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.flatMap((item) => {
    if (!item || typeof item !== "object") {
      return [];
    }
    const row = item as Record<string, unknown>;
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

export default function TracesPage() {
  const [list, setList] = useState<TraceList | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<RunTrace | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const response = await fetch("/api/traces", { cache: "no-store" });
    const data = (await response.json()) as TraceList;
    if (!response.ok) {
      throw new Error(data.detail || `traces HTTP ${response.status}`);
    }
    setList(data);
    setLoadError(null);
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const fromQuery = params.get("run_id");
    if (fromQuery) {
      setSelectedId(fromQuery);
    }
    refresh().catch((error: unknown) => {
      setLoadError(error instanceof Error ? error.message : "failed to load traces");
    });
  }, [refresh]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setDetailError(null);
    fetch(`/api/traces/${encodeURIComponent(selectedId)}`, { cache: "no-store" })
      .then(async (response) => {
        const data = (await response.json()) as RunTrace;
        if (!response.ok) {
          throw new Error(data.detail || `trace HTTP ${response.status}`);
        }
        if (!cancelled) {
          setDetail(data);
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setDetail(null);
          setDetailError(error instanceof Error ? error.message : "failed to load trace");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  const orderedSpans = useMemo(() => {
    if (!detail) {
      return [];
    }
    const order: SpanKind[] = ["retrieve", "rerank", "generate", "abstain"];
    return [...detail.spans].sort(
      (a, b) => order.indexOf(a.kind) - order.indexOf(b.kind),
    );
  }, [detail]);

  return (
    <>
      <h1>Traces</h1>
      <p>
        One <code>RunTrace</code> per generate/ask run. Langfuse is the named
        backend (<code>citebench.run</code> + nested retrieve → rerank →
        generate|abstain). This tab is the local fallback view and stays
        available if Langfuse is down or unconfigured.
      </p>
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

      <p className="actions">
        <button type="button" onClick={() => refresh().catch((error: unknown) => {
          setLoadError(error instanceof Error ? error.message : "failed to load traces");
        })}>
          Refresh
        </button>
      </p>
      {loadError ? <p className="error">{loadError}</p> : null}

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
                onClick={() => setSelectedId(row.run_id)}
              >
                <td>
                  <button type="button" className="linkish" onClick={() => setSelectedId(row.run_id)}>
                    {row.query.trim() || "(empty query)"}
                  </button>
                  <div className="muted">
                    <code>{row.run_id.slice(0, 8)}</code>
                    {row.langfuse_trace_id ? ` · lf ${row.langfuse_trace_id.slice(0, 8)}` : ""}
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
                    {span.parent_id ? `child of ${span.parent_id.slice(0, 12)}` : "root"} ·{" "}
                    {span.started_at} → {span.finished_at}
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

function ChunkTable({
  refs,
  empty = "None.",
}: {
  refs: ChunkRef[];
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
