import { NextRequest, NextResponse } from "next/server";
import { directLocalApi, isSameOrigin } from "@/lib/server-api";

type Context = { params: Promise<{ organizationId: string }> };
export async function GET(_request: NextRequest, { params }: Context) {
  const { organizationId } = await params;
  try {
    const response = await directLocalApi(`/v1/organizations/${encodeURIComponent(organizationId)}/voice-settings`);
    return NextResponse.json(await response.json(), { status: response.status });
  } catch { return NextResponse.json({ error: "The Volvox API could not be reached." }, { status: 502 }); }
}

export async function PUT(request: NextRequest, { params }: Context) {
  if (!isSameOrigin(request)) return NextResponse.json({ error: "Cross-origin requests are not allowed." }, { status: 403 });
  const { organizationId } = await params;
  try {
    const response = await directLocalApi(`/v1/organizations/${encodeURIComponent(organizationId)}/voice-settings`, { method: "PUT", headers: { "content-type": "application/json" }, body: await request.text() });
    return NextResponse.json(await response.json(), { status: response.status });
  } catch { return NextResponse.json({ error: "The Volvox API could not be reached." }, { status: 502 }); }
}
