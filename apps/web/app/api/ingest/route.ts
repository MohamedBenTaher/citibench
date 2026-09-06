const API_URL = process.env.API_URL || "http://127.0.0.1:8000";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const incoming = await request.text();
  try {
    const response = await fetch(`${API_URL}/ingest`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: incoming || "{}",
      cache: "no-store",
    });
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
