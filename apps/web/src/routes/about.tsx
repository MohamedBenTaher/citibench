import { Link, createFileRoute } from "@tanstack/react-router";
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
          description="A citation-grounded retrieval bench for a frozen public corpus. It is not a chat product and does not keep a thread."
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
            The homepage is a research-gym index, not a chat. The circuit is{" "}
            <Link to="/corpus" preload="intent" className={cn(buttonVariants({ variant: "link" }), "h-auto px-0")}>
              Corpus
            </Link>
            ,{" "}
            <Link
              to="/playground"
              preload="intent"
              className={cn(buttonVariants({ variant: "link" }), "h-auto px-0")}
            >
              Playground
            </Link>{" "}
            (single ask),{" "}
            <Link to="/traces" preload="intent" className={cn(buttonVariants({ variant: "link" }), "h-auto px-0")}>
              Traces
            </Link>
            , and{" "}
            <Link to="/evals" preload="intent" className={cn(buttonVariants({ variant: "link" }), "h-auto px-0")}>
              Evals
            </Link>
            . Demo screenshots should start on Evals or a failing trace, not a chat bubble.
          </p>
          <p>
            If the corpus cannot support the question, the system must abstain. It must not invent
            a password, a payroll row, or a citation.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Frozen corpus</CardTitle>
          <CardDescription>
            14 Kubernetes and Azure URLs pinned in <code>corpus/MANIFEST.md</code> (freeze
            2026-09-05).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm leading-relaxed text-muted-foreground">
          <p>
            Ingest snapshots only those rows. Re-index replaces per MANIFEST id.{" "}
            <code>POST /ingest</code> with <code>{`{"wipe": true}`}</code> only
            works when the API has <code>CITEBENCH_ALLOW_WIPE=1</code>. It then
            clears documents and chunks.
          </p>
          <p>
            The browser talks to FastAPI at <code>VITE_API_URL</code> (default{" "}
            <code>http://localhost:8000</code>). Compose SSR uses <code>API_URL=http://api:8000</code>.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Models and cost</CardTitle>
          <CardDescription>Groq is the only billed LLM. Embeddings are local.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm leading-relaxed text-muted-foreground">
          <p>
            Chat / generate uses Groq <code>openai/gpt-oss-20b</code> (override with{" "}
            <code>GROQ_CHAT_MODEL</code>). A live <code>GROQ_API_KEY</code> is required for
            Playground generate, not for ingest or retrieve.
          </p>
          <p>
            Embeddings are local <code>nomic-embed-text-v1.5</code> (768-d ONNX via fastembed).
            Groq no longer hosts that model. First ingest downloads the weights (~0.5&nbsp;GB) into{" "}
            <code>NOMIC_CACHE_DIR</code>.
          </p>
          <p>
            Retrieve is hybrid: dense + FTS, RRF <code>k=60</code>, FlashRank 50→8. Citations are
            always a subset of retrieved chunk ids.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Evals and traces</CardTitle>
          <CardDescription>Public scores. No login wall. No invented metrics.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm leading-relaxed text-muted-foreground">
          <p>
            RAGAS CI gates faithfulness at 0.7. That number is a CI threshold, not a published
            Citebench score. Companion metrics (context precision, answer relevancy) are logged
            only.
          </p>
          <p>
            Redteam is 10 Contract A cases (injection / pii_leak / jailbreak). The runner reuses
            generate → abstain.
          </p>
          <p>
            Langfuse is optional. Missing or rejected keys keep a local RunTrace store so{" "}
            <code>/traces</code> still works.
          </p>
        </CardContent>
      </Card>
    </>
  );
}
