import { createFileRoute } from "@tanstack/react-router";
import { proxyToApi } from "../../../lib/api";

export const Route = createFileRoute("/api/traces/$runId")({
  server: {
    handlers: {
      GET: async ({ params }) => proxyToApi(`/traces/${encodeURIComponent(params.runId)}`),
    },
  },
});
