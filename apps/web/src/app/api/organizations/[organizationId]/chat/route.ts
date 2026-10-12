import { NextRequest, NextResponse } from "next/server";
import { directLocalApi, isSameOrigin } from "@/lib/server-api";

type Context = { params: Promise<{ organizationId: string }> };
export async function POST(request: NextRequest, { params }: Context) {
  if (!isSameOrigin(request)) return NextResponse.json({ error: "Cross-origin requests are not allowed." }, { status: 403 });
  const { organizationId } = await params;
  try {
    const response = await directLocalApi(`/v1/organizations/${encodeURIComponent(organizationId)}/chat`, { method: "POST", headers: { "content-type": "application/json" }, body: await request.text(), signal: AbortSignal.timeout(65000) });
    return NextResponse.json(await response.json(), { status: response.status });
  } catch {
    return NextResponse.json({ error: "The local chat service could not be reached." }, { status: 502 });
  }
}
