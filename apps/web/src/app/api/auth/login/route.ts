import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  const origin = request.headers.get("origin");
  if (origin && origin !== request.nextUrl.origin) {
    return NextResponse.json({ error: "Cross-origin requests are not allowed." }, { status: 403 });
  }
  const baseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL?.replace(/\/$/, "");
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!baseUrl || !anonKey) return NextResponse.json({ error: "Supabase is not configured." }, { status: 503 });
  const body = await request.json().catch(() => null) as { email?: string; password?: string } | null;
  if (!body?.email || !body.password) return NextResponse.json({ error: "Email and password are required." }, { status: 400 });
  try {
    const response = await fetch(`${baseUrl}/auth/v1/token?grant_type=password`, {
      method: "POST",
      headers: { apikey: anonKey, "content-type": "application/json" },
      body: JSON.stringify({ email: body.email, password: body.password }),
      cache: "no-store",
      signal: AbortSignal.timeout(6000),
    });
    const result = await response.json() as { access_token?: string; expires_in?: number; error_description?: string; msg?: string };
    if (!response.ok || !result.access_token) {
      return NextResponse.json({ error: "Supabase sign-in failed. Check your credentials and project settings." }, { status: 401 });
    }
    const reply = NextResponse.json({ authenticated: true });
    reply.cookies.set("volvox_access_token", result.access_token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      path: "/",
      maxAge: Math.max(60, result.expires_in ?? 3600),
    });
    return reply;
  } catch {
    return NextResponse.json({ error: "Supabase could not be reached." }, { status: 502 });
  }
}
