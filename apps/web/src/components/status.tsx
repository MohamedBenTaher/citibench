import { ErrorComponent, useRouter } from "@tanstack/react-router";
import type { ErrorComponentProps } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorAlert } from "@/components/error-alert";

export function RoutePending({ label }: { label: string }) {
  return (
    <div className="space-y-3" aria-live="polite">
      <p className="text-sm text-muted-foreground">{label}</p>
      <div className="grid gap-3 sm:grid-cols-3">
        <Skeleton className="h-20" />
        <Skeleton className="h-20" />
        <Skeleton className="h-20" />
      </div>
    </div>
  );
}

export function RouteError({ error }: ErrorComponentProps) {
  const router = useRouter();
  const message = error instanceof Error ? error.message : "request failed";

  return (
    <div className="space-y-3">
      <ErrorAlert message={message} />
      <Button
        type="button"
        variant="outline"
        onClick={() => {
          void router.invalidate();
        }}
      >
        Retry
      </Button>
      <ErrorComponent error={error} />
    </div>
  );
}
