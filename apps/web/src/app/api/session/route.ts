import { cookies } from "next/headers";
import { NextResponse } from "next/server";

export async function GET() {
  const baseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL?.replace(/\/$/, "");
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  const cookieStore = await cookies();
  const accessToken = cookieStore.get("volvox_access_token")?.value;
  if (!baseUrl || !anonKey || !accessToken) {
    return NextResponse.json({ authenticated: false, preview: true });
  }
  try {
    const response = await fetch(`${baseUrl}/auth/v1/user`, {
      headers: { apikey: anonKey, authorization: `Bearer ${accessToken}` },
      cache: "no-store",
      signal: AbortSignal.timeout(2500),
    });
    if (!response.ok) return NextResponse.json({ authenticated: false, preview: true });
    const user = await response.json() as { id: string; email?: string };
    return NextResponse.json({ authenticated: true, email: user.email ?? "", preview: false });
  } catch {
    return NextResponse.json({ authenticated: false, preview: true });
  }
}
