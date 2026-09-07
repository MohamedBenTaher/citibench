import { Link } from "@tanstack/react-router";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function TraceLink({
  runId,
  children,
}: {
  runId: string;
  children?: string;
}) {
  return (
    <Link
      to="/traces"
      search={{ run_id: runId }}
      preload="intent"
      className={cn(buttonVariants({ variant: "link" }), "h-auto px-0")}
    >
      {children ?? "trace"}
    </Link>
  );
}
