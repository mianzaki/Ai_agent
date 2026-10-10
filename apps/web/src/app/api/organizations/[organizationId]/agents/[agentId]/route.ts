import { NextRequest, NextResponse } from "next/server";
import { ApiError } from "@/lib/contracts";
import { serverApi } from "@/lib/server-api";

type Context = { params: Promise<{ organizationId: string; agentId: string }> };

export async function PATCH(request: NextRequest, { params }: Context) {
  const origin = request.headers.get("origin");
  if (origin && origin !== request.nextUrl.origin) {
    return NextResponse.json({ error: "Cross-origin requests are not allowed." }, { status: 403 });
  }
  try {
    const { organizationId, agentId } = await params;
    return NextResponse.json({ data: await serverApi.updateAgent(organizationId, agentId, await request.json()) });
  } catch (error) {
    const apiError = error instanceof ApiError ? error : new ApiError("Could not update agent.", 400);
    return NextResponse.json({ error: apiError.message }, { status: apiError.status });
  }
}

export async function DELETE(request: NextRequest, { params }: Context) {
  const origin = request.headers.get("origin");
  if (origin && origin !== request.nextUrl.origin) {
    return NextResponse.json({ error: "Cross-origin requests are not allowed." }, { status: 403 });
  }
  try {
    const { organizationId, agentId } = await params;
    await serverApi.deleteAgent(organizationId, agentId);
    return new NextResponse(null, { status: 204 });
  } catch (error) {
    const apiError = error instanceof ApiError ? error : new ApiError("Could not delete agent.", 400);
    return NextResponse.json({ error: apiError.message }, { status: apiError.status });
  }
}
