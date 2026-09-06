import { createServerFn } from "@tanstack/react-start";
import { apiJson } from "./api";
import type {
  CorpusStats,
  EvalLatest,
  RedteamLatest,
  RunTrace,
  TraceList,
} from "./types";

export const getCorpusStats = createServerFn({ method: "GET" }).handler(
  async () => apiJson<CorpusStats>("/corpus/stats"),
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
