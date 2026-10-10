import { NextResponse } from "next/server";
import { cookies } from "next/headers";

export async function GET() {
  const apiUrl = process.env.VOLVOX_API_URL;
  const supabaseConfigured = Boolean(process.env.NEXT_PUBLIC_SUPABASE_URL && process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY);
  const cookieStore = await cookies();
  const token = cookieStore.get("volvox_access_token")?.value;
  let api: "connected" | "unavailable" | "not_configured" = "not_configured";
  let database: "connected" | "unavailable" | "not_configured" = "not_configured";
  let apiAuthenticated: boolean | null = null;
  if (apiUrl) {
    try {
      const response = await fetch(`${apiUrl.replace(/\/$/, "")}/health/ready`, { cache: "no-store", signal: AbortSignal.timeout(1800) });
      api = response.ok ? "connected" : "unavailable";
      database = response.ok ? "connected" : "unavailable";
    } catch {
      api = "unavailable";
      database = "unavailable";
    }
    if (api === "connected" && token) {
      try {
        const response = await fetch(`${apiUrl.replace(/\/$/, "")}/v1/organizations`, {
          headers: { authorization: `Bearer ${token}` },
          cache: "no-store",
          signal: AbortSignal.timeout(1800),
        });
        apiAuthenticated = response.ok;
      } catch {
        apiAuthenticated = false;
      }
    }
  }
  let supabase: "connected" | "unavailable" | "not_configured" = "not_configured";
  if (supabaseConfigured && token) {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_SUPABASE_URL!.replace(/\/$/, "")}/auth/v1/user`, {
        headers: { apikey: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!, authorization: `Bearer ${token}` },
        cache: "no-store",
        signal: AbortSignal.timeout(1800),
      });
      supabase = response.ok ? "connected" : "unavailable";
    } catch {
      supabase = "unavailable";
    }
  }
  return NextResponse.json({ api, database, supabase, apiAuthenticated, voice: "not_configured", preview: api !== "connected" || supabase !== "connected" || !apiAuthenticated });
}
