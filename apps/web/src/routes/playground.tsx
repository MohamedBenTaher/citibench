import { useState, type FormEvent } from "react";
import { Link, createFileRoute } from "@tanstack/react-router";
import { postGenerate } from "../lib/server";
import type { GenerateResult } from "../lib/types";

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

  async function onAsk(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const outcome = await postGenerate({ data: { query } });
      if (!outcome.ok) {
        setResult(null);
        setError(outcome.error);
        return;
      }
      setResult(outcome.data);
    } catch (err: unknown) {
      setResult(null);
      setError(err instanceof Error ? err.message : "generate failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1>Playground</h1>
      <p>
        Single-ask generate over the frozen corpus: retrieve, then citations or
        abstain. This is not a chat surface and does not keep a thread.
      </p>

      <form className="ask" onSubmit={(event) => void onAsk(event)}>
        <label htmlFor="playground-query">Question</label>
        <textarea
          id="playground-query"
          name="query"
          rows={4}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Ask a Kubernetes or Azure question grounded in the freeze."
        />
        <p className="actions">
          <button type="submit" disabled={busy}>
            {busy ? "Asking…" : "Ask"}
          </button>
          <button type="button" disabled={busy} onClick={() => setQuery(IN_CORPUS)}>
            In-corpus example
          </button>
          <button type="button" disabled={busy} onClick={() => setQuery(OUT_OF_CORPUS)}>
            Out-of-corpus example
          </button>
        </p>
      </form>

      {error ? <p className="error">{error}</p> : null}

      {result ? (
        <section className="result" aria-live="polite">
          <h2>Answer</h2>
          <p className="answer">{result.answer}</p>

          <dl className="stats">
            <div>
              <dt>Path</dt>
              <dd>{result.path.join(" → ") || "—"}</dd>
            </div>
            <div>
              <dt>Terminal</dt>
              <dd>{terminalLabel(result.terminal)}</dd>
            </div>
            <div>
              <dt>Abstained</dt>
              <dd>{result.abstained ? "yes" : "no"}</dd>
            </div>
            <div>
              <dt>Reason</dt>
              <dd>{result.abstain_reason ?? "—"}</dd>
            </div>
            <div>
              <dt>Latency</dt>
              <dd>{result.latency_ms.toFixed(1)} ms</dd>
            </div>
            <div>
              <dt>Estimated cost</dt>
              <dd>${result.cost.usd_estimate.toFixed(6)}</dd>
            </div>
          </dl>

          <p className="muted">
            Model <code>{result.model}</code>
            {result.rerank_skipped ? " · rerank skipped" : ""}. Cost method{" "}
            <code>{result.cost_method}</code>
          </p>
          <p className="muted">
            Tokens: prompt {result.cost.prompt_tokens}, completion{" "}
            {result.cost.completion_tokens}, embed {result.cost.embed_tokens},
            rerank {result.cost.rerank_tokens}.
          </p>
          {result.run_id ? (
            <p className="muted">
              Trace <code>{result.run_id}</code>
              {result.trace_backend ? ` (${result.trace_backend})` : ""}.{" "}
              <Link
                to="/traces"
                search={{ run_id: result.run_id }}
                preload="intent"
              >
                Open in Traces
              </Link>
            </p>
          ) : null}

          <h2>Citations</h2>
          {result.citations.length === 0 ? (
            <p>None (empty on abstain).</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>chunk_id</th>
                  <th>text_ref</th>
                  <th>rank</th>
                </tr>
              </thead>
              <tbody>
                {result.citations.map((row) => (
                  <tr key={row.chunk_id}>
                    <td>
                      <code>{row.chunk_id}</code>
                    </td>
                    <td>
                      <code>{row.text_ref}</code>
                    </td>
                    <td>{row.rank ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <h2>Retrieved chunk ids</h2>
          <p className="muted">
            {result.retrieved_chunk_ids.length === 0
              ? "None."
              : result.retrieved_chunk_ids.join(", ")}
          </p>
        </section>
      ) : null}
    </>
  );
}
