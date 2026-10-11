import { Bar, BarChart, CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  type ChartConfig,
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import type { TraceRow } from "@/lib/types";

export type TraceOutcome = "generate" | "abstain" | "failed";

export function traceOutcome(row: Pick<TraceRow, "failed" | "abstained">): TraceOutcome {
  if (row.failed) {
    return "failed";
  }
  if (row.abstained) {
    return "abstain";
  }
  return "generate";
}

const SERIES_CONFIG = {
  latency: { label: "Latency (ms)", color: "var(--color-chart-1)" },
  cost: { label: "Cost (USD)", color: "var(--color-chart-3)" },
} satisfies ChartConfig;

const OUTCOME_CONFIG = {
  generate: { label: "generate", color: "var(--color-chart-2)" },
  abstain: { label: "abstain", color: "var(--color-chart-4)" },
  failed: { label: "failed", color: "var(--color-chart-5)" },
} satisfies ChartConfig;

const MAX_SERIES = 20;

function chronological(rows: TraceRow[]): TraceRow[] {
  return [...rows].sort((a, b) => a.started_at.localeCompare(b.started_at)).slice(-MAX_SERIES);
}

export function TraceCharts({ traces }: { traces: TraceRow[] }) {
  if (traces.length === 0) {
    return null;
  }

  const series = chronological(traces).map((row, index) => ({
    run: row.run_id.slice(0, 8),
    index: index + 1,
    latency: Number(row.latency_ms.toFixed(1)),
    cost: Number(row.cost.usd_estimate.toFixed(6)),
    query: row.query.trim() || "(empty query)",
  }));

  const counts: Record<TraceOutcome, number> = { generate: 0, abstain: 0, failed: 0 };
  for (const row of traces) {
    counts[traceOutcome(row)] += 1;
  }
  const mix = (Object.keys(counts) as TraceOutcome[]).map((outcome) => {
    switch (outcome) {
      case "generate":
      case "abstain":
      case "failed":
        return { outcome, count: counts[outcome], fill: `var(--color-${outcome})` };
      default: {
        const _exhaustive: never = outcome;
        return _exhaustive;
      }
    }
  });

  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Latency and cost</CardTitle>
          <CardDescription>
            Last {series.length} run{series.length === 1 ? "" : "s"} in start order. Scores are from
            stored RunTraces, not estimates.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ChartContainer config={SERIES_CONFIG} className="aspect-video w-full">
            <LineChart data={series} margin={{ left: 8, right: 8, top: 8 }}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="run" tickLine={false} axisLine={false} />
              <YAxis
                yAxisId="latency"
                tickLine={false}
                axisLine={false}
                width={40}
                tickFormatter={(value: number) => `${value}`}
              />
              <YAxis
                yAxisId="cost"
                orientation="right"
                tickLine={false}
                axisLine={false}
                width={48}
                tickFormatter={(value: number) => `$${value}`}
              />
              <ChartTooltip
                content={
                  <ChartTooltipContent
                    labelFormatter={(_, payload) => {
                      const row = payload[0];
                      const query =
                        row && typeof row.payload?.query === "string" ? row.payload.query : "";
                      return query || "run";
                    }}
                    formatter={(value, name) => {
                      const key = String(name);
                      if (key === "cost" && typeof value === "number") {
                        return <span className="font-mono tabular-nums">${value.toFixed(6)}</span>;
                      }
                      if (key === "latency" && typeof value === "number") {
                        return (
                          <span className="font-mono tabular-nums">{value.toFixed(1)} ms</span>
                        );
                      }
                      return <span>{String(value)}</span>;
                    }}
                  />
                }
              />
              <ChartLegend content={<ChartLegendContent />} />
              <Line
                yAxisId="latency"
                type="monotone"
                dataKey="latency"
                stroke="var(--color-latency)"
                strokeWidth={2}
                dot={{ r: 2 }}
                isAnimationActive={false}
              />
              <Line
                yAxisId="cost"
                type="monotone"
                dataKey="cost"
                stroke="var(--color-cost)"
                strokeWidth={2}
                dot={{ r: 2 }}
                isAnimationActive={false}
              />
            </LineChart>
          </ChartContainer>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Outcome mix</CardTitle>
          <CardDescription>
            generate / abstain / failed across {traces.length} listed run
            {traces.length === 1 ? "" : "s"}.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ChartContainer config={OUTCOME_CONFIG} className="aspect-video w-full">
            <BarChart data={mix} margin={{ left: 8, right: 8, top: 8 }}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="outcome" tickLine={false} axisLine={false} />
              <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={28} />
              <ChartTooltip content={<ChartTooltipContent hideLabel />} />
              <Bar dataKey="count" radius={4} isAnimationActive={false} />
            </BarChart>
          </ChartContainer>
        </CardContent>
      </Card>
    </div>
  );
}
