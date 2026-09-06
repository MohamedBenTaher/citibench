import { Link, createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/")({
  component: IndexPage,
});

function IndexPage() {
  return (
    <>
      <h1>Citebench</h1>
      <p>
        Index of placeholder surfaces. This is not a chat homepage and does not
        run retrieval.
      </p>
      <ul>
        <li>
          <Link to="/corpus">Corpus</Link> — frozen 14-doc index counts
          (docs, pages, chunks, last index, failures).
        </li>
        <li>
          <Link to="/playground">Playground</Link> — single-ask generate; not a
          chat surface.
        </li>
        <li>
          <Link to="/traces">Traces</Link> — RunTrace list (Langfuse + local
          fallback).
        </li>
        <li>
          <Link to="/evals">Evals</Link> — public RAGAS last-run plus 10
          redteam cases. Start demo screenshots here, not on Playground.
        </li>
        <li>
          Metrics — scrape <code>GET /metrics</code> on the API (p50/p95,
          cost/1k, last-eval faithfulness). Not a dashboard.
        </li>
      </ul>
    </>
  );
}
