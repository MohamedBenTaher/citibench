import { useMemo, useState, type FormEvent } from "react";
import { Link, createFileRoute } from "@tanstack/react-router";
import { ExternalLinkIcon } from "lucide-react";
import { toast } from "sonner";
import { ErrorAlert } from "@/components/error-alert";
import { Markdown } from "@/components/markdown";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { clientApiJson } from "@/lib/client-api";
import { getCitedChunks } from "@/lib/server";
import type { CitedChunk, Citation, GenerateResult } from "@/lib/types";

const SUGGESTIONS = [
  "How does the kube-scheduler place pods onto nodes?",
  "What is a managed identity in Azure?",
  "How are Kubernetes Secrets stored and used?",
  "What is write-ahead logging in PostgreSQL?",
  "How do you declare a path parameter in FastAPI?",
  "Compare Kubernetes ConfigMaps and Secrets.",
];

const OUT_OF_CORPUS = "What is the InnovX proprietary runbook password?";

export const Route = createFileRoute("/playground")({
  validateSearch: (search: Record<string, unknown>): { q?: string } => ({
    q: typeof search.q === "string" && search.q ? search.q : undefined,
  }),
  component: PlaygroundPage,
});

function terminalLabel(terminal: GenerateResult["terminal"]): string {
  switch (terminal) {
    case "generate":
      return "answer";
    case "abstain":
      return "abstain";
    default: {
      const _exhaustive: never = terminal;
      return _exhaustive;
    }
  }
}

function PlaygroundPage() {
  const { q } = Route.useSearch();
  const [query, setQuery] = useState(q ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GenerateResult | null>(null);
  const [snippets, setSnippets] = useState<Record<string, CitedChunk>>({});
  const canSubmit = !busy && query.trim().length > 0;

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
        toast.message("abstain — not in the freeze");
      } else {
        toast.success("answer grounded in the freeze");
      }
      const ids = data.citations.map((citation) => citation.chunk_id);
      if (ids.length > 0) {
        void getCitedChunks(ids)
          .then((payload) => {
            setSnippets(
              Object.fromEntries(payload.chunks.map((chunk) => [chunk.id, chunk])),
            );
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

  const citationIndex = useMemo(() => {
    if (!result) {
      return new Map<string, number>();
    }
    return new Map(result.citations.map((citation, index) => [citation.chunk_id, index + 1]));
  }, [result]);

  return (
    <>
      <PageHeader
        eyebrow="Set"
        title="Playground"
        description="One question over the frozen corpus. You get a grounded answer with sources, or an abstain. No thread, no follow-ups, no login."
      />

      <section className="border border-border p-4 sm:p-5" aria-labelledby="ask-heading">
        <h2 id="ask-heading" className="sr-only">
          Ask a question
        </h2>
        <form
          className="flex flex-col gap-3"
          aria-busy={busy}
          onSubmit={(event) => void onAsk(event)}
        >
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
              Try an out-of-corpus question
            </Button>
          </div>
        </form>

        <div className="mt-4 border-t border-border pt-3">
          <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
            Try
          </p>
          <div className="flex flex-wrap gap-1.5">
            {SUGGESTIONS.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                disabled={busy}
                onClick={() => setQuery(suggestion)}
                className="rounded-full border border-border px-3 py-1 text-xs text-muted-foreground transition-colors duration-150 ease-standard hover:border-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50"
              >
                {suggestion}
              </button>
            ))}
          </div>
        </div>
      </section>

      {error ? <ErrorAlert title="Generate" message={error} /> : null}

      {busy ? (
        <section className="space-y-3" aria-live="polite" aria-busy="true">
          <p className="text-sm text-muted-foreground">Retrieving and grounding…</p>
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
          <div className="grid gap-3 sm:grid-cols-2">
            <Skeleton className="h-28" />
            <Skeleton className="h-28" />
          </div>
        </section>
      ) : null}

      {result && !busy ? (
        <article className="space-y-6" aria-live="polite">
          <section className="space-y-3" aria-labelledby="answer-heading">
            <div className="flex flex-wrap items-center gap-2">
              <h2 id="answer-heading" className="font-heading text-sm font-medium tracking-tight">
                {result.terminal === "abstain" ? "Abstained" : "Answer"}
              </h2>
              <Badge variant={result.terminal === "generate" ? "default" : "secondary"}>
                {terminalLabel(result.terminal)}
              </Badge>
              {result.abstain_reason ? (
                <span className="font-mono text-[11px] text-muted-foreground">
                  {result.abstain_reason}
                </span>
              ) : null}
              {result.rerank_skipped ? <Badge variant="outline">rerank skipped</Badge> : null}
            </div>

            {result.terminal === "abstain" ? (
              <div className="border border-border bg-card px-4 py-5">
                <p className="font-heading text-lg font-medium tracking-tight">
                  {result.answer}
                </p>
                <p className="mt-2 max-w-2xl text-pretty text-sm leading-relaxed text-muted-foreground">
                  The frozen corpus does not support this question, so the bench refuses
                  rather than inventing an answer or a citation.
                </p>
              </div>
            ) : (
              <div className="border border-border bg-card px-4 py-5 sm:px-5">
                <Markdown text={result.answer} citations={result.citations} />
              </div>
            )}

            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted-foreground">
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
                  Open trace {result.run_id.slice(0, 8)}
                </Link>
              ) : null}
            </div>

            <details className="text-xs text-muted-foreground">
              <summary className="cursor-pointer font-medium text-foreground">
                Cost method
              </summary>
              <p className="mt-2 font-mono">{result.cost_method}</p>
              <p className="mt-1">
                prompt {result.cost.prompt_tokens} · completion {result.cost.completion_tokens} ·
                embed {result.cost.embed_tokens} · rerank {result.cost.rerank_tokens}
              </p>
            </details>
          </section>

          {result.citations.length > 0 ? (
            <section id="sources" className="scroll-mt-20 space-y-3" aria-labelledby="sources-heading">
              <div className="flex items-baseline justify-between gap-3">
                <h2 id="sources-heading" className="font-heading text-sm font-medium tracking-tight">
                  Sources
                </h2>
                <span className="text-xs text-muted-foreground">
                  {result.citations.length} cited chunk
                  {result.citations.length === 1 ? "" : "s"}
                </span>
              </div>
              <ol className="grid gap-3 sm:grid-cols-2">
                {result.citations.map((citation) => (
                  <SourceCard
                    key={citation.chunk_id}
                    citation={citation}
                    index={citationIndex.get(citation.chunk_id) ?? 0}
                    snippet={snippets[citation.chunk_id]}
                  />
                ))}
              </ol>
            </section>
          ) : null}
        </article>
      ) : null}
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
