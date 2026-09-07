import { Card, CardContent, CardHeader } from "@/components/ui/card";

export type StatItem = {
  label: string;
  value: string;
  hint?: string;
};

export function StatCards({ items }: { items: StatItem[] }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {items.map((item) => (
        <Card key={item.label} size="sm">
          <CardHeader className="gap-1">
            <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              {item.label}
            </p>
            <p className="font-mono text-2xl font-semibold tabular-nums text-foreground">
              {item.value}
            </p>
          </CardHeader>
          {item.hint ? (
            <CardContent>
              <p className="text-xs text-muted-foreground">{item.hint}</p>
            </CardContent>
          ) : null}
        </Card>
      ))}
    </div>
  );
}
