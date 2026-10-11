import { createFileRoute, useRouter } from "@tanstack/react-router";
import { useState } from "react";
import { toast } from "sonner";
import { CorpusBrowser } from "@/components/corpus-browser";
import { ErrorAlert } from "@/components/error-alert";
import { PageHeader } from "@/components/page-header";
import { StatCards } from "@/components/stat-cards";
import { RouteError, RoutePending } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
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
  user_doc_count: 0,
  last_index_time: null,
  failures: [],
};

function formatLastIndex(iso: string | null): string {
  if (!iso) {
    return "—";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso.slice(0, 16);
  }
  return `${new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
  }).format(date)} UTC`;
}

export const Route = createFileRoute("/corpus")({
  head: () => ({
    meta: [{ title: "Corpus · Citebench" }],
  }),
  loader: async () => {
    try {
      return {
        stats: await getCorpusStats(),
        loadError: null as string | null,
      };
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
  const [sourceUrl, setSourceUrl] = useState("");
  const isEmpty = stats.doc_count === 0 && stats.chunk_count === 0;

  async function runIngest(body: IngestBody, options?: { skipConfirm?: boolean }) {
    if (
      !options?.skipConfirm &&
      !window.confirm(
        "Re-index can take several minutes. The first run also downloads ONNX embedding weights (~0.5 GB). Continue?",
      )
    ) {
      return;
    }
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

  async function addUrl() {
    const url = sourceUrl.trim();
    if (!url) {
      return;
    }
    setBusy(true);
    setActionError(null);
    try {
      await clientApiJson<CorpusStats>("/corpus/sources", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ url }),
      });
      toast.success("Source indexed");
      setSourceUrl("");
      await router.invalidate();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "source ingest failed";
      setActionError(message);
      toast.error(message);
    } finally {
      setBusy(false);
    }
  }

  async function addUpload(file: File) {
    setBusy(true);
    setActionError(null);
    try {
      const body = new FormData();
      body.append("file", file);
      await clientApiJson<CorpusStats>("/corpus/uploads", {
        method: "POST",
        body,
      });
      toast.success("Upload indexed");
      await router.invalidate();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "upload ingest failed";
      setActionError(message);
      toast.error(message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Floor"
        title="Corpus"
        description="The frozen corpus is the pinned document list. Add your own HTTPS page or file below; Ask searches both."
      />

      <StatCards
        items={[
          { label: "Documents", value: String(stats.doc_count) },
          { label: "Pages", value: String(stats.page_count) },
          { label: "Chunks", value: String(stats.chunk_count) },
          { label: "User docs", value: String(stats.user_doc_count ?? 0) },
          {
            label: "Last index",
            value: formatLastIndex(stats.last_index_time),
            title: stats.last_index_time ?? undefined,
            dense: true,
          },
        ]}
      />

      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" disabled={busy} onClick={() => void runIngest({})}>
          {busy ? "Indexing…" : "Ingest / Re-index"}
        </Button>
        {isEmpty ? (
          <p className="text-sm text-muted-foreground">Index is empty — ingest the freeze.</p>
        ) : null}
      </div>

      <CorpusBrowser />

      <Card>
        <CardHeader>
          <CardTitle>Your sources</CardTitle>
          <CardDescription>
            HTTPS URL or upload. Default cap is 64 MiB. Private/loopback hosts are rejected. This
            does not replace the eval freeze.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <form
            className="flex flex-col gap-2 sm:flex-row"
            onSubmit={(event) => {
              event.preventDefault();
              void addUrl();
            }}
          >
            <Input
              type="url"
              required
              placeholder="https://…"
              value={sourceUrl}
              disabled={busy}
              onChange={(event) => setSourceUrl(event.target.value)}
            />
            <Button type="submit" disabled={busy}>
              Index URL
            </Button>
          </form>
          <div>
            <input
              type="file"
              accept=".pdf,.html,.htm,text/html,application/pdf"
              disabled={busy}
              onChange={(event) => {
                const file = event.target.files?.[0];
                event.target.value = "";
                if (file) {
                  void addUpload(file);
                }
              }}
            />
          </div>
        </CardContent>
      </Card>

      <details className="text-sm text-muted-foreground">
        <summary className="cursor-pointer font-medium text-foreground">About re-indexing</summary>
        <p className="mt-2">
          Re-indexing is idempotent: documents are replaced, not duplicated. A full wipe is
          available only when the operator has enabled it. Embeddings run locally; the first ingest
          downloads the model once.
        </p>
      </details>

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
