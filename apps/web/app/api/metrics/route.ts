const API_URL = process.env.API_URL || "http://127.0.0.1:8000";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const incoming = new URL(request.url);
  const target = new URL("/metrics", API_URL);
  const format = incoming.searchParams.get("format");
  if (format) {
    target.searchParams.set("format", format);
  }
  try {
    const response = await fetch(target, { cache: "no-store" });
    const body = await response.text();
    return new Response(body, {
      status: response.status,
      headers: { "content-type": response.headers.get("content-type") || "application/json" },
    });
  } catch (error) {
    const detail = error instanceof Error ? error.message : "api unreachable";
    return Response.json({ detail }, { status: 503 });
  }
}
