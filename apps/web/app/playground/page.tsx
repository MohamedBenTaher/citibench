"use client";

import { useState, type FormEvent } from "react";

type Citation = {
  chunk_id: string;
  doc_id: string;
  text_ref: string;
  score: number | null;
  rank: number | null;
};

type CostEstimate = {
  prompt_tokens: number;
  completion_tokens: number;
  embed_tokens: number;
  rerank_tokens: number;
  usd_estimate: number;
};

type GenerateResult = {
  answer: string;
  abstained: boolean;
  abstain_reason: string | null;
  path: string[];
  terminal: "generate" | "abstain";
  citations: Citation[];
  retrieved_chunk_ids: string[];
  latency_ms: number;
  cost: CostEstimate;
  cost_method: string;
  rerank_skipped: boolean;
  model: string;
  detail?: string;
};

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

export default function PlaygroundPage() {
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GenerateResult | null>(null);

  async function onAsk(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/generate", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ query }),
      });
      const data = (await response.json()) as GenerateResult;
      if (!response.ok) {
        throw new Error(data.detail || `generate HTTP ${response.status}`);
      }
      setResult(data);
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

      <form className="ask" onSubmit={onAsk}>
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
