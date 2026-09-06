import { createFileRoute } from "@tanstack/react-router";
import { proxyToApi } from "../../lib/api";

export const Route = createFileRoute("/api/metrics")({
  server: {
    handlers: {
      GET: async ({ request }) => {
        const incoming = new URL(request.url);
        const format = incoming.searchParams.get("format");
        const path = format
          ? `/metrics?format=${encodeURIComponent(format)}`
          : "/metrics";
        return proxyToApi(path);
      },
    },
  },
});
