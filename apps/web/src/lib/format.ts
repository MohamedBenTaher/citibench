import type { MetricName } from "./types";

/** Format a nullable number for display; `empty` is the placeholder for a missing value. */
export function formatNumber(value: number | null | undefined, digits = 3, empty = "—"): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return empty;
  }
  return value.toFixed(digits);
}

export function metricLabel(key: MetricName): string {
  switch (key) {
    case "faithfulness":
      return "Faithfulness";
    case "context_precision":
      return "Context precision";
    case "answer_relevancy":
      return "Answer relevancy";
    default: {
      const _exhaustive: never = key;
      return _exhaustive;
    }
  }
}
