import { NextRequest, NextResponse } from "next/server";
import { ApiError } from "@/lib/contracts";
import { directLocalApi, isSameOrigin, serverApi } from "@/lib/server-api";

type Context = { params: Promise<{ organizationId: string }> };

export async function GET(_request: NextRequest, { params }: Context) {
  try {
    const { organizationId } = await params;
    if (process.env.NODE_ENV !== "production" && process.env.VOLVOX_LOCAL_DEV === "true") {
      const response = await directLocalApi(`/v1/organizations/${encodeURIComponent(organizationId)}/agents`);
      const data = await response.json();
      return NextResponse.json({ data, mode: "connected" }, { status: response.status });
    }
    return NextResponse.json({ data: await serverApi.agents(organizationId), mode: "connected" });
  } catch (error) {
    const apiError = error instanceof ApiError ? error : new ApiError("API is unavailable.", 502);
    return NextResponse.json({ error: apiError.message }, { status: apiError.status });
  }
}

export async function POST(request: NextRequest, { params }: Context) {
  if (!isSameOrigin(request)) {
    return NextResponse.json({ error: "Cross-origin requests are not allowed." }, { status: 403 });
  }
  try {
    const { organizationId } = await params;
    const body = await request.json();
    if (process.env.NODE_ENV !== "production" && process.env.VOLVOX_LOCAL_DEV === "true") {
      const response = await directLocalApi(`/v1/organizations/${encodeURIComponent(organizationId)}/agents`, { method: "POST", body: JSON.stringify(body) });
      return NextResponse.json({ data: await response.json(), mode: "connected" }, { status: response.status });
    }
    const agent = await serverApi.createAgent(organizationId, body);
    return NextResponse.json({ data: agent, mode: "connected" }, { status: 201 });
  } catch (error) {
    const apiError = error instanceof ApiError ? error : new ApiError("Could not create agent.", 400);
    return NextResponse.json({ error: apiError.message }, { status: apiError.status });
  }
}
