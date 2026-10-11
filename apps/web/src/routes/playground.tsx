import { ExternalLinkIcon, Loading03Icon, Search01Icon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { type FormEvent, type KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { CitebenchMark } from "@/components/citebench-mark";
import { ErrorAlert } from "@/components/error-alert";
import { Markdown } from "@/components/markdown";
import { StatusPill } from "@/components/status-pill";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { clientApiJson } from "@/lib/client-api";
import { formatNumber } from "@/lib/format";
import { getCitedChunks, getCorpusFacets, getCorpusSuggestions } from "@/lib/server";
import type {
  Citation,
  CitedChunk,
  CorpusFacets,
  CorpusSuggestion,
  GenerateResult,
  RetrievalHit,
} from "@/lib/types";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/playground")({
  validateSearch: (search: Record<string, unknown>): { q?: string } => ({
    q: typeof search.q === "string" && search.q ? search.q : undefined,
  }),
  component: PlaygroundPage,
});

function SearchBar({
  value,
  onChange,
  onSubmit,
  busy,
  compact = false,
  autoFocus = false,
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  busy: boolean;
  compact?: boolean;
  autoFocus?: boolean;
}) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // biome-ignore lint/correctness/useExhaustiveDependencies: value triggers re-measure on text change
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) {
      return;
    }
    const lineHeight = Number.parseFloat(getComputedStyle(el).lineHeight) || 26;
    const maxHeight = lineHeight * 6;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`;
    el.style.overflowY = el.scrollHeight > maxHeight ? "auto" : "hidden";
  }, [value]);

  function handleKey(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      onSubmit();
    }
  }

  return (
    <form
      className="w-full max-w-3xl"
      onSubmit={(event: FormEvent) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <div
        className={cn(
          "flex items-end gap-2 rounded-2xl border border-border bg-card shadow-sm transition-shadow duration-150 ease-standard focus-within:border-ring/60 focus-within:shadow-md focus-within:ring-4 focus-within:ring-ring/10",
          compact ? "p-2 pl-4" : "p-2.5 pl-5",
        )}
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKey}
          rows={2}
          autoFocus={autoFocus}
          aria-label="Ask a question"
          placeholder="Ask anything about the corpus…"
          className="min-h-[3.5rem] flex-1 resize-none bg-transparent px-0 py-2 text-base leading-relaxed text-foreground outline-none placeholder:text-muted-foreground"
        />
        <button
          type="submit"
          disabled={busy || !value.trim()}
          aria-label="Ask"
          className={cn(
            "inline-flex shrink-0 items-center justify-center rounded-xl bg-primary text-white transition-colors duration-150 ease-standard hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-40",
            compact ? "size-10" : "size-11",
          )}
        >
          {busy ? (
            <HugeiconsIcon
              icon={Loading03Icon}
              size={compact ? 18 : 20}
              className="animate-spin motion-reduce:animate-none"
            />
          ) : (
            <HugeiconsIcon icon={Search01Icon} size={compact ? 18 : 22} strokeWidth={2} />
          )}
        </button>
      </div>
    </form>
  );
}

export function SuggestionChips({
  items,
  onPick,
  busy,
}: {
  items: CorpusSuggestion[];
  onPick: (question: string) => void;
  busy: boolean;
}) {
  if (items.length === 0) {
    return null;
  }
  return (
    <div className="flex flex-wrap justify-center gap-2">
      {items.map((item) => (
        <button
          key={item.question}
          type="button"
          disabled={busy}
          title={item.product || undefined}
          onClick={() => onPick(item.question)}
          className="rounded-full border border-border bg-card px-3.5 py-1.5 text-sm text-muted-foreground transition-colors duration-150 ease-standard hover:border-foreground/40 hover:text-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50"
        >
          {item.question}
        </button>
      ))}
    </div>
  );
}

function FilterRow({
  facets,
  product,
  docType,
  onProduct,
  onDocType,
  busy,
  center = false,
}: {
  facets: CorpusFacets | null;
  product: string;
  docType: string;
  onProduct: (value: string) => void;
  onDocType: (value: string) => void;
  busy: boolean;
  center?: boolean;
}) {
  const selectClass =
    "h-8 rounded-lg border border-border bg-card px-2 text-sm text-foreground outline-none transition-colors duration-150 ease-standard focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50";
  return (
    <div className={cn("flex flex-wrap items-center gap-2", center && "justify-center")}>
      <select
        className={selectClass}
        value={product}
        disabled={busy}
        aria-label="Filter by product"
        onChange={(event) => onProduct(event.target.value)}
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
        value={docType}
        disabled={busy}
        aria-label="Filter by document type"
        onChange={(event) => onDocType(event.target.value)}
      >
        <option value="">All types</option>
        {facets?.doc_types.map((value) => (
          <option key={value} value={value}>
            {value}
          </option>
        ))}
      </select>
      {product || docType ? (
        <button
          type="button"
          disabled={busy}
          onClick={() => {
            onProduct("");
            onDocType("");
          }}
          className="text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          Clear filters
        </button>
      ) : null}
    </div>
  );
}

function PlaygroundPage() {
  const { q } = Route.useSearch();
  const [query, setQuery] = useState(q ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GenerateResult | null>(null);
  const [snippets, setSnippets] = useState<Record<string, CitedChunk>>({});
  const [suggestions, setSuggestions] = useState<CorpusSuggestion[]>([]);
  const [facets, setFacets] = useState<CorpusFacets | null>(null);
  const [product, setProduct] = useState("");
  const [docType, setDocType] = useState("");

  useEffect(() => {
    getCorpusSuggestions(6)
      .then((payload) => setSuggestions(payload.suggestions))
      .catch(() => setSuggestions([]));
    getCorpusFacets()
      .then(setFacets)
      .catch(() => setFacets(null));
  }, []);

  async function ask() {
    const question = query.trim();
    if (!question || busy) {
      return;
    }
    setBusy(true);
    setError(null);
    setSnippets({});
    try {
      const filters: Record<string, string> = {};
      if (product) {
        filters.product = product;
      }
      if (docType) {
        filters.doc_type = docType;
      }
      const data = await clientApiJson<GenerateResult>("/generate", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          query: question,
          filters: Object.keys(filters).length > 0 ? filters : undefined,
        }),
      });
      setResult(data);
      if (data.terminal === "abstain") {
        toast.message("abstain — corpus did not support the question");
      }
      const ids = data.citations.map((citation) => citation.chunk_id);
      if (ids.length > 0) {
        void getCitedChunks(ids)
          .then((payload) => {
            setSnippets(Object.fromEntries(payload.chunks.map((chunk) => [chunk.id, chunk])));
          })
          .catch(() => setSnippets({}));
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "generate failed";
      setResult(null);
      setError(message);
      toast.error(message);
    } finally {
      setBusy(false);
    }
  }

  const citedIds = useMemo(
    () => new Set((result?.citations ?? []).map((citation) => citation.chunk_id)),
    [result],
  );
  const retrieved = result?.retrieved_hits ?? [];
  const hasResult = Boolean(result);
  const isEmptyState = !hasResult && !busy && !error;

  if (isEmptyState) {
    return (
      <section className="mx-auto flex w-full max-w-2xl flex-col items-center gap-7 py-10 text-center sm:py-20">
        <CitebenchMark className="size-12" title="Citebench" />
        <div className="space-y-2">
          <h1 className="font-heading text-balance text-3xl font-semibold tracking-tight sm:text-4xl">
            Ask the bench
          </h1>
          <p className="text-pretty text-sm leading-relaxed text-muted-foreground">
            Grounded answers with citations, or an honest abstain. One question over the frozen
            corpus.
          </p>
        </div>
        <SearchBar
          value={query}
          onChange={setQuery}
          onSubmit={() => void ask()}
          busy={busy}
          autoFocus
        />
        <FilterRow
          facets={facets}
          product={product}
          docType={docType}
          onProduct={setProduct}
          onDocType={setDocType}
          busy={busy}
          center
        />
        <SuggestionChips items={suggestions} onPick={setQuery} busy={busy} />
      </section>
    );
  }

  return (
    <>
      <div className="space-y-2 lg:sticky lg:top-0 lg:z-10 lg:-mx-6 lg:border-b lg:border-border lg:bg-background/85 lg:px-6 lg:py-3 lg:backdrop-blur">
        <SearchBar
          value={query}
          onChange={setQuery}
          onSubmit={() => void ask()}
          busy={busy}
          compact
        />
        <FilterRow
          facets={facets}
          product={product}
          docType={docType}
          onProduct={setProduct}
          onDocType={setDocType}
          busy={busy}
        />
      </div>

      {error ? <ErrorAlert title="Generate" message={error} /> : null}

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="min-w-0 space-y-6">
          {busy ? (
            <div className="space-y-3" aria-live="polite" aria-busy="true">
              <p className="text-sm text-muted-foreground">Researching the corpus…</p>
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          ) : null}

          {result && !busy ? (
            <>
              <div className="flex flex-wrap items-center gap-3">
                <StatusPill tone={result.terminal === "abstain" ? "warning" : "success"}>
                  {result.terminal === "abstain" ? "abstain" : "grounded answer"}
                </StatusPill>
                {result.terminal === "generate" ? (
                  <span className="text-xs text-muted-foreground">
                    grounded on {result.citations.length} of{" "}
                    {retrieved.length || result.retrieved_chunk_ids.length} retrieved chunks
                  </span>
                ) : null}
                {result.rerank_skipped ? <Badge variant="outline">rerank skipped</Badge> : null}
              </div>

              <p className="text-pretty text-lg font-medium leading-snug tracking-tight text-foreground">
                {result.query}
              </p>

              {result.terminal === "abstain" ? (
                <div className="border-l-2 border-warning bg-warning/10 px-4 py-4">
                  <p className="font-heading text-lg font-medium tracking-tight">{result.answer}</p>
                  <p className="mt-2 max-w-2xl text-pretty text-sm leading-relaxed text-muted-foreground">
                    The frozen corpus does not contain sufficient evidence, so the bench refuses
                    rather than inventing an answer or a citation.
                  </p>
                </div>
              ) : (
                <Markdown text={result.answer} citations={result.citations} />
              )}

              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
                <span className="font-mono tabular-nums">{result.latency_ms.toFixed(1)} ms</span>
                <span className="font-mono tabular-nums">
                  ${result.cost.usd_estimate.toFixed(6)}
                </span>
                <span>
                  model <code className="font-mono">{result.model}</code>
                </span>
                {result.run_id ? (
                  <Link
                    to="/traces"
                    search={{ run_id: result.run_id }}
                    preload="intent"
                    className="underline-offset-4 hover:text-foreground hover:underline"
                  >
                    trace {result.run_id.slice(0, 8)}
                  </Link>
                ) : null}
              </div>

              <details className="group border-t border-border pt-3 text-sm text-muted-foreground">
                <summary className="cursor-pointer font-medium text-foreground">
                  How this was retrieved
                </summary>
                <div className="mt-3 space-y-2">
                  {retrieved.length === 0 ? (
                    <p>No chunks were retrieved.</p>
                  ) : (
                    <div className="overflow-hidden border border-border">
                      <table className="w-full border-collapse text-left text-xs">
                        <thead className="bg-muted/40 text-[10px] uppercase tracking-[0.1em]">
                          <tr>
                            <th className="px-3 py-2 font-medium">#</th>
                            <th className="px-3 py-2 font-medium">Chunk</th>
                            <th className="hidden px-3 py-2 text-right font-medium sm:table-cell">
                              dense
                            </th>
                            <th className="hidden px-3 py-2 text-right font-medium sm:table-cell">
                              fts
                            </th>
                            <th className="hidden px-3 py-2 text-right font-medium md:table-cell">
                              rrf
                            </th>
                            <th className="px-3 py-2 text-right font-medium">flash</th>
                          </tr>
                        </thead>
                        <tbody>
                          {retrieved.map((hit: RetrievalHit) => {
                            const cited = citedIds.has(hit.chunk_id);
                            return (
                              <tr
                                key={hit.chunk_id}
                                className={cn(
                                  "border-t border-border",
                                  cited && "bg-success/[0.06]",
                                )}
                              >
                                <td className="px-3 py-2 font-mono tabular-nums">{hit.rank}</td>
                                <td className="px-3 py-2">
                                  <span className="flex items-center gap-1.5">
                                    {cited ? (
                                      <span
                                        className="size-1.5 rounded-full bg-success"
                                        role="img"
                                        aria-label="cited"
                                      />
                                    ) : null}
                                    <span className="font-mono text-[11px] text-foreground">
                                      {hit.doc_id}
                                    </span>
                                  </span>
                                  {hit.section ? (
                                    <span className="mt-0.5 block truncate text-[11px]">
                                      {hit.section}
                                    </span>
                                  ) : null}
                                </td>
                                <td className="hidden px-3 py-2 text-right font-mono tabular-nums sm:table-cell">
                                  {formatNumber(hit.vector_score)}
                                </td>
                                <td className="hidden px-3 py-2 text-right font-mono tabular-nums sm:table-cell">
                                  {formatNumber(hit.fts_score)}
                                </td>
                                <td className="hidden px-3 py-2 text-right font-mono tabular-nums md:table-cell">
                                  {formatNumber(hit.fused_score)}
                                </td>
                                <td className="px-3 py-2 text-right font-mono tabular-nums text-foreground">
                                  {formatNumber(hit.rerank_score ?? hit.score)}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                  <p>
                    Citations are drawn only from these retrieved chunks. Cost method{" "}
                    <code className="font-mono">{result.cost_method}</code>.
                  </p>
                </div>
              </details>
            </>
          ) : null}
        </div>

        <aside className="min-w-0 space-y-3 lg:sticky lg:top-24 lg:self-start">
          {result && result.citations.length > 0 ? (
            <>
              <div className="flex items-baseline justify-between gap-2">
                <h2 className="font-heading text-sm font-medium tracking-tight">Sources</h2>
                <span className="text-xs text-muted-foreground">
                  {result.citations.length} cited
                </span>
              </div>
              <ol id="sources" className="space-y-3">
                {result.citations.map((citation, index) => (
                  <SourceCard
                    key={citation.chunk_id}
                    citation={citation}
                    index={index + 1}
                    snippet={snippets[citation.chunk_id]}
                  />
                ))}
              </ol>
            </>
          ) : null}
        </aside>
      </div>
    </>
  );
}

function SourceCard({
  citation,
  index,
  snippet,
}: {
  citation: Citation;
  index: number;
  snippet?: CitedChunk;
}) {
  const title = citation.title ?? snippet?.title ?? citation.doc_id;
  const section = citation.section ?? snippet?.section ?? null;
  const page = citation.page ?? snippet?.page ?? null;
  const url = citation.url ?? snippet?.url ?? null;
  const product = citation.product ?? snippet?.product ?? null;

  return (
    <li className="border border-border bg-card p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="inline-flex size-5 items-center justify-center rounded-full bg-muted font-mono text-[11px] text-muted-foreground">
          {index}
        </span>
        {product ? <Badge variant="outline">{product}</Badge> : null}
      </div>
      <p className="mt-2 text-sm font-medium leading-snug text-foreground">{title}</p>
      {section || page != null ? (
        <p className="mt-0.5 text-xs text-muted-foreground">
          {section}
          {section && page != null ? " · " : ""}
          {page != null ? `page ${page}` : ""}
        </p>
      ) : null}
      {snippet?.text ? (
        <p className="mt-1.5 line-clamp-4 text-pretty text-xs leading-relaxed text-muted-foreground">
          {snippet.text}
        </p>
      ) : null}
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
        {url ? (
          <a
            href={url}
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex items-center gap-1 underline-offset-4 hover:text-foreground hover:underline"
          >
            <HugeiconsIcon icon={ExternalLinkIcon} size={13} aria-hidden />
            source
          </a>
        ) : null}
        <span className="truncate font-mono">{citation.text_ref}</span>
      </div>
    </li>
  );
}
