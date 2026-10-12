import { NextRequest, NextResponse } from "next/server";
import { ApiError } from "@/lib/contracts";
import { directLocalApi, isSameOrigin, serverApi } from "@/lib/server-api";

type Context = { params: Promise<{ organizationId: string; agentId: string }> };

export async function PATCH(request: NextRequest, { params }: Context) {
  if (!isSameOrigin(request)) {
    return NextResponse.json({ error: "Cross-origin requests are not allowed." }, { status: 403 });
  }
  try {
    const { organizationId, agentId } = await params;
    if (process.env.NODE_ENV !== "production" && process.env.VOLVOX_LOCAL_DEV === "true") {
      const response = await directLocalApi(`/v1/organizations/${encodeURIComponent(organizationId)}/agents/${encodeURIComponent(agentId)}`, { method: "PATCH", body: await request.text() });
      return NextResponse.json({ data: await response.json() }, { status: response.status });
    }
    return NextResponse.json({ data: await serverApi.updateAgent(organizationId, agentId, await request.json()) });
  } catch (error) {
    const apiError = error instanceof ApiError ? error : new ApiError("Could not update agent.", 400);
    return NextResponse.json({ error: apiError.message }, { status: apiError.status });
  }
}

export async function DELETE(request: NextRequest, { params }: Context) {
  if (!isSameOrigin(request)) {
    return NextResponse.json({ error: "Cross-origin requests are not allowed." }, { status: 403 });
  }
  try {
    const { organizationId, agentId } = await params;
    if (process.env.NODE_ENV !== "production" && process.env.VOLVOX_LOCAL_DEV === "true") {
      const response = await directLocalApi(`/v1/organizations/${encodeURIComponent(organizationId)}/agents/${encodeURIComponent(agentId)}`, { method: "DELETE" });
      return new NextResponse(null, { status: response.status });
    }
    await serverApi.deleteAgent(organizationId, agentId);
    return new NextResponse(null, { status: 204 });
  } catch (error) {
    const apiError = error instanceof ApiError ? error : new ApiError("Could not delete agent.", 400);
    return NextResponse.json({ error: apiError.message }, { status: apiError.status });
  }
}
