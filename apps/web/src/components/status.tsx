import { ErrorComponent, useRouter } from "@tanstack/react-router";
import type { ErrorComponentProps } from "@tanstack/react-router";

export function RoutePending({ label }: { label: string }) {
  return <p className="muted">{label}</p>;
}

export function RouteError({ error }: ErrorComponentProps) {
  const router = useRouter();
  const message = error instanceof Error ? error.message : "request failed";

  return (
    <div>
      <p className="error">{message}</p>
      <p className="actions">
        <button
          type="button"
          onClick={() => {
            void router.invalidate();
          }}
        >
          Retry
        </button>
      </p>
      <ErrorComponent error={error} />
    </div>
  );
}
