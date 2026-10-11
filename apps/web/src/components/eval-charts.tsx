import { Bar, BarChart, CartesianGrid, ReferenceLine, XAxis, YAxis } from "recharts";
import {
  type ChartConfig,
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import type { AttackType, EvalLatest, MetricName, RedteamCase } from "@/lib/types";

const METRIC_KEYS: MetricName[] = ["faithfulness", "context_precision", "answer_relevancy"];

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

function attackKey(value: AttackType | string | null): string {
  switch (value) {
    case "injection":
    case "pii_leak":
    case "jailbreak":
      return value;
    case null:
      return "unspecified";
    default:
      return value;
  }
}

export type RedteamBucket = "blocked" | "allowed" | "leaked" | "not_run";

export function redteamBucket(row: RedteamCase): RedteamBucket {
  if (row.passed === true) {
    return row.blocked ? "blocked" : "allowed";
  }
  if (row.passed === false) {
    return "leaked";
  }
  return "not_run";
}

const METRIC_CONFIG = {
  current: { label: "This run", color: "var(--color-chart-1)" },
  previous: { label: "Previous", color: "var(--color-chart-3)" },
} satisfies ChartConfig;

const REDTEAM_CONFIG = {
  blocked: { label: "blocked", color: "var(--color-chart-2)" },
  allowed: { label: "allowed (ok)", color: "var(--color-chart-1)" },
  leaked: { label: "leaked", color: "var(--color-chart-5)" },
  not_run: { label: "not run", color: "var(--color-chart-4)" },
} satisfies ChartConfig;

export function EvalMetricChart({ latest }: { latest: EvalLatest | null }) {
  const metrics = latest?.metrics;
  if (!latest?.present || !metrics) {
    return (
      <p className="text-sm text-muted-foreground">
        No eval run yet — charts stay empty rather than inventing scores.
      </p>
    );
  }

  const gate = latest.threshold_faithfulness ?? 0.7;
  const data = METRIC_KEYS.map((key) => ({
    metric: metricLabel(key),
    current: metrics[key],
    previous: latest.previous ? latest.previous[key] : null,
  }));

  return (
    <div className="space-y-2">
      <p className="text-sm text-muted-foreground">
        The faithfulness gate is {gate.toFixed(3)}. Context precision and answer relevancy are
        logged alongside and do not gate.
      </p>
      <ChartContainer config={METRIC_CONFIG} className="aspect-video w-full">
        <BarChart data={data} margin={{ left: 8, right: 8, top: 8 }}>
          <CartesianGrid vertical={false} />
          <XAxis dataKey="metric" tickLine={false} axisLine={false} />
          <YAxis domain={[0, 1]} tickLine={false} axisLine={false} width={32} />
          <ChartTooltip content={<ChartTooltipContent />} />
          <ChartLegend content={<ChartLegendContent />} />
          <ReferenceLine
            y={gate}
            stroke="var(--color-chart-5)"
            strokeDasharray="4 4"
            label={{ value: `gate ${gate.toFixed(2)}`, position: "right", fontSize: 10 }}
          />
          <Bar dataKey="current" fill="var(--color-current)" radius={4} isAnimationActive={false} />
          <Bar
            dataKey="previous"
            fill="var(--color-previous)"
            radius={4}
            isAnimationActive={false}
          />
        </BarChart>
      </ChartContainer>
    </div>
  );
}

export function RedteamChart({ cases }: { cases: RedteamCase[] }) {
  if (cases.length === 0) {
    return null;
  }

  const empty: Record<RedteamBucket, number> = {
    blocked: 0,
    allowed: 0,
    leaked: 0,
    not_run: 0,
  };
  const byAttack = new Map<string, Record<RedteamBucket, number>>();
  for (const row of cases) {
    const key = attackKey(row.attack_type);
    const current = byAttack.get(key) ?? { ...empty };
    current[redteamBucket(row)] += 1;
    byAttack.set(key, current);
  }
  const data = [...byAttack.entries()].map(([attack, counts]) => ({
    attack,
    ...counts,
  }));
  const ran = cases.some((row) => row.passed === true || row.passed === false);

  return (
    <div className="space-y-2">
      <p className="text-sm text-muted-foreground">
        {ran
          ? "Blocked, allowed, and leaked from the last run."
          : "Not run yet — cases stay on “not run” until a run completes."}
      </p>
      <ChartContainer config={REDTEAM_CONFIG} className="aspect-video w-full">
        <BarChart data={data} margin={{ left: 8, right: 8, top: 8 }}>
          <CartesianGrid vertical={false} />
          <XAxis dataKey="attack" tickLine={false} axisLine={false} />
          <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={28} />
          <ChartTooltip content={<ChartTooltipContent />} />
          <ChartLegend content={<ChartLegendContent />} />
          <Bar
            dataKey="blocked"
            stackId="a"
            fill="var(--color-blocked)"
            radius={0}
            isAnimationActive={false}
          />
          <Bar
            dataKey="allowed"
            stackId="a"
            fill="var(--color-allowed)"
            radius={0}
            isAnimationActive={false}
          />
          <Bar
            dataKey="leaked"
            stackId="a"
            fill="var(--color-leaked)"
            radius={0}
            isAnimationActive={false}
          />
          <Bar
            dataKey="not_run"
            stackId="a"
            fill="var(--color-not_run)"
            radius={[4, 4, 0, 0]}
            isAnimationActive={false}
          />
        </BarChart>
      </ChartContainer>
    </div>
  );
}
