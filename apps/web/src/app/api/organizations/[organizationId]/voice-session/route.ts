import { NextRequest, NextResponse } from "next/server";
import { ApiError } from "@/lib/contracts";
import { directLocalApi, isSameOrigin, serverApi } from "@/lib/server-api";

type Context = { params: Promise<{ organizationId: string }> };

export async function POST(request: NextRequest, { params }: Context) {
  if (!isSameOrigin(request)) return NextResponse.json({ error: "Cross-origin requests are not allowed." }, { status: 403 });
  try {
    const { organizationId } = await params;
    const body = await request.json() as { agent_id?: unknown };
    if (typeof body.agent_id !== "string" || !/^[0-9a-f-]{36}$/i.test(body.agent_id)) {
      return NextResponse.json({ error: "Choose a saved agent." }, { status: 422 });
    }
    if (process.env.NODE_ENV !== "production" && process.env.VOLVOX_LOCAL_DEV === "true") {
      const response = await directLocalApi(`/v1/organizations/${encodeURIComponent(organizationId)}/voice-session?agent_id=${encodeURIComponent(body.agent_id)}`, { method: "POST" });
      return NextResponse.json(await response.json(), { status: response.status, headers: { "cache-control": "no-store" } });
    }
    return NextResponse.json(await serverApi.voiceSession(organizationId, body.agent_id), { headers: { "cache-control": "no-store" } });
  } catch (error) {
    const apiError = error instanceof ApiError ? error : new ApiError("The local voice service could not be reached.", 502);
    return NextResponse.json({ error: apiError.message }, { status: apiError.status });
  }
}
