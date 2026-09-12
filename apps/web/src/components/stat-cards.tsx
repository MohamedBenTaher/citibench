import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export type StatItem = {
  label: string;
  value: string;
  hint?: string;
  dense?: boolean;
  title?: string;
};

export function StatCards({ items }: { items: StatItem[] }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {items.map((item) => (
        <Card key={item.label} size="sm">
          <CardHeader className="gap-1">
            <div className="flex items-center gap-1.5">
              <span
                className="h-2.5 w-0.5 bg-foreground/60"
                aria-hidden="true"
              />
              <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
                {item.label}
              </p>
            </div>
            <p
              title={item.title}
              className={cn(
                "font-mono font-semibold tabular-nums text-foreground",
                item.dense
                  ? "text-sm leading-snug tracking-tight sm:text-base"
                  : "text-2xl",
              )}
            >
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
