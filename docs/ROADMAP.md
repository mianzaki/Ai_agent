# Volvox Voice Agent — Roadmap & Remaining Work

*What works today, and everything still to build to turn this into a sellable SaaS.*
*Last updated: 2026-10-14. Companion to [SAAS_PLATFORM_OPTIONS.md](SAAS_PLATFORM_OPTIONS.md) (architecture + cost options).*

---

## ✅ Working today (local, on this machine)

A full, self-hosted voice-agent demo runs end to end with **only local models** (no paid third party):

- **Dashboard** (Next.js, dark "command center" UI) — `http://127.0.0.1:3000`. Connects to the backend, shows the workspace, agents, Voice Studio, and live browser Voice Conversation. No sign-in needed in local dev.
- **API backend** (FastAPI + SQLite in dev) — `http://127.0.0.1:8000`. Multi-tenant model, agent CRUD, chat, TTS, voice-session tickets. Auto-seeds a local workspace.
- **Telephony demo** (`services/telephony/`) — `http://127.0.0.1:8080`. Speaks Twilio's Media Streams protocol; a local simulator (`simulate_call.py`) places a full call with **no Twilio account** (the bypass). Pipeline: faster-whisper → Ollama (llama3.2:3b) → Kokoro, with VAD endpointing and barge-in.
- **Models verified**: Whisper (STT), Ollama (LLM), Kokoro (TTS, 54 voices).
- **Dental clinic persona** — "Ava", a dental receptionist with clinic hours, services, insurance, booking flow, and emergency handling. Configured both as a dashboard agent and the phone persona.

### How to run everything
See [services/telephony/README.md](../services/telephony/README.md) for the call demo, and the root [README.md](../README.md) for the API + dashboard. A one-command macOS start script is a nice-to-have (not yet written).

---

## 🔜 Remaining work (prioritized)

### P0 — make it feel real
1. **Latency: move models to GPU.** CPU is ~15 s/turn (demo-only). A small GPU (even a rented box spun up during calls) drops this under ~1 s. Biggest blocker to being sellable.
2. **Real phone calls via Twilio.** The only unavoidable third party. Buy a number, run `cloudflared tunnel --url http://localhost:8080`, point the number's voice webhook at `/voice`. Code already handles it; enable `TWILIO_VALIDATE=1` + `TWILIO_AUTH_TOKEN` for production.

### P1 — make the agent *do* things (Step 2)
3. **Tools / function-calling**: `book_appointment`, `reschedule`, `cancel`, `take_message`, `transfer_to_human`, `send_sms`, `end_call`.
4. **Calendar integration**: Cal.com (self-host, free) or Google Calendar for real bookings + confirmations.
5. **Follow-ups**: scheduler (worker/cron or n8n) for reminder calls, SMS, and email.

### P2 — make it smart per client
6. **Knowledge base (RAG)**: ingest each client's docs/FAQ/website → embeddings in pgvector (reuse Postgres) → retrieve at call time, per-tenant. Lets the agent answer anything about a specific business, grounded (no hallucinated facts).
7. **Outbound calling + campaigns**: originate calls from the dashboard (lists, scheduling, retries, answering-machine detection).

### P3 — make it a product
8. **Multi-tenant routing**: map each dialed number → organization → that client's agent + knowledge.
9. **Usage metering + billing**: per-minute metering, Stripe plans, overage.
10. **Dashboard features** (includes the earlier request):
    - **Doctor and admin views**, with **client and doctor search bars**, **filters**, and their **sub-screens**.
    - Call history, transcripts, analytics (volume, resolution, handoff rate, avg duration).
11. **Agent builder depth**: per-agent voice/greeting/hours/handoff rules (partly done), prompt templates, A/B testing.

### P4 — production hardening
12. **Postgres** instead of SQLite; run the Alembic migrations; verify cross-tenant isolation on Postgres.
13. **Real auth**: Supabase sign-in/sign-up in the dashboard, token refresh, membership/roles (owner/admin/operator/viewer).
14. **Infra**: TLS ingress, rate limiting, request-size limits, secrets manager, structured metrics/alerting, backups + restore drills, Linux deploy, GPU autoscaling, concurrency/session management for many simultaneous calls.

### P5 — clinic-specific compliance (important: this handles health data)
15. **HIPAA posture**: PHI handling policy, Business Associate Agreements with any vendor that touches call data (incl. Twilio), consent + retention for recordings/transcripts, encryption at rest/in transit, access audit logs, de-identification where possible. Required before taking real patient calls in the US.

---

## ⚠️ Known limitations right now
- CPU latency (~15 s/turn); not production speed until GPU.
- SQLite dev database; no Postgres/migrations run here yet.
- No real telephony until a Twilio number is connected (simulator only).
- No booking/RAG/outbound/billing yet (planned above).
- Local dev uses an auth bypass; production auth (Supabase) not wired in the dashboard.
- Runs verified on macOS; Linux/GPU deployment unverified.

---

## 💡 Suggested next milestone
**"Step 2 + GPU"**: put the models on a small GPU and add the `book_appointment` tool wired to a calendar, so a real Twilio call to the dental clinic can book an appointment end-to-end in under ~1 s per turn. That is the first version worth demoing to a paying clinic.
