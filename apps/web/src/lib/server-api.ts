import "server-only";

import { cookies } from "next/headers";
import type { Agent, AgentCreate, AgentUpdate, Organization } from "./contracts";
import { ApiError } from "./contracts";

const API_URL = process.env.VOLVOX_API_URL?.replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (!API_URL) throw new ApiError("VOLVOX_API_URL is not configured.", 503);
  const cookieStore = await cookies();
  const token = cookieStore.get("volvox_access_token")?.value;
  if (!token) throw new ApiError("Sign in with Supabase to connect your workspace.", 401);
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
};
