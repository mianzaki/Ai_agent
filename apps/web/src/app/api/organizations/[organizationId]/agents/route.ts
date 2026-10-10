import { NextRequest, NextResponse } from "next/server";
import { ApiError } from "@/lib/contracts";
import { serverApi } from "@/lib/server-api";

type Context = { params: Promise<{ organizationId: string }> };

export async function GET(_request: NextRequest, { params }: Context) {
  try {
    const { organizationId } = await params;
    return NextResponse.json({ data: await serverApi.agents(organizationId), mode: "connected" });
  } catch (error) {
    const apiError = error instanceof ApiError ? error : new ApiError("API is unavailable.", 502);
    return NextResponse.json({ error: apiError.message }, { status: apiError.status });
  }
}

export async function POST(request: NextRequest, { params }: Context) {
  const origin = request.headers.get("origin");
  if (origin && origin !== request.nextUrl.origin) {
    return NextResponse.json({ error: "Cross-origin requests are not allowed." }, { status: 403 });
  }
  try {
    const { organizationId } = await params;
    const body = await request.json();
    const agent = await serverApi.createAgent(organizationId, body);
    return NextResponse.json({ data: agent, mode: "connected" }, { status: 201 });
  } catch (error) {
    const apiError = error instanceof ApiError ? error : new ApiError("Could not create agent.", 400);
    return NextResponse.json({ error: apiError.message }, { status: apiError.status });
  }
}
