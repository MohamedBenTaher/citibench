import { createFileRoute } from "@tanstack/react-router";
import { proxyToApi } from "../../../lib/api";

export const Route = createFileRoute("/api/corpus/stats")({
  server: {
    handlers: {
      GET: async () => proxyToApi("/corpus/stats"),
    },
  },
});
