import { fetchApiJson } from "./fetch-api";
import type {
  CorpusStats,
  EvalLatest,
  RedteamLatest,
  RunTrace,
  TraceList,
} from "./types";

export function getCorpusStats() {
  return fetchApiJson<CorpusStats>("/corpus/stats");
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
