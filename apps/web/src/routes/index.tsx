import { Link, createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/page-header";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/")({
  component: IndexPage,
});

const surfaces = [
  {
    to: "/evals" as const,
    title: "Evals",
    body: "Faithfulness gate 0.7, redteam blocks, and receipts into Traces. Start here, not on Playground.",
  },
  {
    to: "/traces" as const,
    title: "Traces",
    body: "Every hop: retrieve → rerank → generate|abstain. Deep-link with ?run_id=.",
  },
  {
    to: "/corpus" as const,
    title: "Corpus",
    body: "Frozen 14-doc index counts (docs, pages, chunks, last index, failures).",
  },
  {
    to: "/playground" as const,
    title: "Playground",
    body: "Single-ask generate; not a chat surface. Creates a RunTrace.",
  },
] as const;

function IndexPage() {
  return (
    <>
      <PageHeader
        title="Citebench"
        description="Index of placeholder surfaces. This is not a chat homepage and does not run retrieval."
      />
      <div className="grid gap-3 sm:grid-cols-2">
        {surfaces.map((surface) => (
          <Card key={surface.to}>
            <CardHeader>
              <CardTitle>
                <Link
                  to={surface.to}
                  preload="intent"
                  className={cn(buttonVariants({ variant: "link" }), "h-auto px-0 text-base")}
                >
                  {surface.title}
                </Link>
              </CardTitle>
              <CardDescription>{surface.body}</CardDescription>
            </CardHeader>
          </Card>
        ))}
        <Card>
          <CardHeader>
            <CardTitle>Metrics</CardTitle>
            <CardDescription>
              Scrape <code>GET /metrics</code> on the API (p50/p95, cost/1k, last-eval
              faithfulness). Not a dashboard.
            </CardDescription>
          </CardHeader>
          <CardContent />
        </Card>
      </div>
    </>
  );
}
