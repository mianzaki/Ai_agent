"use client";

import { AudioLines, Bot, MessageCircle, Moon, Plus, Settings2, Sun, Trash2, Volume2 } from "lucide-react";
import { useEffect, useState } from "react";
import { VoiceStudio } from "@/components/voice-studio";
import { previewDashboard } from "@/lib/preview";
import type { Agent, DashboardData, Organization } from "@/lib/contracts";

type Page = "Voice Studio" | "AI Chat + Voice" | "Agents" | "Settings";
const navigation: { page: Page; icon: typeof AudioLines }[] = [
  { page: "Voice Studio", icon: AudioLines },
  { page: "AI Chat + Voice", icon: MessageCircle },
  { page: "Agents", icon: Bot },
  { page: "Settings", icon: Settings2 },
];

export function Dashboard() {
  const [page, setPage] = useState<Page>("Voice Studio");
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [organization, setOrganization] = useState<Organization>({ id: "", name: "Loading workspace…", created_at: "" });
  const [agents, setAgents] = useState<Agent[]>([]);
  const [services, setServices] = useState<DashboardData["services"]>(previewDashboard.services);
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  const [instructions, setInstructions] = useState("");
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState<Agent | null>(null);

  useEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);
  useEffect(() => {
    let live = true;
    void (async () => {
      try {
        const statusResponse = await fetch("/api/status", { cache: "no-store" });
        const status = await statusResponse.json() as DashboardData["services"];
        if (live) setServices(status);
        const response = await fetch("/api/organizations", { cache: "no-store" });
        const body = await response.json() as { data?: Organization[]; error?: string };
        if (!response.ok || !body.data?.length) throw new Error(body.error ?? "No personal workspace is available. Check that the local API is running.");
        const org = body.data[0];
        const agentResponse = await fetch(`/api/organizations/${encodeURIComponent(org.id)}/agents`, { cache: "no-store" });
        const agentBody = await agentResponse.json() as { data?: Agent[]; error?: string };
        if (!agentResponse.ok) throw new Error(agentBody.error ?? "Could not load agents.");
        if (live) { setOrganization(org); setAgents(agentBody.data ?? []); setError(""); }
      } catch (issue) {
        if (live) setError(issue instanceof Error ? issue.message : "Could not connect to Volvox.");
      }
    })();
    return () => { live = false; };
  }, []);

  const createAgent = async () => {
    if (!name.trim() || !organization.id || saving) return;
    setSaving(true); setError("");
    try {
      const response = await fetch(`/api/organizations/${encodeURIComponent(organization.id)}/agents`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ name: name.trim(), instructions, config: { voice: "af_sarah", language: "en-us" }, enabled: true }),
      });
      const body = await response.json() as { data?: Agent; error?: string };
      if (!response.ok || !body.data) throw new Error(body.error ?? "Could not create the agent.");
      setAgents((current) => [...current, body.data!]); setName(""); setInstructions("");
    } catch (issue) { setError(issue instanceof Error ? issue.message : "Could not create the agent."); }
    finally { setSaving(false); }
  };

  const removeAgent = async (agent: Agent) => {
    if (!window.confirm(`Delete ${agent.name}? This cannot be undone.`)) return;
    try {
      const response = await fetch(`/api/organizations/${encodeURIComponent(organization.id)}/agents/${encodeURIComponent(agent.id)}`, { method: "DELETE" });
      if (!response.ok) throw new Error("Could not delete the agent.");
      setAgents((current) => current.filter((item) => item.id !== agent.id));
    } catch (issue) { setError(issue instanceof Error ? issue.message : "Could not delete the agent."); }
  };

  const updateAgent = async () => {
    if (!editing || !organization.id || saving) return;
    setSaving(true); setError("");
    try {
      const response = await fetch(`/api/organizations/${encodeURIComponent(organization.id)}/agents/${encodeURIComponent(editing.id)}`, {
        method: "PATCH", headers: { "content-type": "application/json" },
        body: JSON.stringify({ name: editing.name, instructions: editing.instructions }),
      });
      const body = await response.json() as { data?: Agent; error?: string };
      if (!response.ok || !body.data) throw new Error(body.error ?? "Could not save the agent.");
      setAgents((current) => current.map((agent) => agent.id === body.data!.id ? body.data! : agent)); setEditing(null);
    } catch (issue) { setError(issue instanceof Error ? issue.message : "Could not save the agent."); }
    finally { setSaving(false); }
  };

  const pageDescription: Record<Page, string> = {
    "Voice Studio": "Turn typed text into natural speech with your installed Kokoro voices.",
    "AI Chat + Voice": "Chat with local Ollama, then speak any response with Kokoro.",
    Agents: "Manage your personal agents and preview their available voices.",
    Settings: "Your local Volvox services and connection status.",
  };

  return <div className="app-shell">
    <aside className="sidebar" aria-label="Main navigation">
      <a className="brand" href="#studio" onClick={() => setPage("Voice Studio")}><span className="brand-mark"><AudioLines size={20} /></span><span className="brand-name">volvox<span className="brand-ai">ai</span></span></a>
      <div className="workspace-switcher"><span className="workspace-avatar">V</span><span className="workspace-copy"><b>{organization.name}</b><small>Personal workspace</small></span></div>
      <nav><div className="nav-label">Workspace</div><div className="nav-list">{navigation.map(({ page: target, icon: Icon }) => <button key={target} className={`nav-item${page === target ? " active" : ""}`} onClick={() => setPage(target)} type="button"><Icon size={17} /><span>{target}</span></button>)}</div></nav>
      <div className="sidebar-bottom"><div className="sidebar-note"><span className="status-dot" />Local-first voice tools<br /><small>Ollama + Kokoro ONNX</small></div><div className="sidebar-user"><span className="user-avatar">V</span><span><b>My Volvox</b><small>Personal workspace</small></span></div></div>
    </aside>
    <main className="main-area">
      <header className="topbar"><div className="breadcrumbs"><span>Workspace</span><span aria-hidden="true">/</span><b>{page}</b></div><div className="top-actions"><span className="status-pill"><span className={`status-dot${services.api === "connected" ? "" : " status-dot-muted"}`} />{services.api === "connected" ? "API connected" : "API unavailable"}</span><button aria-label={`Switch to ${theme === "light" ? "dark" : "light"} mode`} className="icon-btn" onClick={() => setTheme(theme === "light" ? "dark" : "light")} type="button">{theme === "light" ? <Moon size={17} /> : <Sun size={17} />}</button></div></header>
      <div className="content"><div className="page-heading"><div><div className="eyebrow">VOLVOX VOICE WORKSPACE</div><h1>{page}</h1><p>{pageDescription[page]}</p></div></div>
        {error && <div className="studio-error" role="alert">{error}<button type="button" aria-label="Dismiss error" onClick={() => setError("")}>×</button></div>}
        {!organization.id && page !== "Settings" ? <section className="card section-card"><h2>Connecting to your local workspace</h2><p>{error || "Loading your organization and agents…"}</p><button className="btn" onClick={() => location.reload()} type="button">Try again</button></section> : null}
        {organization.id && page === "Voice Studio" && <VoiceStudio key={organization.id} organization={organization} agents={agents} initialTab="studio" />}
        {organization.id && page === "AI Chat + Voice" && <VoiceStudio key={organization.id} organization={organization} agents={agents} initialTab="chat" />}
        {page === "Agents" && <div className="agents-layout"><section className="card section-card"><div className="section-head"><div><h2 className="section-title">Your agents</h2><p className="section-subtitle">Agent instructions apply to typed AI chat messages.</p></div><span className="pill">{agents.length} agents</span></div>{agents.length ? agents.map((agent) => editing?.id === agent.id ? <article className="agent-edit" key={agent.id}><label className="studio-field"><span>Agent name</span><input value={editing.name} onChange={(event) => setEditing({ ...editing, name: event.target.value })} maxLength={200} /></label><label className="studio-field"><span>Instructions</span><textarea value={editing.instructions} onChange={(event) => setEditing({ ...editing, instructions: event.target.value })} maxLength={20000} rows={3} /></label><button className="btn btn-primary" disabled={saving || !editing.name.trim()} onClick={() => void updateAgent()} type="button">{saving ? "Saving…" : "Save agent"}</button><button className="btn" onClick={() => setEditing(null)} type="button">Cancel</button></article> : <article className="agent-row" key={agent.id}><span className="agent-emblem"><Bot size={17} /></span><div className="agent-meta"><b>{agent.name}</b><small>{agent.instructions || "No custom instructions"}</small></div><button className="agent-action" aria-label={`Edit ${agent.name}`} onClick={() => setEditing(agent)} type="button"><Settings2 size={16} /></button><button className="agent-action" aria-label={`Delete ${agent.name}`} onClick={() => void removeAgent(agent)} type="button"><Trash2 size={16} /></button></article>) : <div className="chat-empty"><span><Bot size={22} /></span><b>No agents yet</b><p>Create an agent to give Ollama a custom system instruction.</p></div>}</section><section className="card section-card"><div className="section-head"><div><h2 className="section-title">Voice presets</h2><p className="section-subtitle">Preview installed Kokoro voices and save agent defaults.</p></div><Volume2 size={19} /></div>{organization.id && <VoiceStudio key={`${organization.id}-presets`} organization={organization} agents={agents} initialTab="presets" />}</section><section className="card section-card"><h2 className="section-title">Create agent</h2><label className="studio-field"><span>Agent name</span><input value={name} onChange={(event) => setName(event.target.value)} maxLength={200} placeholder="Friendly assistant" /></label><label className="studio-field"><span>Instructions for Ollama</span><textarea value={instructions} onChange={(event) => setInstructions(event.target.value)} maxLength={20000} placeholder="How should this agent respond?" rows={4} /></label><button className="btn btn-primary" disabled={saving || !name.trim()} onClick={() => void createAgent()} type="button"><Plus size={16} />{saving ? "Saving…" : "Create agent"}</button></section></div>}
        {page === "Settings" && <div className="settings-grid"><section className="card section-card"><h2 className="section-title">Local services</h2><ServiceRow label="FastAPI" value={services.api} /><ServiceRow label="Database" value={services.database} /><ServiceRow label="Kokoro ONNX" value={services.voice} /><ServiceRow label="Ollama" value={services.ollama} /></section><section className="card section-card"><h2 className="section-title">Workspace</h2><p className="settings-copy">{organization.name}</p><p className="settings-copy">Text is sent to the local Volvox API. Ollama and Kokoro run on this machine.</p></section></div>}
      </div>
    </main>
  </div>;
}

function ServiceRow({ label, value }: { label: string; value: string }) { return <div className="service-row"><span>{label}</span><span className={`service-state ${value === "connected" ? "good" : ""}`}><i />{value.replaceAll("_", " ")}</span></div>; }
