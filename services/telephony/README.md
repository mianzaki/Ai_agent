# Volvox Telephony — Step 1 (inbound voice call)

One inbound phone call, handled entirely by **local models** (faster-whisper →
Ollama → Kokoro), streamed over **Twilio's Media Streams** protocol — with
turn-taking (VAD endpointing) and barge-in.

**Twilio is bypassable.** Nothing here needs a Twilio account to run. A local
simulator speaks the identical protocol so you can place a full call today. When
you add a number later, you only set one webhook — no code changes.

```
caller audio ─► [Twilio Media Streams WS] ─► faster-whisper ─► Ollama ─► Kokoro ─► caller
                        ▲ bypass: simulate_call.py plays this role locally
```

## Run it now (no Twilio)

Prereqs (already set up on this machine): Ollama running with the model, the
Kokoro model files in `models/`, and the Whisper model in `models/whisper/`.

```bash
# 1. start Ollama if it isn't running
ollama serve &            # then: ollama pull llama3.2:3b   (first time only)

# 2. start the telephony service
.venv312/bin/python -m uvicorn call_agent:app --app-dir services/telephony --host 127.0.0.1 --port 8080

# 3. in another terminal, place a simulated call
.venv312/bin/python services/telephony/simulate_call.py \
    --question "What services do you offer and what are your hours?"
```

The caller question is synthesized with a Kokoro voice, streamed like a real
call, and the agent's greeting + answer are saved to `last_call.wav`. The live
transcript and reply text print in the **server** log.

Dependencies: `pip install -r services/telephony/requirements.txt` (plus the
repo's `requirements-speech.txt` stack, already installed in `.venv312`).

## Latency note (important)

On **CPU**, a turn takes ~8–16s (Whisper + Ollama + Kokoro all on CPU). That is
fine to prove the loop works; it is **not** sellable latency. A small GPU — even
a rented box spun up only during calls — drops this under ~1s. This is the
expected next step once the logic is locked.

## Add Twilio later (the only third-party piece)

1. Create a Twilio account and buy a phone number (~$1/mo + ~$0.0085/min inbound).
2. Expose this service publicly so Twilio can reach it (free tunnel):
   ```bash
   cloudflared tunnel --url http://localhost:8080      # or: ngrok http 8080
   ```
   Note the public `https://<id>...` URL it prints.
3. Point the number's **Voice → "A call comes in"** webhook at:
   `https://<id>.../voice`  (HTTP POST)
4. Set the WebSocket URL the TwiML hands back:
   ```bash
   export VOLVOX_PUBLIC_WS_URL="wss://<id>.../twilio/ws"
   ```
   (or leave it unset — `/voice` derives `wss://<host>/twilio/ws` from the request).
5. Call the number and talk. Same pipeline, now over the real phone network.

Optional hardening when you go live:
`export TWILIO_VALIDATE=1 TWILIO_AUTH_TOKEN=<token>` to verify requests are
genuinely from Twilio. Off by default so local runs need no credentials.

## Configuration (env vars — all optional)

| Var | Default | Purpose |
|-----|---------|---------|
| `VOLVOX_MODEL` | `llama3.2:3b` | Ollama model (the "brain") |
| `VOLVOX_OLLAMA_URL` | `http://127.0.0.1:11434` | local Ollama |
| `VOLVOX_VOICE` / `VOLVOX_VOICE_LANG` | `af_sarah` / `en-us` | agent Kokoro voice |
| `VOLVOX_GREETING` | "Thank you for calling…" | opening line |
| `VOLVOX_SYSTEM` | receptionist prompt | agent behavior/instructions |
| `VOLVOX_MAX_TOKENS` | `120` | reply length cap (keeps it fast + spoken) |
| `VOLVOX_PUBLIC_WS_URL` | — | public `wss://` for Twilio TwiML |
| `TWILIO_VALIDATE` / `TWILIO_AUTH_TOKEN` | off | verify requests are from Twilio |

## What's next (Step 2)

Give the agent actions: a `book_appointment` tool (→ Cal.com / Google Calendar),
"take a message", and transfer-to-human. Then per-client knowledge (RAG) so it
can answer anything about a specific business.
