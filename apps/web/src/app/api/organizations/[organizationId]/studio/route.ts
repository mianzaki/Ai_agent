import { NextRequest, NextResponse } from "next/server";
import { directLocalApi, isSameOrigin } from "@/lib/server-api";

type Context = { params: Promise<{ organizationId: string }> };

async function proxy(request: NextRequest, { params }: Context, path: string, method: string) {
  if (!isSameOrigin(request)) return NextResponse.json({ error: "Cross-origin requests are not allowed." }, { status: 403 });
  const { organizationId } = await params;
  try {
    const response = await directLocalApi(`/v1/organizations/${encodeURIComponent(organizationId)}/${path}`, {
      method,
      headers: method === "GET" ? {} : { "content-type": "application/json" },
      ...(method === "GET" ? {} : { body: await request.text() }),
      cache: "no-store",
      signal: AbortSignal.timeout(path === "speech" ? 55000 : 65000),
    });
    const contentType = response.headers.get("content-type") ?? "application/json";
    return new NextResponse(await response.arrayBuffer(), { status: response.status, headers: { "content-type": contentType, ...(contentType.startsWith("audio/") ? { "cache-control": "no-store" } : {}) } });
  } catch {
    return NextResponse.json({ error: "The Volvox API could not be reached." }, { status: 502 });
  }
}

export const POST = (request: NextRequest, context: Context) => proxy(request, context, "speech", "POST");
