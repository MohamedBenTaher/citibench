import { Badge } from "@/components/ui/badge";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDiff, formatScore } from "@/lib/format";
import type { MetricName, Metrics } from "@/lib/types";

const METRICS: { key: MetricName; gated: boolean }[] = [
  { key: "faithfulness", gated: true },
  { key: "context_precision", gated: false },
  { key: "answer_relevancy", gated: false },
];

function metricLabel(key: MetricName): string {
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

function gateState(
  score: number | null | undefined,
  threshold: number,
): "pass" | "fail" | "unknown" {
  if (score === null || score === undefined || Number.isNaN(score)) {
    return "unknown";
  }
  return score >= threshold ? "pass" : "fail";
}

export function MetricStrip({
  metrics,
  diff,
  previous,
  threshold,
}: {
  metrics: Metrics | null;
  diff: Metrics | null;
  previous: Metrics | null;
  threshold: number;
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {METRICS.map((metric) => {
        const score = metrics?.[metric.key];
        const gate = metric.gated ? gateState(score, threshold) : null;
        return (
          <Card
            key={metric.key}
            size="sm"
            className={gate === "fail" ? "ring-destructive/40" : undefined}
          >
            <CardHeader>
              <CardDescription>{metricLabel(metric.key)}</CardDescription>
              <CardTitle className="font-mono text-2xl tabular-nums">
                {formatScore(score)}
              </CardTitle>
              {gate ? (
                <CardAction>
                  <Badge variant={gate === "fail" ? "destructive" : gate === "pass" ? "secondary" : "outline"}>
                    {gate === "unknown" ? "—" : gate}
                  </Badge>
                </CardAction>
              ) : (
                <CardAction>
                  <Badge variant="outline">logged</Badge>
                </CardAction>
              )}
            </CardHeader>
            <CardContent className="space-y-1">
              <p className="text-xs text-muted-foreground">
                {metric.gated
                  ? `CI gate ≥ ${formatScore(threshold)}`
                  : "Logged only — does not gate CI"}
              </p>
              <p className="text-xs tabular-nums text-muted-foreground">
                vs previous {formatDiff(diff?.[metric.key])}
                {previous
                  ? ` (${formatScore(previous[metric.key])})`
                  : " (no previous run)"}
              </p>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
