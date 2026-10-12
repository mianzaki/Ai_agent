import { NextResponse } from "next/server";
import { directLocalApi, serverApi } from "@/lib/server-api";
import { ApiError } from "@/lib/contracts";

export async function GET() {
  if (process.env.NODE_ENV !== "production" && process.env.VOLVOX_LOCAL_DEV === "true") {
    try {
      const response = await directLocalApi("/v1/organizations");
      const data = await response.json();
      return NextResponse.json({ data, mode: "connected" }, { status: response.status });
    } catch { return NextResponse.json({ error: "The local API could not be reached." }, { status: 502 }); }
  }
  try {
    return NextResponse.json({ data: await serverApi.organizations(), mode: "connected" });
  } catch (error) {
    const apiError = error instanceof ApiError ? error : new ApiError("API is unavailable.", 502);
    return NextResponse.json({ error: apiError.message, mode: "disconnected" }, { status: apiError.status });
  }
}
