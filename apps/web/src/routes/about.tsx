import { createFileRoute, Link } from "@tanstack/react-router";
import { CitebenchMark } from "@/components/citebench-mark";
import { PageHeader } from "@/components/page-header";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/about")({
  head: () => ({
    meta: [{ title: "About · Citebench" }],
  }),
  component: AboutPage,
});

function AboutPage() {
  return (
    <>
      <div className="flex items-start gap-3">
        <CitebenchMark className="mt-1 size-10" />
        <PageHeader
          eyebrow="Gym"
          title="About Citebench"
          description="A citation-grounded retrieval bench over a frozen public corpus."
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>What it is</CardTitle>
          <CardDescription>
            Index → retrieve → generate or abstain, then score whether the answer stayed on
            retrieved chunks.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm leading-relaxed text-muted-foreground">
          <p>
            The circuit is{" "}
            <Link
              to="/corpus"
              preload="intent"
              className={cn(buttonVariants({ variant: "link" }), "h-auto px-0")}
            >
              Corpus
            </Link>
            ,{" "}
            <Link
              to="/playground"
              preload="intent"
              className={cn(buttonVariants({ variant: "link" }), "h-auto px-0")}
            >
              Ask
            </Link>
            ,{" "}
            <Link
              to="/traces"
              preload="intent"
              className={cn(buttonVariants({ variant: "link" }), "h-auto px-0")}
            >
              Traces
            </Link>
            , and{" "}
            <Link
              to="/evals"
              preload="intent"
              className={cn(buttonVariants({ variant: "link" }), "h-auto px-0")}
            >
              Evals
            </Link>
            . Every step is inspectable: retrieved chunks, scores, citations, and the final
            decision.
          </p>
          <p>
            If the corpus cannot support the question, Citebench abstains. It never invents a
            password, a payroll row, or a citation.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Frozen corpus</CardTitle>
          <CardDescription>
            Kubernetes, Azure, PostgreSQL, FastAPI, and xv6 documentation.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm leading-relaxed text-muted-foreground">
          <p>
            The corpus is a pinned snapshot: documents are fetched once, hashed, and indexed with
            their license recorded. Re-indexing replaces the pinned documents; a full wipe is
            opt-in.
          </p>
          <p>
            You can add your own HTTPS page or file from the Corpus tab. A source that cannot be
            fetched is reported, and the last good copy stays indexed.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Models and cost</CardTitle>
          <CardDescription>Groq is the only billed LLM. Embeddings run locally.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm leading-relaxed text-muted-foreground">
          <p>
            Answers are generated with Groq <code>openai/gpt-oss-20b</code>. A live key is required
            to generate; ingest and retrieve run without it.
          </p>
          <p>
            Embeddings are local <code>nomic-embed-text-v1.5</code> (768-d). The first ingest
            downloads the weights once into a local cache.
          </p>
          <p>
            Retrieval is hybrid: dense vectors plus full-text search, fused with Reciprocal Rank
            Fusion, then re-ranked by a cross-encoder down to the top results. Citations are always
            a subset of the retrieved chunks.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Evals and traces</CardTitle>
          <CardDescription>Public scores. No login. No invented metrics.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm leading-relaxed text-muted-foreground">
          <p>
            Faithfulness is checked against a 0.7 gate. Context precision and answer relevancy are
            logged alongside it. Unmeasured values are shown as such — never estimated.
          </p>
          <p>
            Redteam runs ten attack cases covering prompt injection, PII leaks, and jailbreaks; a
            pass is a refusal.
          </p>
          <p>
            Every ask writes a trace. Traces are stored locally and an external tracing backend can
            be connected.
          </p>
        </CardContent>
      </Card>
    </>
  );
}
