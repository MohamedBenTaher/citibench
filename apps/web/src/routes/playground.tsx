import { useState, type FormEvent } from "react";
import { Link, createFileRoute } from "@tanstack/react-router";
import { toast } from "sonner";
import { ErrorAlert } from "@/components/error-alert";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { clientApiJson } from "@/lib/client-api";
import { cn } from "@/lib/utils";
import type { GenerateResult } from "@/lib/types";

const IN_CORPUS = "how does the kube-scheduler place pods onto nodes";
const OUT_OF_CORPUS = "What is the InnovX proprietary runbook password?";

function terminalLabel(terminal: GenerateResult["terminal"]): string {
  switch (terminal) {
    case "generate":
      return "generate";
    case "abstain":
      return "abstain";
    default: {
      const _exhaustive: never = terminal;
      return _exhaustive;
    }
  }
}

export const Route = createFileRoute("/playground")({
  component: PlaygroundPage,
});

function PlaygroundPage() {
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GenerateResult | null>(null);
  const canSubmit = !busy && query.trim().length > 0;

  async function onAsk(event: FormEvent) {
    event.preventDefault();
    if (!query.trim()) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const data = await clientApiJson<GenerateResult>("/generate", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ query }),
      });
      setResult(data);
      switch (data.terminal) {
        case "generate":
          toast.success(terminalLabel(data.terminal));
          break;
        case "abstain":
          toast.message(terminalLabel(data.terminal));
          break;
        default: {
          const _exhaustive: never = data.terminal;
          return _exhaustive;
        }
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

  return (
    <>
      <PageHeader
        title="Playground"
        description="Single-ask generate over the frozen corpus: retrieve, then citations or abstain. This is not a chat surface and does not keep a thread."
      />

      <Card>
        <CardHeader>
          <CardTitle>Ask</CardTitle>
          <CardDescription>
            One question. No login wall. Not a conversation.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            className="flex flex-col gap-3"
            aria-busy={busy}
            onSubmit={(event) => void onAsk(event)}
          >
            <div className="space-y-2">
              <Label htmlFor="playground-query">Question</Label>
              <Textarea
                id="playground-query"
                name="query"
                rows={4}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Ask a Kubernetes or Azure question grounded in the freeze."
              />
            </div>
            <div className="flex flex-wrap gap-2">
              <Button type="submit" disabled={!canSubmit}>
                {busy ? "Asking…" : "Ask"}
              </Button>
              <Button
                type="button"
                variant="outline"
                disabled={busy}
                onClick={() => setQuery(IN_CORPUS)}
              >
                In-corpus example
              </Button>
              <Button
                type="button"
                variant="outline"
                disabled={busy}
                onClick={() => setQuery(OUT_OF_CORPUS)}
              >
                Out-of-corpus example
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {error ? <ErrorAlert title="Generate" message={error} /> : null}

      {result ? (
        <section className="space-y-4" aria-live="polite">
          <Card>
            <CardHeader>
              <CardTitle>Answer</CardTitle>
              <CardDescription className="flex flex-wrap items-center gap-2">
                <Badge variant={result.terminal === "generate" ? "default" : "secondary"}>
                  {terminalLabel(result.terminal)}
                </Badge>
                {result.rerank_skipped ? <Badge variant="outline">rerank skipped</Badge> : null}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="whitespace-pre-wrap text-base leading-relaxed">
                {result.answer}
              </p>
              <p className="text-sm text-muted-foreground">
                {result.latency_ms.toFixed(1)} ms · ${result.cost.usd_estimate.toFixed(6)} ·{" "}
                model <code>{result.model}</code>
                {result.rerank_skipped ? " · rerank skipped" : ""}
              </p>
              <details className="text-sm text-muted-foreground">
                <summary className="cursor-pointer font-medium text-foreground">Cost method</summary>
                <p className="mt-2">
                  <code>{result.cost_method}</code>
                </p>
                <p className="mt-1">
                  Tokens: prompt {result.cost.prompt_tokens}, completion{" "}
                  {result.cost.completion_tokens}, embed {result.cost.embed_tokens}, rerank{" "}
                  {result.cost.rerank_tokens}.
                </p>
              </details>
              {result.run_id ? (
                <p className="text-sm text-muted-foreground">
                  Trace <code>{result.run_id}</code>
                  {result.trace_backend ? ` (${result.trace_backend})` : ""}.{" "}
                  <Link
                    to="/traces"
                    search={{ run_id: result.run_id }}
                    preload="intent"
                    className={cn(buttonVariants({ variant: "link" }), "h-auto px-0")}
                  >
                    Open in Traces
                  </Link>
                </p>
              ) : null}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Citations</CardTitle>
            </CardHeader>
            <CardContent>
              {result.citations.length === 0 ? (
                <p className="text-sm text-muted-foreground">None (empty on abstain).</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>chunk_id</TableHead>
                      <TableHead>text_ref</TableHead>
                      <TableHead>rank</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {result.citations.map((row) => (
                      <TableRow key={row.chunk_id}>
                        <TableCell>
                          <code>{row.chunk_id}</code>
                        </TableCell>
                        <TableCell>
                          <code>{row.text_ref}</code>
                        </TableCell>
                        <TableCell>{row.rank ?? "—"}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>

          {result.retrieved_chunk_ids.length > 0 ? (
            <details className="text-sm text-muted-foreground">
              <summary className="cursor-pointer font-medium text-foreground">
                Retrieved chunk ids ({result.retrieved_chunk_ids.length})
              </summary>
              <p className="mt-2 break-all">{result.retrieved_chunk_ids.join(", ")}</p>
            </details>
          ) : (
            <p className="text-sm text-muted-foreground">Retrieved chunk ids: None.</p>
          )}
        </section>
      ) : null}
    </>
  );
}
