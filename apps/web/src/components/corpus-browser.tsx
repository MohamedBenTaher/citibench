import { useCallback, useEffect, useState } from "react";
import { HugeiconsIcon } from "@hugeicons/react";
import { Cancel01Icon, ExternalLinkIcon, File01Icon } from "@hugeicons/core-free-icons";
import { ErrorAlert } from "@/components/error-alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getCorpusDocument, getCorpusDocuments, getCorpusFacets } from "@/lib/server";
import type { CorpusFacets, DocumentDetail, DocumentList, DocumentRow } from "@/lib/types";

const PAGE_SIZE = 20;

const selectClass =
  "h-8 rounded-lg border border-input bg-transparent px-2 text-sm text-foreground outline-none transition-colors duration-150 ease-standard focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50";

export function CorpusBrowser() {
  const [facets, setFacets] = useState<CorpusFacets | null>(null);
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [product, setProduct] = useState("");
  const [source, setSource] = useState("");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<DocumentList | null>(null);
  const [selected, setSelected] = useState<DocumentDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getCorpusFacets()
      .then(setFacets)
      .catch(() => setFacets(null));
  }, []);

  useEffect(() => {
    const handle = window.setTimeout(() => {
      setQuery(search.trim());
      setOffset(0);
    }, 250);
    return () => window.clearTimeout(handle);
  }, [search]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = await getCorpusDocuments({
        q: query,
        product,
        source,
        limit: PAGE_SIZE,
        offset,
      });
      setData(payload);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "failed to load corpus");
    } finally {
      setLoading(false);
    }
  }, [query, product, source, offset]);

  useEffect(() => {
    void load();
  }, [load]);

  async function openDocument(doc: DocumentRow) {
    setSelected(null);
    try {
      setSelected(await getCorpusDocument(doc.id, { limit: 40 }));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "failed to load document");
    }
  }

  const total = data?.total ?? 0;
  const shownFrom = total === 0 ? 0 : offset + 1;
  const shownTo = Math.min(offset + PAGE_SIZE, total);

  return (
    <section className="space-y-3" aria-labelledby="browse-heading">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 id="browse-heading" className="font-heading text-sm font-medium tracking-tight">
            Browse the freeze
          </h2>
          <p className="text-sm text-muted-foreground">
            Every indexed document, its sections, and chunk previews. Read the floor
            before you ask.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search title, id, URL…"
            aria-label="Search corpus"
            className="w-56"
          />
          <select
            className={selectClass}
            value={product}
            aria-label="Filter by product"
            onChange={(event) => {
              setProduct(event.target.value);
              setOffset(0);
            }}
          >
            <option value="">All products</option>
            {facets?.products.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
          <select
            className={selectClass}
            value={source}
            aria-label="Filter by source"
            onChange={(event) => {
              setSource(event.target.value);
              setOffset(0);
            }}
          >
            <option value="">All sources</option>
            {facets?.sources.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </div>
      </div>

      {error ? <ErrorAlert title="Corpus" message={error} /> : null}

      <div className="overflow-hidden border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Document</TableHead>
              <TableHead className="hidden sm:table-cell">Product</TableHead>
              <TableHead className="hidden md:table-cell">Type</TableHead>
              <TableHead className="text-right">Pages</TableHead>
              <TableHead className="text-right">Chunks</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading && !data ? (
              <TableRow>
                <TableCell colSpan={5} className="text-sm text-muted-foreground">
                  Loading documents…
                </TableCell>
              </TableRow>
            ) : null}
            {data?.documents.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="text-sm text-muted-foreground">
                  No documents match this filter.
                </TableCell>
              </TableRow>
            ) : null}
            {data?.documents.map((doc) => (
              <TableRow
                key={doc.id}
                data-state={selected?.document.id === doc.id ? "selected" : undefined}
              >
                <TableCell>
                  <button
                    type="button"
                    onClick={() => void openDocument(doc)}
                    className="flex max-w-prose items-start gap-2 text-left text-sm font-medium text-foreground underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
                  >
                    <HugeiconsIcon
                      icon={File01Icon}
                      size={14}
                      className="mt-0.5 shrink-0 text-muted-foreground"
                      aria-hidden
                    />
                    <span className="line-clamp-2">{doc.title}</span>
                  </button>
                  <span className="mt-0.5 block truncate font-mono text-[11px] text-muted-foreground">
                    {doc.id}
                  </span>
                </TableCell>
                <TableCell className="hidden sm:table-cell">
                  <Badge variant="outline">{doc.product ?? "—"}</Badge>
                </TableCell>
                <TableCell className="hidden md:table-cell text-sm text-muted-foreground">
                  {doc.doc_type ?? "—"}
                </TableCell>
                <TableCell className="text-right font-mono text-sm tabular-nums">
                  {doc.page_count}
                </TableCell>
                <TableCell className="text-right font-mono text-sm tabular-nums">
                  {doc.chunk_count}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <div className="flex items-center justify-between gap-3">
        <p className="text-xs text-muted-foreground">
          {shownFrom}–{shownTo} of {total} documents
        </p>
        <div className="flex gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={loading || offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            Previous
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={loading || shownTo >= total}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            Next
          </Button>
        </div>
      </div>

      {selected ? (
        <div className="border border-border bg-card">
          <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
            <div className="min-w-0 space-y-1">
              <p className="font-heading text-sm font-medium tracking-tight">
                {selected.document.title}
              </p>
              <p className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <span className="font-mono">{selected.document.id}</span>
                {selected.document.product ? (
                  <Badge variant="outline">{selected.document.product}</Badge>
                ) : null}
                <span>{selected.document.license}</span>
                <span>
                  {selected.chunk_total} chunks · {selected.document.page_count} pages
                </span>
              </p>
              <a
                href={selected.document.source_url}
                target="_blank"
                rel="noreferrer noopener"
                className="inline-flex items-center gap-1 text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
              >
                <HugeiconsIcon icon={ExternalLinkIcon} size={13} aria-hidden />
                {selected.document.source_url}
              </a>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label="Close document"
              onClick={() => setSelected(null)}
            >
              <HugeiconsIcon icon={Cancel01Icon} size={16} />
            </Button>
          </div>
          <ol className="divide-y divide-border">
            {selected.chunks.map((chunk) => (
              <li key={chunk.id} className="px-4 py-3">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
                  <span className="font-mono tabular-nums">#{chunk.chunk_index}</span>
                  {chunk.section ? (
                    <span className="font-medium text-foreground/80">{chunk.section}</span>
                  ) : null}
                  {chunk.page != null ? <span>page {chunk.page}</span> : null}
                  <span className="font-mono">{chunk.token_count} tok</span>
                </div>
                <p className="mt-1 text-pretty text-sm leading-relaxed text-muted-foreground">
                  {chunk.preview}
                  {chunk.preview.length >= 600 ? "…" : ""}
                </p>
              </li>
            ))}
          </ol>
        </div>
      ) : null}
    </section>
  );
}
