import { useState } from "react";
import { createFileRoute, useRouter } from "@tanstack/react-router";
import { RouteError, RoutePending } from "../components/status";
import { getCorpusStats, postIngest, type IngestBody } from "../lib/server";
import type { CorpusStats } from "../lib/types";

export const Route = createFileRoute("/corpus")({
  loader: () => getCorpusStats(),
  pendingComponent: () => <RoutePending label="Loading corpus counts…" />,
  errorComponent: RouteError,
  component: CorpusPage,
});

function CorpusPage() {
  const router = useRouter();
  const stats = Route.useLoaderData();
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function runIngest(body: IngestBody) {
    setBusy(true);
    setActionError(null);
    try {
      await postIngest({ data: body });
      await router.invalidate();
    } catch (error: unknown) {
      setActionError(error instanceof Error ? error.message : "ingest failed");
      await router.invalidate();
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

      <StatsGrid stats={stats} />

      <p className="actions">
        <button type="button" disabled={busy} onClick={() => void runIngest({})}>
          {busy ? "Indexing…" : "Ingest / Re-index"}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void runIngest({ simulate_failure_id: "k8s-pods" })}
        >
          Re-index with one failure
        </button>
      </p>
      <p className="hint">
        Re-index is idempotent (replace per MANIFEST id).{" "}
        <code>POST /ingest</code> with <code>{`{"wipe": true}`}</code> wipes
        documents and chunks first.
      </p>

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

function StatsGrid({ stats }: { stats: CorpusStats }) {
  return (
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
  );
}
