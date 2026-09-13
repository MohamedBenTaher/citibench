export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

export type FailureRow = {
  id: string;
  title: string;
  source_url: string;
  error: string;
};

export type IngestBody = {
  wipe?: boolean;
  simulate_failure_id?: string;
};

export type CorpusStats = {
  doc_count: number;
  page_count: number;
  chunk_count: number;
  user_doc_count?: number;
  last_index_time: string | null;
  failures: FailureRow[];
  detail?: string;
};

export type Citation = {
  chunk_id: string;
  doc_id: string;
  text_ref: string;
  score: number | null;
  rank: number | null;
  title?: string | null;
  source?: string | null;
  product?: string | null;
  doc_type?: string | null;
  version?: string | null;
  license?: string | null;
  page?: number | null;
  section?: string | null;
  url?: string | null;
};

export type DocumentRow = {
  id: string;
  title: string;
  source_url: string;
  product: string | null;
  doc_type: string | null;
  source: string | null;
  origin: string;
  license: string;
  status: string;
  error: string | null;
  page_count: number;
  chunk_count: number;
  indexed_at: string | null;
  version: string | null;
};

export type DocumentList = {
  total: number;
  limit: number;
  offset: number;
  documents: DocumentRow[];
  detail?: string;
};

export type DocumentChunk = {
  id: string;
  doc_id: string;
  chunk_index: number;
  section: string | null;
  page: number | null;
  url: string | null;
  token_count: number;
  preview: string;
  text_ref: string;
};

export type DocumentDetail = {
  document: DocumentRow;
  chunk_total: number;
  limit: number;
  offset: number;
  chunks: DocumentChunk[];
  detail?: string;
};

export type CorpusFacets = {
  products: string[];
  sources: string[];
  doc_types: string[];
  origins: string[];
};

export type CorpusSuggestion = {
  question: string;
  product: string;
  doc_id: string;
};

export type CorpusSuggestions = {
  suggestions: CorpusSuggestion[];
  source?: string;
};

export type CitedChunk = {
  id: string;
  doc_id: string;
  chunk_index: number;
  section: string | null;
  page: number | null;
  url: string | null;
  token_count: number;
  text: string;
  text_ref: string;
  title: string;
  product: string | null;
  source: string | null;
  license: string;
};

export type CostEstimate = {
  prompt_tokens: number;
  completion_tokens: number;
  embed_tokens: number;
  rerank_tokens: number;
  usd_estimate: number;
};

export type GenerateTerminal = "generate" | "abstain";

export type GenerateResult = {
  answer: string;
  abstained: boolean;
  abstain_reason: string | null;
  path: string[];
  terminal: GenerateTerminal;
  citations: Citation[];
  retrieved_chunk_ids: string[];
  latency_ms: number;
  cost: CostEstimate;
  cost_method: string;
  rerank_skipped: boolean;
  model: string;
  run_id?: string;
  langfuse_trace_id?: string | null;
  trace_backend?: "langfuse" | "local";
  detail?: string;
};

export type TraceRow = {
  run_id: string;
  query: string;
  started_at: string;
  finished_at: string;
  abstained: boolean;
  model: string;
  tokens_in: number;
  tokens_out: number;
  latency_ms: number;
  cost: CostEstimate;
  cost_method: string;
  langfuse_trace_id: string | null;
  rerank_skipped: boolean;
  citation_count: number;
  failed: boolean;
};

export type TraceList = {
  langfuse_configured: boolean;
  backend: "langfuse" | "local";
  count: number;
  traces: TraceRow[];
  detail?: string;
};

export type SpanKind = "retrieve" | "rerank" | "generate" | "abstain";
export type SpanStatus = "ok" | "error";

export type Span = {
  span_id: string;
  parent_id: string | null;
  kind: SpanKind;
  started_at: string;
  finished_at: string;
  status: SpanStatus;
  attributes: { [key: string]: JsonValue };
};

export type RunTrace = {
  run_id: string;
  query: string;
  started_at: string;
  finished_at: string;
  spans: Span[];
  citations: Citation[];
  abstained: boolean;
  cost: CostEstimate;
  langfuse_trace_id: string | null;
  rerank_skipped: boolean;
  model: string;
  tokens_in: number;
  tokens_out: number;
  latency_ms: number;
  cost_method: string;
  detail?: string;
};

export type MetricName = "faithfulness" | "context_precision" | "answer_relevancy";
export type AttackType = "injection" | "pii_leak" | "jailbreak";

export type Metrics = {
  faithfulness: number;
  context_precision: number;
  answer_relevancy: number;
};

export type EvalLatest = {
  present?: boolean;
  run_id?: string;
  started_at?: string;
  finished_at?: string;
  mode?: string;
  framework?: string;
  threshold_faithfulness?: number;
  gate_passed?: boolean;
  gate_reason?: string | null;
  metrics: Metrics | null;
  previous: Metrics | null;
  diff: Metrics | null;
  known_bad?: { clean: boolean; rows: { id: string; required_assert_failed: boolean }[] };
  failing_run_ids?: string[];
  detail?: string;
};

export type RedteamCase = {
  id: string;
  question: string;
  expected: string;
  attack_type: AttackType | string | null;
  expect_block: boolean | null;
  tags: string[];
  run_id?: string;
  blocked?: boolean;
  passed?: boolean;
  abstained?: boolean;
};

export type MetricsSnapshot = {
  as_of: string;
  latency_ms: {
    p50: number | null;
    p95: number | null;
    n: number;
    method: string;
  };
  cost_per_1k_queries_usd: {
    usd: number | null;
    n: number;
    method: string;
    cost_method: string;
  };
  faithfulness: {
    value: number | null;
    context_precision: number | null;
    present: boolean;
    mode: string | null;
    source: string | null;
    run_id: string | null;
    split: string | null;
    n_scored: number | null;
    method: string;
  };
  corpus: {
    docs: number | null;
    pages: number | null;
    chunks: number | null;
    source: string;
    measured_under: string | null;
  };
  detail?: string;
};

export type RedteamLatest = {
  present?: boolean;
  split?: string;
  case_count?: number;
  cases: RedteamCase[];
  run?: {
    run_id?: string;
    mode?: string;
    gate_passed?: boolean;
    gate_reason?: string | null;
    passed?: number;
    failed?: number;
    blocked?: number;
    finished_at?: string;
    failing_run_ids?: string[];
  } | null;
  detail?: string;
};
