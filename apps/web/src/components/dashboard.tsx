"use client";

import {
  Activity,
  ArrowRight,
  AudioLines,
  Bell,
  Bot,
  CalendarClock,
  Check,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Clock3,
  Database,
  FileAudio2,
  FileText,
  Headphones,
  HeartPulse,
  LayoutDashboard,
  Menu,
  Mic2,
  Moon,
  Play,
  Plus,
  Radio,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  Sun,
  Users,
  WandSparkles,
  X,
  type LucideIcon,
} from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { Agent, DashboardData, Organization } from "@/lib/contracts";
import { previewDashboard, previewAgents } from "@/lib/preview";

type PageKey = "Overview" | "My Agents" | "Agent Builder" | "Voice Playground" | "Calls" | "Analytics" | "Settings";
type NavItem = { label: PageKey; icon: LucideIcon; badge?: string };

const primaryNav: NavItem[] = [
  { label: "Overview", icon: LayoutDashboard },
  { label: "My Agents", icon: Bot, badge: "2" },
  { label: "Agent Builder", icon: WandSparkles },
  { label: "Voice Playground", icon: AudioLines },
];
const insightsNav: NavItem[] = [
  { label: "Calls", icon: FileAudio2 },
  { label: "Analytics", icon: Activity },
  { label: "Settings", icon: Settings2 },
];

function GlassOrb({ size = 22 }: { size?: number }) {
  return <AudioLines size={size} strokeWidth={2.3} />;
}

function StatusDot({ ok = false }: { ok?: boolean }) {
  return <span className={`status-dot${ok ? "" : " status-dot-muted"}`} />;
}

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (next: boolean) => void; label: string }) {
  return (
    <button aria-label={label} aria-pressed={checked} className={`toggle ${checked ? "on" : ""}`} onClick={() => onChange(!checked)} type="button">
      <span />
    </button>
  );
}

export function Dashboard() {
  const [page, setPage] = useState<PageKey>("Overview");
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [data, setData] = useState<DashboardData>(previewDashboard);
  const [selectedOrg, setSelectedOrg] = useState<Organization>(previewDashboard.organizations[0]);
  const [agents, setAgents] = useState<Agent[]>(previewAgents);
  const [toast, setToast] = useState<{ text: string; error?: boolean } | null>(null);
  const [search, setSearch] = useState("");
  const [modal, setModal] = useState(false);
  const [draftAgent, setDraftAgent] = useState<Agent | null>(null);
  const [playgroundReady, setPlaygroundReady] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [authModal, setAuthModal] = useState(false);
  const [signedInEmail, setSignedInEmail] = useState("");
  const [businessDate] = useState(() => new Intl.DateTimeFormat("en", { weekday: "long", month: "long", day: "numeric" }).format(new Date()).toUpperCase());
  const reducedMotion = useReducedMotion();

  const notify = useCallback((text: string, error = false) => {
    setToast({ text, error });
    window.setTimeout(() => setToast(null), 3200);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/session", { cache: "no-store" })
      .then((response) => response.json())
      .then((session: { authenticated?: boolean; email?: string }) => {
        if (!cancelled && session.authenticated && session.email) setSignedInEmail(session.email);
        else if (!cancelled) setSignedInEmail("");
      })
      .catch(() => undefined);
    fetch("/api/status", { cache: "no-store" })
      .then((response) => response.json())
      .then((services: DashboardData["services"]) => {
        if (!cancelled) setData((old) => ({ ...old, services }));
      })
      .catch(() => undefined);
    fetch("/api/organizations", { cache: "no-store" })
      .then(async (response) => ({ response, body: await response.json() }))
      .then(async ({ response, body }) => {
        if (cancelled) return;
        if (response.ok && Array.isArray(body.data)) {
          const organizations = body.data as Organization[];
          if (!organizations.length) {
            setSelectedOrg({ id: "", name: "No organization", created_at: "" });
            setData((old) => ({ ...old, mode: "connected", organizations, agents: [], services: { ...old.services, api: "connected", database: "connected", apiAuthenticated: true, voice: "not_configured" } }));
            setAgents([]);
            notify("API connected. No organization memberships were found.");
            return;
          }
          setSelectedOrg(organizations[0]);
          setData((old) => ({ ...old, mode: "connected", organizations, services: { ...old.services, api: "connected", database: "connected", apiAuthenticated: true, voice: "not_configured" } }));
          fetch(`/api/organizations/${encodeURIComponent(organizations[0].id)}/agents`, { cache: "no-store" })
            .then(async (agentResponse) => ({ agentResponse, agentBody: await agentResponse.json() }))
            .then(({ agentResponse, agentBody }) => {
              if (cancelled) return;
              if (agentResponse.ok && Array.isArray(agentBody.data)) {
                setAgents(agentBody.data);
                setData((old) => ({ ...old, agents: agentBody.data }));
              } else {
                notify(agentBody.error ?? "Could not load agents.", true);
              }
            })
            .catch(() => !cancelled && notify("The API could not be reached.", true));
        } else if (body.error) {
          // Health is independent of authentication and contains no tenant data.
          const services = await fetch("/api/status", { cache: "no-store" }).then((statusResponse) => statusResponse.json() as Promise<DashboardData["services"]>).catch(() => previewDashboard.services);
          if (cancelled) return;
          const hasIdentity = services.supabase === "connected";
          setSelectedOrg(hasIdentity ? { id: "", name: "No organization", created_at: "" } : previewDashboard.organizations[0]);
          setData({ ...previewDashboard, services, mode: hasIdentity ? "connected" : "preview", organizations: hasIdentity ? [] : previewDashboard.organizations });
          setAgents(hasIdentity ? [] : previewAgents);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setData({ ...previewDashboard, mode: "preview" });
          setAgents(previewAgents);
        }
      });
    return () => { cancelled = true; };
  }, [notify]);

  const filteredAgents = useMemo(
    () => agents.filter((agent) => agent.name.toLowerCase().includes(search.toLowerCase())),
    [agents, search],
  );

  const saveAgent = async (agent: Agent, enabled: boolean) => {
    if (data.mode === "preview") {
      const updated = agents.some((item) => item.id === agent.id)
        ? agents.map((item) => item.id === agent.id ? { ...agent, enabled } : item)
        : [...agents, { ...agent, enabled }];
      setAgents(updated);
      setModal(false);
      notify("Saved in preview only. Connect the API to persist this agent.");
      return;
    }
    if (!selectedOrg.id) throw new Error("Select an organization before saving an agent.");
    const method = agent.id.startsWith("preview-") ? "POST" : "PATCH";
    const url = method === "POST"
      ? `/api/organizations/${encodeURIComponent(selectedOrg.id)}/agents`
      : `/api/organizations/${encodeURIComponent(selectedOrg.id)}/agents/${encodeURIComponent(agent.id)}`;
    const response = await fetch(url, {
      method,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ name: agent.name, instructions: agent.instructions, config: agent.config, enabled }),
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.error ?? "Could not save agent.");
    const saved = body.data as Agent;
    setAgents((old) => old.some((item) => item.id === saved.id) ? old.map((item) => item.id === saved.id ? saved : item) : [...old, saved]);
    setModal(false);
    notify("Agent saved.");
  };

  const deleteAgent = async (agent: Agent) => {
    if (data.mode === "preview") {
      setAgents((old) => old.filter((item) => item.id !== agent.id));
      notify("Removed from this preview session.");
      return;
    }
    if (!selectedOrg.id) {
      notify("Select an organization before deleting an agent.", true);
      return;
    }
    const response = await fetch(`/api/organizations/${encodeURIComponent(selectedOrg.id)}/agents/${encodeURIComponent(agent.id)}`, { method: "DELETE" });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      notify(body.error ?? "Could not delete agent.", true);
      return;
    }
    setAgents((old) => old.filter((item) => item.id !== agent.id));
    notify("Agent deleted.");
  };

  const openCreate = () => {
    setDraftAgent({ id: `preview-${crypto.randomUUID()}`, organization_id: selectedOrg.id ?? "", name: "", instructions: "", config: { voice: "af_sarah", language: "English" }, enabled: true, created_at: new Date().toISOString() });
    setModal(true);
  };

  const pageTitle = page === "Overview" ? "Welcome to Volvox" : page;
  const pageSubtitle: Record<PageKey, string> = {
    Overview: "Hereâ€™s whatâ€™s happening with your voice agents today.",
    "My Agents": "Build, tune, and manage your AI team.",
    "Agent Builder": "Shape how your agent sounds, responds, and helps.",
    "Voice Playground": "Try a local voice flow when the runtime is connected.",
    Calls: "Review call activity once a telephony transport is connected.",
    Analytics: "Understand what your agents are achieving.",
    Settings: "Manage your workspace, team, and integrations.",
  };

  const pageVariants = {
    initial: { opacity: 0, y: reducedMotion ? 0 : 5 },
    animate: { opacity: 1, y: 0 },
    exit: { opacity: 0, y: reducedMotion ? 0 : -3 },
  };

  return (
    <div className="app-shell">
      <aside aria-label="Main navigation" className={`sidebar${mobileMenuOpen ? " mobile-open" : ""}`}>
        <div className="brand">
          <div className="brand-mark"><GlassOrb /></div>
          <div className="brand-name">volvox<span className="brand-ai">ai</span></div>
        </div>
        <button className="workspace-switcher" disabled={data.mode === "connected" && data.organizations.length < 2} type="button" aria-label="Workspace selector" onClick={() => { if (data.organizations.length > 1) notify("Organization switching is not available in this foundation."); }}>
          <span className="workspace-avatar">V</span>
          <span className="workspace-copy"><b>{data.mode === "preview" ? "Preview workspace" : selectedOrg.name}</b><small>{data.mode === "preview" ? "Local preview" : data.organizations.length ? "Workspace" : "No membership"}</small></span>
          <ChevronDown size={14} />
        </button>
        <nav>
          <div className="nav-label">Workspace</div>
          <div className="nav-list">{primaryNav.map((item) => <NavButton key={item.label} item={item} active={page === item.label} onClick={() => setPage(item.label)} />)}</div>
          <div className="nav-label">Insights &amp; admin</div>
          <div className="nav-list">{insightsNav.map((item) => <NavButton key={item.label} item={item} active={page === item.label} onClick={() => setPage(item.label)} />)}</div>
        </nav>
        <div className="sidebar-bottom">
          <div className="plan-card">
          <div className="plan-top"><span>Plans and billing</span><span className="plan-chip">NOT CONNECTED</span></div>
            <p>Usage and billing appear here when metering is connected.</p>
            <div className="plan-track"><span /></div>
          </div>
          <div className="sidebar-user"><div className="user-avatar">{signedInEmail ? signedInEmail.slice(0, 1).toUpperCase() : "V"}</div><div><b>{signedInEmail || "Preview mode"}</b><small>{signedInEmail ? "Supabase account" : "No identity connected"}</small></div>{signedInEmail ? <button aria-label="Sign out" className="agent-action" onClick={async () => { await fetch("/api/auth/logout", { method: "POST" }); window.location.reload(); }}><X size={15} /></button> : <button aria-label="Sign in" className="agent-action" onClick={() => setAuthModal(true)}><ArrowRight size={15} /></button>}</div>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumbs"><button className="icon-btn mobile-menu" aria-label="Open navigation" aria-expanded={mobileMenuOpen} onClick={() => setMobileMenuOpen((open) => !open)}><Menu size={15} /></button><span>Workspace</span><ChevronRight size={12} /><b>{page}</b></div>
          <div className="top-actions">
            <div className="status-pill"><StatusDot ok={data.services.api === "connected"} />{data.services.api === "connected" ? "API connected" : "Preview mode"}</div>
            <button aria-label={`Switch to ${theme === "light" ? "dark" : "light"} mode`} className="icon-btn" onClick={() => setTheme(theme === "light" ? "dark" : "light")} type="button">{theme === "light" ? <Moon size={15} /> : <Sun size={15} />}</button>
            <button aria-label="Notifications" className="icon-btn" type="button" onClick={() => notify("Youâ€™re all caught up.")}><Bell size={15} /><span className="notification-dot" /></button>
            <button aria-label="Help" className="icon-btn" type="button" onClick={() => notify("Help center is coming soon.")}><CircleHelp size={15} /></button>
          </div>
        </header>
        <div className="content">
          <div className="page-heading">
            <div><div className="eyebrow">{page === "Overview" ? businessDate : "VOLVOX WORKSPACE"}</div><h1>{pageTitle}</h1><p>{pageSubtitle[page]}</p></div>
            <div className="heading-actions">{page === "My Agents" || page === "Agent Builder" ? <button className="btn btn-primary" onClick={openCreate}><Plus size={14} />New agent</button> : <button className="btn" onClick={() => notify("This section is connected as data becomes available.")}><CalendarClock size={13} />Last 7 days<ChevronDown size={12} /></button>}</div>
          </div>
          <AnimatePresence mode="wait">
            <motion.div key={page} variants={pageVariants} initial="initial" animate="animate" exit="exit" transition={{ duration: reducedMotion ? 0 : 0.18 }}>
              {page === "Overview" && <Overview agents={agents} data={data} onNavigate={setPage} onCreate={openCreate} onSignIn={() => setAuthModal(true)} />}
              {page === "My Agents" && <AgentsPage agents={filteredAgents} search={search} onSearch={setSearch} onEdit={(agent) => { setDraftAgent(agent); setPage("Agent Builder"); setModal(true); }} onToggle={async (agent) => { try { await saveAgent(agent, !agent.enabled); } catch (error) { notify(error instanceof Error ? error.message : "Could not update agent.", true); } }} onDelete={deleteAgent} preview={data.mode === "preview"} onSignIn={() => setAuthModal(true)} />}
              {page === "Agent Builder" && <Builder agents={agents} preview={data.mode === "preview"} onCreate={openCreate} onEdit={(agent) => { setDraftAgent(agent); setModal(true); }} onSignIn={() => setAuthModal(true)} />}
              {page === "Voice Playground" && <Playground agents={agents} ready={playgroundReady} onConnect={() => { setPlaygroundReady(false); notify("No browser media transport is connected. This control wonâ€™t start a call.", true); }} />}
              {page === "Calls" && <CallsEmpty />}
              {page === "Analytics" && <AnalyticsEmpty />}
              {page === "Settings" && <SettingsPage services={data.services} mode={data.mode} />}
            </motion.div>
          </AnimatePresence>
        </div>
      </main>

      <AnimatePresence>{modal && draftAgent && <AgentModal agent={draftAgent} onClose={() => setModal(false)} onSave={async (agent) => { try { await saveAgent(agent, agent.enabled); } catch (error) { notify(error instanceof Error ? error.message : "Could not save agent.", true); } }} />}</AnimatePresence>
      <AnimatePresence>{authModal && <SignInModal onClose={() => setAuthModal(false)} onSuccess={() => window.location.reload()} />}</AnimatePresence>
      <AnimatePresence>{toast && <motion.div animate={{ opacity: 1, y: 0 }} className={`toast${toast.error ? " error" : ""}`} exit={{ opacity: 0, y: 8 }} initial={{ opacity: 0, y: 8 }} role={toast.error ? "alert" : "status"}>{toast.text}</motion.div>}</AnimatePresence>
    </div>
  );
}

function NavButton({ item, active, onClick }: { item: NavItem; active: boolean; onClick: () => void }) {
  const Icon = item.icon;
  return <button className={`nav-item${active ? " active" : ""}`} onClick={onClick} type="button"><Icon size={15} strokeWidth={1.8} /><span>{item.label}</span>{item.badge && <small className="nav-trailing">{item.badge}</small>}</button>;
}

function Overview({ agents, data, onNavigate, onCreate, onSignIn }: { agents: Agent[]; data: DashboardData; onNavigate: (page: PageKey) => void; onCreate: () => void; onSignIn: () => void }) {
  return <>
    <div className="grid stats-grid">
      <StatCard title="Active agents" value={String(agents.filter((agent) => agent.enabled).length).padStart(2, "0")} foot="Ready when a transport is connected" icon={Bot} color="violet" />
      <StatCard title="Total calls" value="â€”" foot="No telephony data connected" icon={Headphones} color="mint" empty />
      <StatCard title="Talk time" value="â€”" foot="Usage metering not connected" icon={Clock3} color="blue" empty />
      <StatCard title="Avg. call duration" value="â€”" foot="No call history yet" icon={Activity} color="peach" empty />
    </div>
    <div className="grid main-grid">
      <section className="card section-card">
        <div className="section-head"><div><h2 className="section-title">Call activity</h2><p className="section-subtitle">A view of conversations across your agents</p></div><select aria-label="Call activity time range" className="select-small" defaultValue="7 days"><option>7 days</option><option>30 days</option></select></div>
        <EmptyChart title="Your call activity will show up here" text="Connect a telephony transport to see conversations, trends, and outcomes." icon={AudioLines} />
      </section>
      <ActivityCard />
    </div>
    <div className="grid bottom-grid">
      <section className="card section-card">
        <div className="section-head"><div><h2 className="section-title">Your agents</h2><p className="section-subtitle">A quick look at your voice team</p></div><button className="btn btn-quiet" onClick={() => onNavigate("My Agents")}>View all<ArrowRight size={12} /></button></div>
        {agents.length ? agents.slice(0, 4).map((agent) => <AgentRow agent={agent} key={agent.id} />) : <div className="chart-empty" style={{ minHeight: 150 }}><div className="empty-inner"><b>No agents yet</b><p>Create your first agent to get started.</p><button className="btn btn-primary" onClick={onCreate}><Plus size={12} />Create agent</button></div></div>}
      </section>
      <section className="card section-card">
        <div className="section-head"><div><h2 className="section-title">Environment health</h2><p className="section-subtitle">Local services at a glance</p></div><HeartPulse size={16} color="#8c82cc" /></div>
        <HealthList services={data.services} />
      </section>
    </div>
    {data.mode === "preview" && <PreviewBanner onSignIn={onSignIn} />}
  </>;
}

function StatCard({ title, value, foot, icon: Icon, color, empty = false }: { title: string; value: string; foot: string; icon: LucideIcon; color: string; empty?: boolean }) {
  return <article className="card stat-card"><div className="stat-head"><span>{title}</span><span className={`stat-icon ${color}`}><Icon size={14} /></span></div><div className="stat-value">{value}</div><div className="stat-foot">{empty ? <span className="empty-note">Not connected</span> : <span>{foot}</span>}</div></article>;
}

function EmptyChart({ title, text, icon: Icon }: { title: string; text: string; icon: LucideIcon }) {
  return <div className="chart-empty"><div className="empty-inner"><div className="empty-illustration"><Icon size={19} /></div><b>{title}</b><p>{text}</p></div></div>;
}

function ActivityCard() {
  return <section className="card section-card"><div className="section-head"><div><h2 className="section-title">Workspace setup</h2><p className="section-subtitle">Connect the pieces to make this workspace operational.</p></div><Sparkles size={16} color="#8c82cc" /></div><div className="activity-list">
    <ActivityRow icon={Bot} color="" title="Configure your first agent" text="Add the business instructions, voice, and handoff rules." time="Next step" />
    <ActivityRow icon={ShieldCheck} color="green" title="Connect your organization" text="Sign in and load data scoped to your organization." time="Next step" />
    <ActivityRow icon={Radio} color="orange" title="Connect a voice transport" text="A media transport is required before a browser call can start." time="Not connected" />
  </div></section>;
}

function ActivityRow({ icon: Icon, color, title, text, time }: { icon: LucideIcon; color: string; title: string; text: string; time: string }) {
  return <div className="activity-row"><div className={`activity-symbol ${color}`}><Icon size={13} /></div><div className="activity-copy"><b>{title}</b><p>{text}</p></div><span className="activity-time">{time}</span></div>;
}

function AgentRow({ agent }: { agent: Agent }) {
  return <div className="agent-row"><div className="agent-emblem"><Bot size={17} /></div><div className="agent-meta"><b>{agent.name}</b><small>{String(agent.config.voice ?? "Voice not set")} Â· {String(agent.config.language ?? "Language not set")}</small></div><div className={`agent-health${agent.enabled ? "" : " off"}`}><StatusDot ok={agent.enabled} />{agent.enabled ? "Enabled" : "Paused"}</div><button className="agent-action" aria-label={`Open ${agent.name}`}><ArrowRight size={14} /></button></div>;
}

function HealthList({ services }: { services: DashboardData["services"] }) {
  const rows: { key: keyof typeof services; title: string; detail: string; icon: LucideIcon }[] = [
    { key: "api", title: "API service", detail: "FastAPI control plane", icon: Radio },
    { key: "database", title: "Database", detail: "PostgreSQL readiness", icon: Database },
    { key: "supabase", title: "Authentication", detail: "Supabase identity", icon: ShieldCheck },
    { key: "voice", title: "Voice transport", detail: "Browser media connection", icon: Mic2 },
  ];
  return <div className="health-stack">{rows.map((row) => <div className="health-row" key={row.key}><div className="health-symbol"><row.icon size={13} /></div><div className="health-copy"><b>{row.title}</b><small>{row.detail}</small></div><span className={`health-state ${services[row.key] === "connected" ? "ok" : ""}`}>{services[row.key] === "connected" ? "Connected" : services[row.key] === "unavailable" ? "Unavailable" : "Not connected"}</span></div>)}</div>;
}

function PreviewBanner({ onSignIn }: { onSignIn: () => void }) {
  return <div className="preview-banner"><Sparkles size={15} /><p><b>Preview mode</b> â€” what you see is clearly labeled sample configuration. Calls, usage, and billing are not represented as live data.</p><button className="btn" onClick={onSignIn}>Connect services<ArrowRight size={11} /></button></div>;
}

function AgentsPage({ agents, search, onSearch, onEdit, onToggle, onDelete, preview, onSignIn }: { agents: Agent[]; search: string; onSearch: (value: string) => void; onEdit: (agent: Agent) => void; onToggle: (agent: Agent) => void; onDelete: (agent: Agent) => void; preview: boolean; onSignIn: () => void }) {
  return <div className="page-body"><section className="card section-card"><div className="section-head"><div><h2 className="section-title">Your agents <span className="pill">{agents.length}</span></h2><p className="section-subtitle">Configure the voice and behavior for each job.</p></div><div className="search-box"><Search size={13} /><input aria-label="Search agents" onChange={(event) => onSearch(event.target.value)} placeholder="Search agents" value={search} /></div></div>
    {agents.length ? agents.map((agent) => <div className="agent-row" key={agent.id}><div className="agent-emblem"><Bot size={17} /></div><div className="agent-meta"><b>{agent.name}</b><small>{String(agent.config.voice ?? "Voice not set")} Â· {String(agent.config.language ?? "English")} {preview && "Â· Preview"}</small></div><div className={`agent-health${agent.enabled ? "" : " off"}`}><StatusDot ok={agent.enabled} />{agent.enabled ? "Enabled" : "Paused"}</div><Toggle checked={agent.enabled} label={`${agent.enabled ? "Disable" : "Enable"} ${agent.name}`} onChange={() => onToggle(agent)} /><button className="agent-action" aria-label={`Edit ${agent.name}`} onClick={() => onEdit(agent)}><Settings2 size={14} /></button><button className="agent-action" aria-label={`Delete ${agent.name}`} onClick={() => onDelete(agent)}><X size={14} /></button></div>) : <EmptyChart title="No agents match that search" text="Try a different name or create a new agent." icon={Bot} />}
  </section>{preview && <PreviewBanner onSignIn={onSignIn} />}</div>;
}

function Builder({ agents, preview, onCreate, onEdit, onSignIn }: { agents: Agent[]; preview: boolean; onCreate: () => void; onEdit: (agent: Agent) => void; onSignIn: () => void }) {
  return <div className="builder-grid"><section className="card section-card"><div className="section-head"><div><h2 className="section-title">Agent configurations</h2><p className="section-subtitle">Each agent keeps its instructions and voice settings together.</p></div><button className="btn btn-primary" onClick={onCreate}><Plus size={13} />New agent</button></div>{agents.map((agent) => <div className="agent-row" key={agent.id}><div className="agent-emblem"><WandSparkles size={16} /></div><div className="agent-meta"><b>{agent.name}</b><small>{(agent.instructions || "No business instructions yet.").slice(0, 78)}</small></div><button className="btn" onClick={() => onEdit(agent)}>Edit<ArrowRight size={12} /></button></div>)}{preview && <PreviewBanner onSignIn={onSignIn} />}</section><section className="card form-card"><div className="eyebrow">BUILDER GUIDE</div><h2 className="section-title" style={{ marginTop: 8 }}>A good first prompt</h2><p className="section-subtitle" style={{ lineHeight: 1.7 }}>Give your agent one clear job, the business details it needs, and the moments when it should hand things to a person.</p><div className="placeholder-list"><div className="placeholder-row"><span className="workspace-avatar" style={{ width: 23, height: 23, fontSize: 9 }}>1</span><span><b>Set the purpose</b><br />What should this agent handle?</span></div><div className="placeholder-row"><span className="workspace-avatar" style={{ width: 23, height: 23, fontSize: 9, background: "#d9d3ff" }}>2</span><span><b>Share safe context</b><br />Only provide approved business facts.</span></div><div className="placeholder-row"><span className="workspace-avatar" style={{ width: 23, height: 23, fontSize: 9, background: "#ffdabe" }}>3</span><span><b>Define handoff</b><br />Say when a human should take over.</span></div></div></section></div>;
}

function Playground({ agents, ready, onConnect }: { agents: Agent[]; ready: boolean; onConnect: () => void }) {
  const [agentId, setAgentId] = useState(agents[0]?.id ?? "");
  return <div className="page-body"><div className="grid main-grid"><section className="card playground"><div className="playground-core"><div className="voice-orb"><AudioLines size={43} /></div><div className="eyebrow">LOCAL PLAYGROUND</div><h2>{ready ? "Transport connected" : "Your voice stage is ready"}</h2><p>{ready ? "A real media session is connected." : "The browser media transport is not configured, so no call will be started here."}</p><button className="btn btn-primary" disabled={!ready} onClick={onConnect}><Play size={13} />Start session</button></div></section><section className="card form-card"><div className="section-head"><div><h2 className="section-title">Session setup</h2><p className="section-subtitle">Choose the agent you want to test.</p></div><Headphones size={15} color="#8678e8" /></div><div className="field"><label htmlFor="playground-agent">Selected agent</label><select id="playground-agent" value={agentId} onChange={(event) => setAgentId(event.target.value)}>{agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}</select></div><div className="health-stack"><div className="health-row"><div className="health-symbol"><Radio size={13} /></div><div className="health-copy"><b>Media connection</b><small>WebRTC / LiveKit not integrated</small></div><span className="health-state">Disconnected</span></div><div className="health-row"><div className="health-symbol"><FileText size={13} /></div><div className="health-copy"><b>Transcript</b><small>No live transcript stream</small></div><span className="health-state">Waiting</span></div></div><div className="preview-banner" style={{ marginTop: 14 }}><CircleHelp size={14} /><p>Playground controls are disabled until a real browser media transport and session endpoint are implemented.</p></div></section></div><section className="card section-card"><div className="tabs"><button className="tab active">Transcript</button><button className="tab">Event log</button></div><EmptyChart title="No session transcript" text="Transcript appears when a real voice session is connected." icon={FileText} /></section></div>;
}

function CallsEmpty() {
  return <section className="card section-card page-placeholder"><div className="section-head"><div><h2 className="section-title">Call history</h2><p className="section-subtitle">Call records will appear once telephony is connected.</p></div><div className="heading-actions" style={{ padding: 0 }}><div className="search-box"><Search size={13} /><input aria-label="Search calls" placeholder="Search caller or agent" /></div><button className="btn"><ChevronDown size={12} />Filters</button></div></div><div className="call-table-wrap"><table className="call-table"><thead><tr><th>CALLER</th><th>AGENT</th><th>DATE</th><th>DURATION</th><th>STATUS</th></tr></thead><tbody><tr><td colSpan={5} style={{ padding: 0 }}><EmptyChart title="No calls yet" text="Connect a real telephony transport to start collecting call history." icon={Headphones} /></td></tr></tbody></table></div><div className="preview-banner"><ShieldCheck size={14} /><p><b>Recording controls are unavailable.</b> Recordings require consent, retention, and storage features that are not implemented.</p></div></section>;
}

function AnalyticsEmpty() {
  return <div className="page-body"><div className="grid stats-grid"><StatCard title="Calls handled" value="â€”" foot="No call events" icon={Headphones} color="violet" empty /><StatCard title="Resolution rate" value="â€”" foot="Outcome tracking not connected" icon={Check} color="mint" empty /><StatCard title="Avg. response time" value="â€”" foot="Latency telemetry not connected" icon={Clock3} color="blue" empty /><StatCard title="Handoff rate" value="â€”" foot="No handoff events" icon={Users} color="peach" empty /></div><section className="card section-card"><div className="section-head"><div><h2 className="section-title">Agent performance</h2><p className="section-subtitle">Real call and outcome data will populate here.</p></div></div><EmptyChart title="Analytics will appear after your first connected call" text="No sample metrics are shown as if they were live." icon={Activity} /></section></div>;
}

function SettingsPage({ services, mode }: { services: DashboardData["services"]; mode: DashboardData["mode"] }) {
  const configs = [
    { name: "API control plane", detail: "Tenant-aware FastAPI service", state: services.api },
    { name: "Authentication", detail: "Supabase JWT and membership check", state: services.supabase },
    { name: "Database", detail: "PostgreSQL readiness", state: services.database },
    { name: "Voice transport", detail: "Media sessions are not configured", state: services.voice },
  ];
  return <div className="builder-grid"><section className="card section-card"><div className="eyebrow">WORKSPACE</div><div className="field"><label htmlFor="org-name">Organization name</label><input id="org-name" disabled value={mode === "preview" ? "Preview workspace" : "Connected organization"} /></div><div className="field"><label>Team members</label><div className="placeholder-row"><Users size={14} /><span><b>Membership management isnâ€™t available yet.</b><br />Member data is kept private on the API.</span></div></div><div className="field"><label>Billing</label><div className="placeholder-row"><CircleHelp size={14} /><span><b>Billing is a placeholder.</b><br />No usage or payment data is connected.</span></div></div></section><section className="card section-card"><h2 className="section-title">Connected services</h2><p className="section-subtitle">Only configured and verified services show connected.</p><div className="health-stack">{configs.map((item) => <div className="health-row" key={item.name}><div className="health-symbol"><Database size={13} /></div><div className="health-copy"><b>{item.name}</b><small>{item.detail}</small></div><span className={`health-state ${item.state === "connected" ? "ok" : ""}`}>{item.state === "connected" ? "Connected" : "Not connected"}</span></div>)}</div><div className="preview-banner"><ShieldCheck size={14} /><p>Service credentials remain on the server. Never add service-role secrets to browser-exposed variables.</p></div></section></div>;
}

function AgentModal({ agent, onClose, onSave }: { agent: Agent; onClose: () => void; onSave: (agent: Agent) => Promise<void> }) {
  const [name, setName] = useState(agent.name);
  const [instructions, setInstructions] = useState(agent.instructions);
  const [voice, setVoice] = useState(String(agent.config.voice ?? "af_sarah"));
  const [language, setLanguage] = useState(String(agent.config.language ?? "English"));
  const [greeting, setGreeting] = useState(String(agent.config.greeting ?? ""));
  const [hours, setHours] = useState(String(agent.config.business_hours ?? ""));
  const [businessName, setBusinessName] = useState(String(agent.config.business_name ?? ""));
  const [handoff, setHandoff] = useState(Boolean(agent.config.human_handoff ?? true));
  const [enabled, setEnabled] = useState(agent.enabled);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!name.trim()) { setError("Give your agent a name to continue."); return; }
    setSaving(true); setError("");
    try {
      await onSave({ ...agent, name: name.trim(), instructions, enabled, config: { ...agent.config, business_name: businessName, voice, language, greeting, business_hours: hours, human_handoff: handoff } });
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : "Could not save this agent.");
    } finally { setSaving(false); }
  };
  return <motion.div animate={{ opacity: 1 }} className="modal-scrim" exit={{ opacity: 0 }} initial={{ opacity: 0 }} onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <motion.form animate={{ opacity: 1, y: 0 }} className="agent-modal" exit={{ opacity: 0, y: 10 }} initial={{ opacity: 0, y: 10 }} onSubmit={submit}>
      <div className="modal-head"><div><div className="eyebrow">AGENT BUILDER</div><h2>{agent.name ? "Edit your agent" : "Create an agent"}</h2><p>Tell your agent what it should do and how it should sound.</p></div><button aria-label="Close" className="icon-btn" onClick={onClose} type="button"><X size={15} /></button></div>
      <div className="modal-scroll"><div className="two-fields"><div className="field"><label htmlFor="agent-name">Agent name</label><input id="agent-name" maxLength={200} onChange={(event) => setName(event.target.value)} placeholder="e.g. Front desk assistant" required value={name} /></div><div className="field"><label htmlFor="business-name">Business name</label><input id="business-name" maxLength={200} onChange={(event) => setBusinessName(event.target.value)} placeholder="Your business" value={businessName} /></div></div>
        <div className="field"><label htmlFor="agent-instructions">Purpose and instructions</label><textarea id="agent-instructions" maxLength={20000} onChange={(event) => setInstructions(event.target.value)} placeholder="You answer incoming questions about our business. Be warm, concise, and ask one question at a time." value={instructions} /><span className="field-hint">Add approved business facts and tell the agent when to hand off.</span></div>
        <div className="two-fields"><div className="field"><label htmlFor="agent-voice">Voice</label><select id="agent-voice" onChange={(event) => setVoice(event.target.value)} value={voice}><option value="af_sarah">Sarah Â· Warm</option><option value="am_michael">Michael Â· Clear</option><option value="af_nicole">Nicole Â· Bright</option></select></div><div className="field"><label htmlFor="agent-language">Language</label><select id="agent-language" onChange={(event) => setLanguage(event.target.value)} value={language}><option>English</option><option>Spanish</option><option>French</option><option>Urdu</option></select></div></div>
        <div className="field"><label htmlFor="agent-greeting">Opening greeting</label><input id="agent-greeting" maxLength={500} onChange={(event) => setGreeting(event.target.value)} placeholder="Thanks for callingâ€¦" value={greeting} /></div>
        <div className="two-fields"><div className="field"><label htmlFor="agent-hours">Business hours</label><input id="agent-hours" onChange={(event) => setHours(event.target.value)} placeholder="Monâ€“Fri, 9amâ€“5pm" value={hours} /></div><div className="field"><label>Human handoff</label><div className="toggle-row" style={{ border: 0, padding: "8px 0" }}><span className="field-hint">Enable handoff setting</span><Toggle checked={handoff} label="Toggle human handoff" onChange={setHandoff} /></div></div></div>
        <div className="placeholder-row"><FileText size={14} /><span><b>Knowledge base</b><br />Document upload will be added after secure storage and indexing are designed.</span></div>
        <div className="toggle-row"><div className="toggle-copy"><b>Agent enabled</b><small>Enable only when a connected voice transport is ready.</small></div><Toggle checked={enabled} label="Enable agent" onChange={setEnabled} /></div>
        {error && <p className="modal-error" role="alert">{error}</p>}
      </div>
      <div className="modal-footer"><span className="field-hint">No voice calls are made when you save.</span><div><button className="btn" onClick={onClose} type="button">Cancel</button><button className="btn btn-primary" disabled={saving} type="submit">{saving ? "Savingâ€¦" : "Save agent"}<ArrowRight size={12} /></button></div></div>
    </motion.form>
  </motion.div>;
}

function SignInModal({ onClose, onSuccess }: { onClose: () => void; onSuccess: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error ?? "Could not sign in.");
      onSuccess();
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : "Could not sign in.");
      setBusy(false);
    }
  };
  return <motion.div animate={{ opacity: 1 }} className="modal-scrim" exit={{ opacity: 0 }} initial={{ opacity: 0 }} onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <motion.form animate={{ opacity: 1, y: 0 }} className="agent-modal auth-modal" exit={{ opacity: 0, y: 10 }} initial={{ opacity: 0, y: 10 }} onSubmit={submit}>
      <div className="modal-head"><div><div className="eyebrow">SECURE WORKSPACE</div><h2>Sign in to Volvox</h2><p>Sign in with your Supabase account to load your real organization and agents.</p></div><button aria-label="Close" className="icon-btn" onClick={onClose} type="button"><X size={15} /></button></div>
      <div className="modal-scroll"><div className="field"><label htmlFor="login-email">Email</label><input autoComplete="username" id="login-email" onChange={(event) => setEmail(event.target.value)} required type="email" value={email} /></div><div className="field"><label htmlFor="login-password">Password</label><input autoComplete="current-password" id="login-password" onChange={(event) => setPassword(event.target.value)} required type="password" value={password} /></div>{error && <p className="modal-error" role="alert">{error}</p>}<div className="placeholder-row"><ShieldCheck size={14} /><span><b>Protected session</b><br />The access token is stored in an HttpOnly cookie and never exposed to client JavaScript.</span></div></div>
      <div className="modal-footer"><span className="field-hint">Supabase must be configured by your operator.</span><div><button className="btn" onClick={onClose} type="button">Cancel</button><button className="btn btn-primary" disabled={busy} type="submit">{busy ? "Signing inâ€¦" : "Sign in"}<ArrowRight size={12} /></button></div></div>
    </motion.form>
  </motion.div>;
}
