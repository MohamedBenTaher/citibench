import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

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
          <CardHeader>
            <CardDescription>{item.label}</CardDescription>
            <CardTitle className="font-mono text-xl tabular-nums">{item.value}</CardTitle>
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
