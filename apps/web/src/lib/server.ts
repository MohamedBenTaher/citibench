import { createServerFn } from "@tanstack/react-start";
import { apiJson } from "./api";
import type {
  CorpusStats,
  EvalLatest,
  GenerateResult,
  RedteamLatest,
  RunTrace,
  TraceList,
} from "./types";

export const getCorpusStats = createServerFn({ method: "GET" }).handler(
  async () => apiJson<CorpusStats>("/corpus/stats"),
);

export type IngestBody = {
  wipe?: boolean;
  simulate_failure_id?: string;
};

export const postIngest = createServerFn({ method: "POST" })
  .validator((body: IngestBody) => body)
  .handler(async ({ data }) =>
    apiJson<CorpusStats>("/ingest", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(data ?? {}),
    }),
  );

export const postGenerate = createServerFn({ method: "POST" })
  .validator((body: { query: string }) => body)
  .handler(async ({ data }) =>
    apiJson<GenerateResult>("/generate", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ query: data.query }),
    }),
  );

export const getTraces = createServerFn({ method: "GET" }).handler(async () =>
  apiJson<TraceList>("/traces"),
);

export const getTrace = createServerFn({ method: "GET" })
  .validator((runId: string) => runId)
  .handler(async ({ data }) =>
    apiJson<RunTrace>(`/traces/${encodeURIComponent(data)}`),
  );

export const getEvalLatest = createServerFn({ method: "GET" }).handler(
  async () => apiJson<EvalLatest>("/evals/latest"),
);

export const getRedteamLatest = createServerFn({ method: "GET" }).handler(
  async () => apiJson<RedteamLatest>("/evals/redteam"),
);
