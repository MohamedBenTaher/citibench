import * as http from "node:http";
import * as https from "node:https";

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

type RequestBody = string | Buffer | undefined;

function requestApi(
  path: string,
  init?: { method?: string; headers?: Record<string, string>; body?: RequestBody },
): Promise<{ status: number; contentType: string; body: string }> {
  const url = new URL(path, `${apiBase()}/`);
  const lib = url.protocol === "https:" ? https : http;
  const method = init?.method || "GET";
  const headers = { ...(init?.headers ?? {}) };

  return new Promise((resolve, reject) => {
    const req = lib.request(
      {
        protocol: url.protocol,
        hostname: url.hostname,
        port: url.port,
        path: `${url.pathname}${url.search}`,
        method,
        headers,
      },
      (res) => {
        const chunks: Buffer[] = [];
        res.on("data", (chunk) => {
          chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
        });
        res.on("end", () => {
          resolve({
            status: res.statusCode || 500,
            contentType: String(res.headers["content-type"] || "application/json"),
            body: Buffer.concat(chunks).toString("utf8"),
          });
        });
      },
    );
    req.on("error", (error) => {
      reject(error);
    });
    if (init?.body) {
      req.write(init.body);
    }
    req.end();
  });
}

export async function proxyToApi(
  path: string,
  init?: { method?: string; headers?: Record<string, string>; body?: string },
): Promise<Response> {
  try {
    const result = await requestApi(path, init);
    return new Response(result.body, {
      status: result.status,
      headers: { "content-type": result.contentType },
    });
  } catch (error) {
    const detail = error instanceof Error ? error.message : "api unreachable";
    return Response.json({ detail }, { status: 503 });
  }
}

export async function apiJson<T>(
  path: string,
  init?: { method?: string; headers?: Record<string, string>; body?: string },
): Promise<T> {
  let result: { status: number; body: string };
  try {
    result = await requestApi(path, init);
  } catch (error) {
    const detail = error instanceof Error ? error.message : "api unreachable";
    throw new ApiError(detail, 503);
  }

  let data: T & { detail?: string };
  try {
    data = JSON.parse(result.body) as T & { detail?: string };
  } catch {
    throw new ApiError(result.body || `HTTP ${result.status}`, result.status);
  }
  if (result.status < 200 || result.status >= 300) {
    throw new ApiError(data.detail || `HTTP ${result.status}`, result.status);
  }
  return data;
}
