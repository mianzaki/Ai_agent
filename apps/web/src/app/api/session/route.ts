import { NextResponse } from "next/server";

export async function GET() {
  if (process.env.NODE_ENV !== "production" && process.env.VOLVOX_LOCAL_DEV === "true") {
    return NextResponse.json({ authenticated: true, email: "local@volvox.test", preview: false });
  }
  return NextResponse.json({ authenticated: false, preview: true });
}
