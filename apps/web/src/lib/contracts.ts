export type Organization = {
  id: string;
  name: string;
  created_at: string;
};

export type Agent = {
  id: string;
  organization_id: string;
  name: string;
  instructions: string;
  config: Record<string, unknown>;
  enabled: boolean;
  created_at: string;
};

export type AgentCreate = {
  name: string;
  instructions?: string;
  config?: Record<string, unknown>;
  enabled?: boolean;
};

export type AgentUpdate = Partial<AgentCreate>;

export type ServiceState = "connected" | "not_configured" | "unavailable";

export type DashboardData = {
  mode: "connected" | "preview";
  organizations: Organization[];
  agents: Agent[];
  services: {
    api: ServiceState;
    database: ServiceState;
    supabase: ServiceState;
    apiAuthenticated?: boolean | null;
    voice: ServiceState;
  };
};

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
