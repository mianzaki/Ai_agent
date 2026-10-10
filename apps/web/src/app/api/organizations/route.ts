import { NextResponse } from "next/server";
import { serverApi } from "@/lib/server-api";
import { ApiError } from "@/lib/contracts";

export async function GET() {
  try {
    return NextResponse.json({ data: await serverApi.organizations(), mode: "connected" });
  } catch (error) {
    const apiError = error instanceof ApiError ? error : new ApiError("API is unavailable.", 502);
    return NextResponse.json({ error: apiError.message, mode: "disconnected" }, { status: apiError.status });
  }
}
