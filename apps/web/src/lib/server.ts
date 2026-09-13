import { fetchApiJson } from "./fetch-api";
import type {
  CitedChunk,
  CorpusFacets,
  CorpusStats,
  DocumentDetail,
  DocumentList,
  EvalLatest,
  MetricsSnapshot,
  RedteamLatest,
  RunTrace,
  TraceList,
} from "./types";

function withQuery(
  base: string,
  params: Record<string, string | number | undefined>,
): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === "") continue;
    search.set(key, String(value));
  }
  const suffix = search.toString();
  return suffix ? `${base}?${suffix}` : base;
}

export function getMetrics() {
  return fetchApiJson<MetricsSnapshot>("/metrics");
}

export function getCorpusStats() {
  return fetchApiJson<CorpusStats>("/corpus/stats");
}

export function getCorpusFacets() {
  return fetchApiJson<CorpusFacets>("/corpus/facets");
}

export function getCorpusDocuments(
  params: Record<string, string | number | undefined> = {},
) {
  return fetchApiJson<DocumentList>(withQuery("/corpus/documents", params));
}

export function getCorpusDocument(
  docId: string,
  params: Record<string, string | number | undefined> = {},
) {
  return fetchApiJson<DocumentDetail>(
    withQuery(`/corpus/documents/${encodeURIComponent(docId)}`, params),
  );
}

export function getCitedChunks(ids: string[]) {
  if (ids.length === 0) {
    return Promise.resolve({ chunks: [] as CitedChunk[] });
  }
  return fetchApiJson<{ chunks: CitedChunk[] }>(
    withQuery("/corpus/chunks", { ids: ids.slice(0, 24).join(",") }),
  );
}

export function getTraces() {
  return fetchApiJson<TraceList>("/traces");
}

export function getTrace(runId: string) {
  return fetchApiJson<RunTrace>(`/traces/${encodeURIComponent(runId)}`);
}

export function getEvalLatest() {
  return fetchApiJson<EvalLatest>("/evals/latest");
}

export function getRedteamLatest() {
  return fetchApiJson<RedteamLatest>("/evals/redteam");
}
