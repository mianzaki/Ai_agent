import "server-only";

import type { NextRequest } from "next/server";
import { cookies } from "next/headers";
import type { Agent, AgentCreate, AgentUpdate, Organization } from "./contracts";
import { ApiError } from "./contracts";

const API_URL = process.env.VOLVOX_API_URL?.replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (!API_URL) throw new ApiError("VOLVOX_API_URL is not configured.", 503);
  const cookieStore = await cookies();
  const token = cookieStore.get("volvox_access_token")?.value ??
    (process.env.NODE_ENV !== "production" && process.env.VOLVOX_LOCAL_DEV === "true" ? "local-development" : undefined);
  if (!token) throw new ApiError("Workspace access is not configured.", 401);
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${token}`,
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null) as { detail?: string } | null;
    throw new ApiError(detail?.detail ?? `API request failed (${response.status}).`, response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const serverApi = {
  organizations: () => request<Organization[]>("/v1/organizations"),
  agents: (organizationId: string) =>
    request<Agent[]>(`/v1/organizations/${encodeURIComponent(organizationId)}/agents`),
  createAgent: (organizationId: string, body: AgentCreate) =>
    request<Agent>(`/v1/organizations/${encodeURIComponent(organizationId)}/agents`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateAgent: (organizationId: string, agentId: string, body: AgentUpdate) =>
    request<Agent>(
      `/v1/organizations/${encodeURIComponent(organizationId)}/agents/${encodeURIComponent(agentId)}`,
      { method: "PATCH", body: JSON.stringify(body) },
    ),
  deleteAgent: (organizationId: string, agentId: string) =>
    request<void>(
      `/v1/organizations/${encodeURIComponent(organizationId)}/agents/${encodeURIComponent(agentId)}`,
      { method: "DELETE" },
    ),
  voiceSession: (organizationId: string, agentId: string) =>
    request<{ url: string; expires_in: string }>(`/v1/organizations/${encodeURIComponent(organizationId)}/voice-session?agent_id=${encodeURIComponent(agentId)}`, { method: "POST" }),
};

export async function directLocalApi(path: string, init?: RequestInit): Promise<Response> {
  if (process.env.NODE_ENV === "production" || process.env.VOLVOX_LOCAL_DEV !== "true") {
    throw new ApiError("Local development access is disabled.", 403);
  }
  if (!API_URL) throw new ApiError("VOLVOX_API_URL is not configured.", 503);
  return fetch(`${API_URL}${path}`, {
    ...init,
    cache: "no-store",
    headers: { authorization: "Bearer local-development", ...(typeof init?.body === "string" ? { "content-type": "application/json" } : {}), ...init?.headers },
  });
}

export function isSameOrigin(request: NextRequest): boolean {
  const origin = request.headers.get("origin");
  if (!origin) return false;
  try {
    const parsed = new URL(origin);
    if (parsed.origin !== origin || !["http:", "https:"].includes(parsed.protocol)) return false;
    const host = request.headers.get("host");
    if (process.env.NODE_ENV !== "production" && process.env.VOLVOX_LOCAL_DEV === "true") {
      return host === "127.0.0.1:3000" && origin === "http://127.0.0.1:3000";
    }
    if (!host) return false;
    const forwardedProtocol = request.headers.get("x-forwarded-proto")?.split(",")[0]?.trim();
    const protocol = forwardedProtocol && ["http", "https"].includes(forwardedProtocol) ? `${forwardedProtocol}:` : request.nextUrl.protocol;
    return origin === new URL(`${protocol}//${host}`).origin;
  } catch {
    return false;
  }
}
