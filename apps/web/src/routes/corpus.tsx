import { useState } from "react";
import { createFileRoute, useRouter } from "@tanstack/react-router";
import { toast } from "sonner";
import { ErrorAlert } from "@/components/error-alert";
import { PageHeader } from "@/components/page-header";
import { StatCards } from "@/components/stat-cards";
import { RouteError, RoutePending } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { clientApiJson } from "@/lib/client-api";
import { getCorpusStats } from "@/lib/server";
import type { CorpusStats, IngestBody } from "@/lib/types";

const EMPTY: CorpusStats = {
  doc_count: 0,
  page_count: 0,
  chunk_count: 0,
  last_index_time: null,
  failures: [],
};

export const Route = createFileRoute("/corpus")({
  loader: async () => {
    try {
      return { stats: await getCorpusStats(), loadError: null as string | null };
    } catch (error) {
      return {
        stats: EMPTY,
        loadError: error instanceof Error ? error.message : "failed to load stats",
      };
    }
  },
  pendingComponent: () => <RoutePending label="Loading corpus counts…" />,
  errorComponent: RouteError,
  component: CorpusPage,
});

function CorpusPage() {
  const router = useRouter();
  const { stats, loadError } = Route.useLoaderData();
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function runIngest(body: IngestBody) {
    setBusy(true);
    setActionError(null);
    try {
      await clientApiJson<CorpusStats>("/ingest", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body ?? {}),
      });
      toast.success("Ingest finished");
      await router.invalidate();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "ingest failed";
      setActionError(message);
      toast.error(message);
      await router.invalidate();
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Corpus"
        description="Frozen Kubernetes and Azure set from corpus/MANIFEST.md (2026-09-05, 14 URLs). Ingest snapshots only those rows."
      />

      <StatCards
        items={[
          { label: "Documents", value: String(stats.doc_count) },
          { label: "Pages", value: String(stats.page_count) },
          { label: "Chunks", value: String(stats.chunk_count) },
          { label: "Last index", value: stats.last_index_time ?? "—" },
        ]}
      />

      <div className="flex flex-wrap gap-2">
        <Button type="button" disabled={busy} onClick={() => void runIngest({})}>
          {busy ? "Indexing…" : "Ingest / Re-index"}
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={busy}
          onClick={() => void runIngest({ simulate_failure_id: "k8s-pods" })}
        >
          Re-index with one failure
        </Button>
      </div>
      <p className="text-sm text-muted-foreground">
        Re-index is idempotent (replace per MANIFEST id).{" "}
        <code>POST /ingest</code> with <code>{`{"wipe": true}`}</code> wipes documents
        and chunks first.
      </p>

      {loadError ? <ErrorAlert title="Corpus stats" message={loadError} /> : null}
      {actionError ? <ErrorAlert title="Ingest" message={actionError} /> : null}

      <Card>
        <CardHeader>
          <CardTitle>Failures</CardTitle>
          <CardDescription>Snapshot rows that did not land in the index.</CardDescription>
        </CardHeader>
        <CardContent>
          {stats.failures.length === 0 ? (
            <p className="text-sm text-muted-foreground">None.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>id</TableHead>
                  <TableHead>error</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {stats.failures.map((row) => (
                  <TableRow key={row.id}>
                    <TableCell>
                      <code>{row.id}</code>
                    </TableCell>
                    <TableCell className="whitespace-normal">
                      {row.error}
                      <div className="text-xs text-muted-foreground">{row.source_url}</div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </>
  );
}
