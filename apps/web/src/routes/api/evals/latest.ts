import { createFileRoute } from "@tanstack/react-router";
import { proxyToApi } from "../../../lib/api";

export const Route = createFileRoute("/api/evals/latest")({
  server: {
    handlers: {
      GET: async () => proxyToApi("/evals/latest"),
    },
  },
});
