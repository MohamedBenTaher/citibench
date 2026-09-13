import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { Link, createFileRoute } from "@tanstack/react-router";
import { ExternalLinkIcon } from "lucide-react";
import { toast } from "sonner";
import { ErrorAlert } from "@/components/error-alert";
import { Markdown } from "@/components/markdown";
import { PageHeader } from "@/components/page-header";
import { StatusPill } from "@/components/status-pill";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { clientApiJson } from "@/lib/client-api";
import { getCitedChunks, getCorpusSuggestions } from "@/lib/server";
import { cn } from "@/lib/utils";
import type {
  CitedChunk,
  Citation,
  CorpusSuggestion,
  GenerateResult,
  RetrievalHit,
} from "@/lib/types";

const OUT_OF_CORPUS = "What is the InnovX proprietary runbook password?";

export const Route = createFileRoute("/playground")({
  validateSearch: (search: Record<string, unknown>): { q?: string } => ({
    q: typeof search.q === "string" && search.q ? search.q : undefined,
  }),
  component: PlaygroundPage,
});

function score(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return value.toFixed(3);
}

function PlaygroundPage() {
  const { q } = Route.useSearch();
  const [query, setQuery] = useState(q ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GenerateResult | null>(null);
  const [snippets, setSnippets] = useState<Record<string, CitedChunk>>({});
  const [suggestions, setSuggestions] = useState<CorpusSuggestion[]>([]);
  const canSubmit = !busy && query.trim().length > 0;

  useEffect(() => {
    getCorpusSuggestions(7)
      .then((payload) => setSuggestions(payload.suggestions))
      .catch(() => setSuggestions([]));
  }, []);

  async function onAsk(event: FormEvent) {
    event.preventDefault();
    const question = query.trim();
    if (!question) {
      return;
    }
    setBusy(true);
    setError(null);
    setSnippets({});
    try {
      const data = await clientApiJson<GenerateResult>("/generate", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ query: question }),
      });
      setResult(data);
      if (data.terminal === "abstain") {
        toast.message("abstain — corpus did not support the question");
      } else {
        toast.success("answer grounded in the freeze");
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

  return (
    <>
      <PageHeader
        eyebrow="Ask"
        title="Single ask"
        description="One question over the frozen corpus. You get a grounded answer with sources, or an abstain. No thread, no follow-ups, no login."
      />

      <section className="border border-border bg-card p-4 sm:p-5" aria-labelledby="ask-heading">
        <h2 id="ask-heading" className="sr-only">
          Ask a question
        </h2>
        <form className="flex flex-col gap-3" aria-busy={busy} onSubmit={(event) => void onAsk(event)}>
          <Textarea
            id="playground-query"
            name="query"
            rows={3}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Ask about Kubernetes, Azure, PostgreSQL, FastAPI, or xv6 — grounded in the freeze."
            className="text-base"
          />
          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit" size="lg" disabled={!canSubmit} className="min-h-11 px-5">
              {busy ? "Researching…" : "Ask"}
            </Button>
            {result || query ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={busy}
                onClick={() => {
                  setQuery("");
                  setResult(null);
                  setError(null);
                  setSnippets({});
                }}
              >
                Clear
              </Button>
            ) : null}
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={busy}
              onClick={() => setQuery(OUT_OF_CORPUS)}
            >
              Test abstain (out of corpus)
            </Button>
          </div>
        </form>

        {suggestions.length > 0 ? (
          <div className="mt-4 border-t border-border pt-3">
            <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
              From the corpus
            </p>
            <div className="flex flex-wrap gap-1.5">
              {suggestions.map((suggestion) => (
                <button
                  key={suggestion.question}
                  type="button"
                  disabled={busy}
                  title={suggestion.product}
                  onClick={() => setQuery(suggestion.question)}
                  className="rounded-full border border-border px-3 py-1 text-left text-xs text-muted-foreground transition-colors duration-150 ease-standard hover:border-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50"
                >
                  {suggestion.question}
                </button>
              ))}
            </div>
          </div>
        ) : null}
      </section>

      {error ? <ErrorAlert title="Generate" message={error} /> : null}

      {busy ? (
        <section className="space-y-3" aria-live="polite" aria-busy="true">
          <p className="text-sm text-muted-foreground">Retrieving and grounding…</p>
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
          <Skeleton className="h-28" />
        </section>
      ) : null}

      {result && !busy ? (
        <article className="space-y-8" aria-live="polite">
          <Section step="01" title="Query">
            <p className="text-pretty text-[15px] leading-relaxed text-foreground">
              {result.query}
            </p>
          </Section>

          <Section
            step="02"
            title="Retrieved chunks"
            aside={`${retrieved.length || result.retrieved_chunk_ids.length} hits · citations are a strict subset`}
          >
            {retrieved.length === 0 ? (
              <p className="text-sm text-muted-foreground">No chunks retrieved.</p>
            ) : (
              <div className="overflow-hidden border border-border">
                <table className="w-full border-collapse text-left text-xs">
                  <thead className="bg-muted/40 text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
                    <tr>
                      <th className="px-3 py-2 font-medium">#</th>
                      <th className="px-3 py-2 font-medium">Chunk</th>
                      <th className="hidden px-3 py-2 text-right font-medium sm:table-cell">dense</th>
                      <th className="hidden px-3 py-2 text-right font-medium sm:table-cell">fts</th>
                      <th className="hidden px-3 py-2 text-right font-medium md:table-cell">rrf</th>
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
                          <td className="px-3 py-2 font-mono tabular-nums text-muted-foreground">
                            {hit.rank}
                          </td>
                          <td className="px-3 py-2">
                            <span className="flex items-center gap-1.5">
                              {cited ? (
                                <span className="size-1.5 rounded-full bg-success" aria-label="cited" />
                              ) : null}
                              <span className="font-mono text-[11px] text-foreground">
                                {hit.doc_id}
                              </span>
                            </span>
                            {hit.section ? (
                              <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">
                                {hit.section}
                              </span>
                            ) : null}
                          </td>
                          <td className="hidden px-3 py-2 text-right font-mono tabular-nums text-muted-foreground sm:table-cell">
                            {score(hit.vector_score)}
                          </td>
                          <td className="hidden px-3 py-2 text-right font-mono tabular-nums text-muted-foreground sm:table-cell">
                            {score(hit.fts_score)}
                          </td>
                          <td className="hidden px-3 py-2 text-right font-mono tabular-nums text-muted-foreground md:table-cell">
                            {score(hit.fused_score)}
                          </td>
                          <td className="px-3 py-2 text-right font-mono tabular-nums text-foreground">
                            {score(hit.rerank_score ?? hit.score)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Section>

          <Section
            step="03"
            title="Decision"
            aside={
              result.terminal === "abstain"
                ? "no answer generated"
                : `grounded on ${result.citations.length} of ${retrieved.length || result.retrieved_chunk_ids.length} retrieved chunks`
            }
          >
            <div className="flex flex-wrap items-center gap-3">
              <StatusPill tone={result.terminal === "abstain" ? "warning" : "success"}>
                {result.terminal === "abstain" ? "abstain" : "generate"}
              </StatusPill>
              {result.abstain_reason ? (
                <span className="font-mono text-[11px] text-muted-foreground">
                  {result.abstain_reason}
                </span>
              ) : null}
              {result.rerank_skipped ? <Badge variant="outline">rerank skipped</Badge> : null}
              <span className="ml-auto flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
                <span className="font-mono tabular-nums">{result.latency_ms.toFixed(1)} ms</span>
                <span className="font-mono tabular-nums">${result.cost.usd_estimate.toFixed(6)}</span>
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
              </span>
            </div>
          </Section>

          <Section step="04" title={result.terminal === "abstain" ? "Abstained" : "Answer"}>
            {result.terminal === "abstain" ? (
              <div className="border-l-2 border-warning bg-warning/10 px-4 py-4">
                <p className="font-heading text-lg font-medium tracking-tight">
                  {result.answer}
                </p>
                <p className="mt-2 max-w-2xl text-pretty text-sm leading-relaxed text-muted-foreground">
                  The frozen corpus does not contain sufficient evidence, so the bench
                  refuses rather than inventing an answer or a citation.
                </p>
              </div>
            ) : (
              <Markdown text={result.answer} citations={result.citations} />
            )}
          </Section>

          {result.citations.length > 0 ? (
            <Section
              step="05"
              title="Sources"
              aside={`${result.citations.length} cited chunk${result.citations.length === 1 ? "" : "s"}`}
              id="sources"
            >
              <ol className="grid gap-3 sm:grid-cols-2">
                {result.citations.map((citation, index) => (
                  <SourceCard
                    key={citation.chunk_id}
                    citation={citation}
                    index={index + 1}
                    snippet={snippets[citation.chunk_id]}
                  />
                ))}
              </ol>
            </Section>
          ) : null}
        </article>
      ) : null}
    </>
  );
}

function Section({
  step,
  title,
  aside,
  id,
  children,
}: {
  step: string;
  title: string;
  aside?: string;
  id?: string;
  children: ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-20 space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h2 className="flex items-center gap-2 font-heading text-sm font-medium tracking-tight">
          <span className="font-mono text-[11px] tabular-nums text-muted-foreground">{step}</span>
          {title}
        </h2>
        {aside ? <span className="text-xs text-muted-foreground">{aside}</span> : null}
      </div>
      {children}
    </section>
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
    <li className="flex flex-col gap-2 border border-border bg-card p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-sm border border-border px-1 font-mono text-[11px] text-muted-foreground">
          {index}
        </span>
        {product ? <Badge variant="outline">{product}</Badge> : null}
      </div>
      <p className="text-sm font-medium leading-snug text-foreground">{title}</p>
      {section || page != null ? (
        <p className="text-xs text-muted-foreground">
          {section}
          {section && page != null ? " · " : ""}
          {page != null ? `page ${page}` : ""}
        </p>
      ) : null}
      {snippet?.text ? (
        <p className="line-clamp-4 text-pretty text-xs leading-relaxed text-muted-foreground">
          {snippet.text}
        </p>
      ) : null}
      <div className="mt-auto flex flex-wrap items-center gap-x-3 gap-y-1 pt-1 text-[11px] text-muted-foreground">
        {url ? (
          <a
            href={url}
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex items-center gap-1 underline-offset-4 hover:text-foreground hover:underline"
          >
            <ExternalLinkIcon className="size-3" aria-hidden />
            source
          </a>
        ) : null}
        <span className="font-mono">{citation.text_ref}</span>
      </div>
    </li>
  );
}
