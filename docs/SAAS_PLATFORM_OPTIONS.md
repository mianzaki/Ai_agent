# Volvox AI — Voice Agent SaaS: Architecture Options, Costs & Roadmap

*Written for: you, as the product owner deciding how to build and sell this.*
*Date: 2026-10-13. All prices are approximate 2026 figures and move constantly — treat them as planning estimates and confirm each vendor's current rate card before committing. Sources are listed at the end.*

---

## 1. The verdict: is this manageable the way you're building it?

**Partly.** Your repo has two very different halves, and they deserve opposite decisions:

| Half | What it is | Keep or replace? |
|------|-----------|------------------|
| **Control plane** — Next.js dashboard, FastAPI, Supabase auth, Postgres multi-tenancy | The "SaaS shell": accounts, agents, config, billing hooks | ✅ **Keep & invest.** This is your real product and differentiator. |
| **Voice core** — local Ollama 3B + batch Whisper + Kokoro TTS, Windows, loopback only | The thing that actually talks on a call | ❌ **Replace.** Not sellable as-is (reasons below). |

### Why the current voice core can't be sold as a product
1. **No telephony.** There is no PSTN/SIP connection, so it cannot place or receive a real phone call — neither inbound nor outbound. This is the single biggest gap for your stated goal.
2. **Latency is too high.** It's a *batch* pipeline: record → transcribe the whole turn → generate the whole reply → then speak. Real voice agents *stream* all three stages and target <800ms response. The repo's own audit notes it drops microphone audio while replying (no barge-in).
3. **Won't scale.** A local 3B model on one machine serves ~1 call at a time. A SaaS needs dozens to thousands of concurrent calls — that means either a hosted platform or GPU autoscaling you'd have to operate.
4. **Windows-only audio.** `winsound`/`sounddevice` are desktop APIs, not a server call transport.
5. **No booking, no follow-ups, no outbound campaigns** — none of the business logic you need to sell exists yet.

**Bottom line:** keep the dashboard, drop the DIY local voice engine, and connect your dashboard to a *real* realtime voice stack. The rest of this doc is how, and what each way costs.

---

## 2. What a sellable voice-agent product actually needs

Every option below has to cover these six layers. The decision is really *"who operates each layer — you, or a vendor?"*

```
 ┌─────────────────────────────────────────────────────────────┐
 │ 6. YOUR DASHBOARD / CONTROL PLANE  (accounts, config, billing)│ ← you own this (your moat)
 ├─────────────────────────────────────────────────────────────┤
 │ 5. BUSINESS LOGIC  (booking, CRM, follow-up SMS, campaigns)   │ ← n8n / Make / your API
 ├─────────────────────────────────────────────────────────────┤
 │ 4. AGENT ORCHESTRATION  (turn-taking, barge-in, tools, memory)│ ← platform OR framework
 ├─────────────────────────────────────────────────────────────┤
 │ 3. THE "BRAIN"  (LLM)      2. VOICE (STT + TTS)               │ ← models
 ├─────────────────────────────────────────────────────────────┤
 │ 1. TELEPHONY  (PSTN / SIP phone numbers, inbound + outbound)  │ ← Twilio / Telnyx / platform
 └─────────────────────────────────────────────────────────────┘
```

---

## 3. The options for building the voice engine (ranked by how much *you* operate)

### Option A — Managed voice-agent platform (Vapi / Retell / Bland / Synthflow)
**You configure an agent via API; the platform runs telephony + STT + LLM + TTS + orchestration.**

- **Effort:** Lowest. Days to a working inbound+outbound agent. Your dashboard calls their API to create/update agents and read call logs.
- **Latency:** Very good — Retell advertises sub-700ms; all three are tuned for it.
- **Inbound + outbound:** Built in. Outbound campaigns, call transfer to humans, and tool/function calls for booking are first-class.
- **Cost (all-in, incl. telephony):** ~**$0.11–0.14/min** typical.
  - Vapi: $0.05/min platform fee + STT/LLM/TTS passed through at cost (or free if you bring your own keys) + telephony.
  - Retell: ~$0.07–0.13/min mainstream; voice infra $0.055/min.
  - Bland: $0.11–0.14/min incl. speech+LLM, telephony separate; higher tiers have monthly platform fees.
- **Pros:** Fastest to revenue, no infra to run, scales for you, HIPAA/compliance options on some.
- **Cons:** Per-minute margin squeeze at scale, vendor lock-in, less control over voice quality/latency internals, your margin is "resale price − their per-minute fee."
- **Choose if:** You want to launch and sell *this quarter* and validate demand before building infrastructure. **← recommended starting point.**

### Option B — Realtime framework, you host (LiveKit Agents / Pipecat Cloud) + à-la-carte models + Twilio
**You run the orchestration (open-source frameworks) and wire in your own STT/LLM/TTS and telephony.** This is the grown-up version of what `bot.py` already uses (Pipecat!).

- **Effort:** Medium–high. You assemble and operate the pipeline, but the frameworks handle turn-taking, barge-in, and transport.
- **Latency:** Excellent and *tunable* — you pick the fastest components (e.g., Cartesia TTS, Deepgram STT, a fast LLM).
- **Cost:** Framework is **free to self-host** (just infra); managed clouds are ~**$0.01/min** (LiveKit Cloud agent sessions, Pipecat Cloud) + model components + telephony. Fully-loaded DIY typically **$0.06–0.12/min**.
- **Pros:** Full control, best margins at volume, no platform lock-in, swap any component.
- **Cons:** You operate it (scaling, monitoring, on-call), more engineering.
- **Choose if:** You have real call volume and want to cut the per-minute fee, or need deep customization. **← the migration target once revenue justifies it.** Your Pipecat code is a head start.

### Option C — Speech-to-speech model (OpenAI Realtime API) + Twilio
**One model does STT+LLM+TTS natively (speech in, speech out), over a media stream from Twilio.**

- **Effort:** Medium. Fewer moving parts than B (one model instead of three), but you still own telephony glue + orchestration.
- **Latency:** Best-in-class (single model, no hand-offs).
- **Cost:** token-billed; worked examples ≈ **$0.05/min** flagship, ≈ **$0.016/min** `gpt-realtime-mini` + Twilio (~$0.0085 in / $0.014 out per min).
- **Pros:** Lowest latency, simplest pipeline, very natural turn-taking.
- **Cons:** Single-vendor (OpenAI) for the core, less control over individual voice/model swap, cost scales with conversation length.
- **Choose if:** Latency and naturalness are the top selling point and you're fine standardizing on OpenAI.

### Option D — No-code / low-code orchestration (n8n / Make) + a voice platform
**This is where n8n fits — and it is *not* the voice engine.** n8n/Make are the **business-logic and integration layer (#5)**: they receive webhooks/tool-calls from the voice platform and do the booking, CRM writes, follow-up SMS, and multi-step workflows.

- **Typical pattern (what freelancers sell today):** Vapi or Retell runs the *call*; n8n runs the *backend* — "when the agent books, create the calendar event, text a confirmation, log to the CRM, schedule a reminder call tomorrow."
- **Effort:** Low–medium, mostly visual.
- **Cost:** n8n self-hosted is **free** (open-source; your server); n8n Cloud from ~$20–50/mo; Make similar.
- **Pros:** Fast to assemble integrations, easy to change, great for appointment/follow-up logic without code.
- **Cons:** Not for sub-second voice loops; can get fragile as a *product* backbone at scale (fine as glue, risky as the whole spine). For a product you own, graduate the critical paths into your FastAPI over time.
- **Choose if:** You want to ship booking + follow-ups fast and iterate. **Great complement to Option A.**

### Option E — Fully self-host everything (today's approach, done properly)
Self-host open models (Llama/Qwen on vLLM), Whisper, Kokoro/Orpheus TTS, on your own GPUs.
- **Effort:** Highest (you're now an ML-infra company).
- **Cost:** Cheapest *per minute at very high volume*, but large fixed GPU + ops cost and real latency-engineering work.
- **Choose if:** You're at massive scale or have hard data-residency/offline requirements. **Not recommended before product-market fit.**

---

## 4. Side-by-side

| | A. Managed platform | B. Framework self-host | C. OpenAI Realtime | D. n8n + platform | E. Full self-host |
|---|---|---|---|---|---|
| Time to launch | **Days** | Weeks | 1–2 weeks | Days | Months |
| Per-minute cost | $0.11–0.14 | $0.06–0.12 | $0.05 (/$0.016 mini) + tel. | ~platform + ~free glue | lowest @ scale |
| Latency | Very good | **Best (tunable)** | **Best** | platform-bound | tunable |
| You operate infra? | No | **Yes** | Partly | Light | **Heavy** |
| Margin at scale | Lower | **High** | High | Lower | Highest |
| Lock-in | High | Low | Medium | Medium | None |
| Best for | **Launch now** | **Scale later** | Latency USP | Fast integrations | Massive scale |

---

## 5. The component menu (for Options B/C/E — à-la-carte pricing)

| Layer | Vendor / option | ~2026 price |
|---|---|---|
| **Telephony** | Twilio US inbound / outbound | $0.0085 / $0.014 per min; local # $1.15/mo; toll-free in $0.022/min |
| | Telnyx | often cheaper than Twilio; similar model |
| **STT** | Deepgram Nova-3 | ~$0.0077/min |
| | Cartesia Ink-Whisper | ~$0.0022/min (est.) |
| **LLM (brain)** | `gpt-realtime-mini` (speech-to-speech) | ~$0.016/min equiv. |
| | GPT-4o-mini / Claude Haiku / Gemini Flash (text) | ~$0.002–0.01/min of conversation |
| | Fast open models on Groq/Cerebras | very low, ultra-low latency |
| **TTS (voice)** | Cartesia Sonic | ~$0.035–0.044/min (low latency) |
| | Deepgram Aura-2 | ~$0.030/min |
| | ElevenLabs | ~$0.08/min conversational; premium higher |
| | Kokoro (self-host) | free (your compute) — *you already have this* |
| **Orchestration** | LiveKit Cloud / Pipecat Cloud | ~$0.01/min (free self-hosted) |
| **Scheduling** | Cal.com (open-source) | free self-host / ~$15/user-mo cloud |
| | Google Calendar API | free |
| **Follow-up SMS** | Twilio SMS (US) | ~$0.0079/msg + A2P 10DLC registration |
| **Automation glue** | n8n (open-source) | free self-host / ~$20–50/mo cloud |

---

## 6. How your four hard requirements get met

| Requirement | How it's delivered |
|---|---|
| **Low latency** | Streaming pipeline (Option B/C), fast components (Deepgram + Cartesia + fast LLM), speech-to-speech model (C), barge-in enabled. Target <800ms. The current batch design cannot hit this. |
| **Inbound calls** | A phone number (Twilio/Telnyx or the platform) routes incoming calls to the agent. Native in A/C; you wire it in B. |
| **Outbound calls & campaigns** | Platform outbound API (A), or Twilio outbound dial from your backend (B/C). Trigger from your dashboard or n8n ("call this list"). |
| **Answer questions about services** | **RAG** — store each client's business info/FAQ/docs in a vector store (e.g., pgvector in your existing Postgres), retrieve at call time, inject into the LLM prompt. Per-tenant isolation using your `organization_id`. |
| **Appointment booking** | LLM **tool/function call** → your API or n8n → Cal.com/Google Calendar. Confirm on the call, text a confirmation. |
| **Follow-up calls & messages** | Scheduled jobs (n8n/your worker) fire outbound calls and Twilio SMS reminders; log outcomes back to the tenant record. |

---

## 7. Recommended path (phased — launch cheap, migrate for margin)

1. **Phase 1 — Validate & sell (now):** Option **A (Retell or Vapi)** for the voice + **D (n8n)** for booking/follow-ups + **your dashboard** as the branded control plane. You can sign clients in weeks. Price per-seat or per-minute with markup.
2. **Phase 2 — Add the moat:** RAG over each client's docs (pgvector in your Postgres), outbound campaigns, analytics in your dashboard, Stripe metered billing. Still on the managed platform.
3. **Phase 3 — Cut costs at volume:** migrate the voice core to Option **B (LiveKit Agents or Pipecat)** when per-minute fees exceed the cost of operating your own pipeline. Your existing Pipecat code and Kokoro assets transfer here. Keep A as fallback/overflow.

This lets you **earn while small and save when big**, without betting the company on infra before you have customers.

---

## 8. What it takes to build each major piece (rough effort)

| Piece | Effort (solo/small team) | Notes |
|---|---|---|
| Connect dashboard → Retell/Vapi API (create agent, list calls) | 3–5 days | Replaces the local voice core in the UI |
| Inbound number + basic Q&A agent | 2–3 days | On a managed platform |
| Outbound calling + campaign UI | 1–2 weeks | List upload, scheduling, retry logic |
| Appointment booking (tool-call → Cal.com) | 3–5 days | + confirmation SMS |
| Follow-up scheduler (calls + SMS) | 1 week | n8n or a worker + cron |
| RAG knowledge base per client | 1–2 weeks | pgvector, ingest pipeline, retrieval tool |
| Stripe metered billing + usage metering | 1–2 weeks | Per-minute/seat plans |
| Dashboard redesign (pro "command center") | 3–5 days | Independent of voice backend |
| Migrate voice core to LiveKit/Pipecat (Phase 3) | 3–6 weeks | Only when volume justifies it |

---

## 9. Unit economics (worked example)

Client runs **2,000 call-minutes/month**:

| Model | Your cost | Resell at | Your margin |
|---|---|---|---|
| Option A (managed) @ ~$0.13/min | ~$260/mo | $0.35/min = $700, or flat $699/mo | ~$440/mo |
| Option B (self-host) @ ~$0.09/min | ~$180/mo | same $699/mo | ~$520/mo |

Plus SaaS platform fee (e.g., $199–499/mo per client) on top. Margins improve as you move toward Option B at volume. The dashboard + integrations are what justify the platform fee — not the per-minute voice, which is a commodity.

---

## 10. Repo cleanup & structure (what's redundant)

**Current issues:** prototype smoke scripts and generated artifacts are mixed into the repo root; a `.bak` dead file; build caches committed.

| Path | Action | Why |
|---|---|---|
| `bot.py.bak` | **Remove** | Dead older-API copy; the repo's own audit calls it inactive. |
| `test_conversation.py`, `test_stt.py`, `test_tts.py`, `test_vad.py` (root) | **Move → `scripts/smoke/`** | Manual prototype smoke tools; keep but separate from the real `tests/` suite. |
| `artifacts/*.wav` | **Remove + gitignore** | Generated audio output, shouldn't be versioned. |
| `apps/web/tsconfig.tsbuildinfo` | **Remove + gitignore** | Build cache. |
| `apps/web/.env.local` | **Untrack if tracked** | Local secrets must never be committed. |
| `play_wav.py`, `local_speech.py` | Keep (move to `services/voice/` later) | Still used by the CLI. |

**Target structure (where it's heading):**
```
apps/web/            # dashboard (your product)
services/api/        # FastAPI control plane  ← add: voice-platform adapter, RAG, billing
services/voice/      # Pipecat runtime (Phase-3 self-host target)
packages/shared/     # cross-language contracts
scripts/smoke/       # manual prototype tools (moved out of root)
infra/               # compose, deploy
docs/                # architecture, this file, migration
```

---

## 11. Decisions I need from you

1. **Which voice path for Phase 1** — Retell (lowest latency, recommended), Vapi (most flexible/BYO-keys), or Bland (simple outbound)? I recommend **Retell**.
2. **Managed vs. go straight to self-host** — I strongly recommend starting managed (Option A) and migrating later (B). Only skip to B if you already have volume.
3. **Spend** — managed platforms and OpenAI Realtime cost real money per minute and need API keys/accounts in your name. Nothing in Phase 1 is free.

---

## Sources (approximate 2026 pricing — verify before committing)
- Vapi / Retell / Bland comparisons: [Lindy](https://www.lindy.ai/blog/vapi-ai), [CloudTalk](https://www.cloudtalk.io/retell-ai-vs-vapi-ai/), [StackBinary](https://stackbinary.io/insights/voice-ai-pricing-per-minute-2026), [Aliteq](https://aliteq.com/ai-voice-agent-cost-per-minute-2026)
- Twilio / Deepgram / ElevenLabs / Cartesia: [caller.digital](https://caller.digital/voice-ai-pricing-comparison), [edesy Twilio guide](https://edesy.in/blog/twilio-voice-pricing-guide-2026), [Ringlyn](https://www.ringlyn.com/blog/ai-voice-agent-pricing-per-minute-2026/)
- OpenAI Realtime: [OpenAI pricing](https://developers.openai.com/api/docs/pricing), [Forasoft](https://www.forasoft.com/blog/article/openai-realtime-api-pricing), [Layer3Labs](https://www.layer3labs.io/guides/openai-realtime-api-pricing)
- LiveKit / Pipecat: [Forasoft Pipecat vs LiveKit](https://www.forasoft.com/blog/article/pipecat-vs-livekit-agents), [futureagi](https://futureagi.com/blog/livekit-alternatives-2026/)
- n8n + voice pattern: [futureagi booking tools](https://futureagi.com/blog/best-ai-appointment-booking-voice-tools-2026/)
