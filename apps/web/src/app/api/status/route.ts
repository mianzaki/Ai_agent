import { NextResponse } from "next/server";
import { directLocalApi } from "@/lib/server-api";

type Services = { api: string; database: string; ollama: string; voice: string; voice_transport: string; supabase: "not_configured" };

export async function GET() {
  const localDevelopment = process.env.NODE_ENV !== "production" && process.env.VOLVOX_LOCAL_DEV === "true";
  const apiUrl = process.env.VOLVOX_API_URL?.replace(/\/$/, "");
  try {
    const response = localDevelopment
      ? await directLocalApi("/health/services", { signal: AbortSignal.timeout(3000) })
      : apiUrl
        ? await fetch(`${apiUrl}/health/services`, { cache: "no-store", signal: AbortSignal.timeout(3000) })
        : null;
    if (!response?.ok) throw new Error("Service status is unavailable.");
    const services = await response.json() as Omit<Services, "supabase">;
    return NextResponse.json({ ...services, supabase: "not_configured", preview: false });
  } catch {
    return NextResponse.json({ api: "unavailable", database: "unavailable", ollama: "unavailable", voice: "unavailable", voice_transport: "unavailable", supabase: "not_configured", preview: true });
  }
}
