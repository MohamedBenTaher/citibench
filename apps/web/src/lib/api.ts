export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function apiBase(): string {
  const fromEnv =
    process.env.API_URL || process.env.VITE_API_URL || "http://127.0.0.1:8000";
  return fromEnv.replace(/\/$/, "");
}

export async function proxyToApi(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  try {
    const response = await fetch(`${apiBase()}${path}`, {
      ...init,
      cache: "no-store",
    });
    const body = await response.text();
    return new Response(body, {
      status: response.status,
      headers: {
        "content-type":
          response.headers.get("content-type") || "application/json",
      },
    });
  } catch (error) {
    const detail = error instanceof Error ? error.message : "api unreachable";
    return Response.json({ detail }, { status: 503 });
  }
}

export async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiBase()}${path}`, {
      ...init,
      cache: "no-store",
    });
  } catch (error) {
    const detail = error instanceof Error ? error.message : "api unreachable";
    throw new ApiError(detail, 503);
  }

  const data = (await response.json()) as T & { detail?: string };
  if (!response.ok) {
    throw new ApiError(data.detail || `HTTP ${response.status}`, response.status);
  }
  return data;
}
