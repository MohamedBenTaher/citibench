import { createFileRoute } from "@tanstack/react-router";
import { proxyToApi } from "../../lib/api";

export const Route = createFileRoute("/api/ingest")({
  server: {
    handlers: {
      POST: async ({ request }) => {
        const incoming = await request.text();
        return proxyToApi("/ingest", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: incoming || "{}",
        });
      },
    },
  },
});
