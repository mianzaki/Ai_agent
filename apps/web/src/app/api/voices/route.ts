import { NextResponse } from "next/server";
import { directLocalApi } from "@/lib/server-api";

export async function GET() {
  try {
    const response = await directLocalApi("/v1/voices");
    return NextResponse.json(await response.json(), { status: response.status });
  } catch {
    return NextResponse.json({ error: "The Volvox API could not be reached." }, { status: 502 });
  }
}
