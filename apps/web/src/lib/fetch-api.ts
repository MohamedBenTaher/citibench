import { apiJson } from "./api";
import { clientApiJson } from "./client-api";

/**
 * FastAPI JSON helper that works in both Nitro SSR and the browser.
 *
 * SSR (Compose `web`) uses API_URL → http://api:8000.
 * The browser uses VITE_API_URL → http://localhost:8000.
 *
 * Do not wrap GET loaders in createServerFn: TanStack Start's RPC
 * rejects cross-origin / missing-CSRF GETs with 401/500, which is
 * what broke Corpus stats and the Traces tab.
 */
export async function fetchApiJson<T>(path: string, init?: RequestInit): Promise<T> {
  if (typeof window === "undefined") {
    return apiJson<T>(path, {
      method: init?.method,
      headers: headersToRecord(init?.headers),
      body: bodyToString(init?.body),
    });
  }
  return clientApiJson<T>(path, init);
}

function headersToRecord(headers?: HeadersInit): Record<string, string> | undefined {
  if (!headers) {
    return undefined;
  }
  if (headers instanceof Headers) {
    return Object.fromEntries(headers.entries());
  }
  if (Array.isArray(headers)) {
    return Object.fromEntries(headers);
  }
  return headers;
}

function bodyToString(body: BodyInit | null | undefined): string | undefined {
  if (body == null) {
    return undefined;
  }
  if (typeof body === "string") {
    return body;
  }
  throw new Error("SSR fetchApiJson only accepts a string body");
}
