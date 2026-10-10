import type { Agent, DashboardData } from "./contracts";

export const previewAgents: Agent[] = [
  {
    id: "preview-front-desk",
    organization_id: "preview-workspace",
    name: "Front Desk Assistant",
    instructions: "Preview configuration only. No calls are connected.",
    config: { voice: "Sarah", language: "English" },
    enabled: true,
    created_at: "2026-10-01T12:00:00Z",
  },
  {
    id: "preview-appointments",
    organization_id: "preview-workspace",
    name: "Appointment Concierge",
    instructions: "Preview configuration only. No calendar is connected.",
    config: { voice: "Michael", language: "English" },
    enabled: false,
    created_at: "2026-10-02T12:00:00Z",
  },
];

export const previewDashboard: DashboardData = {
  mode: "preview",
  organizations: [{ id: "preview-workspace", name: "Preview workspace", created_at: "2026-10-01T00:00:00Z" }],
  agents: previewAgents,
  services: { api: "not_configured", database: "not_configured", supabase: "not_configured", voice: "not_configured" },
};
