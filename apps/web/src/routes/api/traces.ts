import { createFileRoute } from "@tanstack/react-router";
import { proxyToApi } from "../../lib/api";

export const Route = createFileRoute("/api/traces")({
  server: {
    handlers: {
      GET: async () => proxyToApi("/traces"),
    },
  },
});
