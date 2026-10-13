import { ApiError, formatApiDetail } from "./errors";

export function publicApiBase(): string {
  const fromEnv = import.meta.env.VITE_API_URL || "http://localhost:8000";
  return fromEnv.replace(/\/$/, "");
}

export async function clientApiJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${publicApiBase()}${path}`, {
      ...init,
      cache: "no-store",
      // The API lives on its own hostname, and in production it sits behind an
      // edge auth gate (e.g. Cloudflare Access) that identifies the browser by
      // cookie. Without "include" the browser strips cookies from this
      // cross-origin request, the gate answers with a login redirect, and the
      // call surfaces as a generic failure. The API's CORS must set
      // allow_credentials=True for this to be honoured.
      credentials: init?.credentials ?? "include",
    });
  } catch (error) {
    const detail = error instanceof Error ? error.message : "api unreachable";
    throw new ApiError(detail, 503);
  }

  let data: T & { detail?: unknown };
  try {
    data = (await response.json()) as T & { detail?: unknown };
  } catch {
    throw new ApiError(`HTTP ${response.status}`, response.status);
  }
  if (!response.ok) {
    throw new ApiError(formatApiDetail(data.detail) ?? `HTTP ${response.status}`, response.status);
  }
  return data;
}
