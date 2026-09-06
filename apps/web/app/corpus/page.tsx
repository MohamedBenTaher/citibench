"use client";

import { useCallback, useEffect, useState } from "react";

type FailureRow = {
  id: string;
  title: string;
  source_url: string;
  error: string;
};

type CorpusStats = {
  doc_count: number;
  page_count: number;
  chunk_count: number;
  last_index_time: string | null;
  failures: FailureRow[];
  detail?: string;
};

const EMPTY: CorpusStats = {
  doc_count: 0,
  page_count: 0,
  chunk_count: 0,
  last_index_time: null,
  failures: [],
};

export default function CorpusPage() {
  const [stats, setStats] = useState<CorpusStats>(EMPTY);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const response = await fetch("/api/corpus/stats", { cache: "no-store" });
    const data = (await response.json()) as CorpusStats;
    if (!response.ok) {
      throw new Error(data.detail || `stats HTTP ${response.status}`);
    }
    setStats(data);
    setLoadError(null);
  }, []);

  useEffect(() => {
    refresh().catch((error: unknown) => {
      setLoadError(error instanceof Error ? error.message : "failed to load stats");
    });
  }, [refresh]);

  async function runIngest(body: Record<string, unknown>) {
    setBusy(true);
    setActionError(null);
    try {
      const response = await fetch("/api/ingest", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = (await response.json()) as CorpusStats;
      if (!response.ok) {
        throw new Error(data.detail || `ingest HTTP ${response.status}`);
      }
      setStats(data);
    } catch (error: unknown) {
      setActionError(error instanceof Error ? error.message : "ingest failed");
      await refresh().catch(() => undefined);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1>Corpus</h1>
      <p>
        Frozen Kubernetes and Azure set from <code>corpus/MANIFEST.md</code>{" "}
        (2026-09-05, 14 URLs). Ingest snapshots only those rows.
      </p>

      <dl className="stats">
        <div>
          <dt>Documents</dt>
          <dd>{stats.doc_count}</dd>
        </div>
        <div>
          <dt>Pages</dt>
          <dd>{stats.page_count}</dd>
        </div>
        <div>
          <dt>Chunks</dt>
          <dd>{stats.chunk_count}</dd>
        </div>
        <div>
          <dt>Last index</dt>
          <dd>{stats.last_index_time ?? "—"}</dd>
        </div>
      </dl>

      <p className="actions">
        <button type="button" disabled={busy} onClick={() => runIngest({})}>
          {busy ? "Indexing…" : "Ingest / Re-index"}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => runIngest({ simulate_failure_id: "k8s-pods" })}
        >
          Re-index with one failure
        </button>
      </p>
      <p className="hint">
        Re-index is idempotent (replace per MANIFEST id).{" "}
        <code>POST /ingest</code> with <code>{`{"wipe": true}`}</code> wipes
        documents and chunks first.
      </p>

      {loadError ? <p className="error">{loadError}</p> : null}
      {actionError ? <p className="error">{actionError}</p> : null}

      <h2>Failures</h2>
      {stats.failures.length === 0 ? (
        <p>None.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>id</th>
              <th>error</th>
            </tr>
          </thead>
          <tbody>
            {stats.failures.map((row) => (
              <tr key={row.id}>
                <td>
                  <code>{row.id}</code>
                </td>
                <td>
                  {row.error}
                  <div className="muted">{row.source_url}</div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
