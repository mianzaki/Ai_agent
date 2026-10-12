# Volvox local voice conversation

## Start and stop on Windows

From a PowerShell window in the repository root:

```powershell
Set-Location C:\Users\hassa\Desktop\volvox-voice-agent
.\start-volvox.ps1
```

Open **http://127.0.0.1:3000**. Use this exact origin. Create an agent under **AI Agents**, then select it under **Voice Conversation**. Choose push-to-talk or automatic turn detection before starting. The browser must grant microphone permission for a real conversation.

```powershell
.\stop-volvox.ps1
```

The launcher starts or reuses Ollama, starts FastAPI on `127.0.0.1:8000`, and starts Next.js on `127.0.0.1:3000`. Install dashboard dependencies once with `Set-Location apps/web; npm ci`. Install the Ollama model once with `ollama pull llama3.2:3b`. If Ollama is not already running, the launcher calls `ollama serve`. Kokoro and the Pipecat voice path run **inside FastAPI**; there is no additional TTS or voice-worker process to launch.

Logs are under `.volvox-runtime`: `api.out.log`, `api.err.log`, `dashboard.out.log`, `dashboard.err.log`, `ollama.*.log` when launched by the script, and `voice-runtime.log`. The stop script only stops processes whose PIDs it recorded. The API uses ignored local SQLite when PostgreSQL is not configured; `/health/ready` still reports 503 in that development fallback.

## Local voice path

An authenticated HTTP request to `/v1/organizations/{id}/voice-session` checks tenant membership and the saved agent, then issues a one-use, 60-second WebSocket ticket. The browser sends mono 16 kHz PCM16 audio over a binary WebSocket on loopback. The server checks the exact dashboard Origin, the loopback client, the ticket, membership and agent again. It keeps the audio in memory, uses faster-whisper for transcription, the existing Pipecat/Ollama runner for a bounded contextual reply, and Kokoro ONNX for a WAV answer. Automatic mode uses Pipecat's bundled Silero VAD. The browser displays transcript and response text and provides an audio player.

Limits: one active local voice session per API worker, five minutes per session, 20 turns, 20 seconds of buffered audio per utterance, 12 history messages, 60-second ticket lifetime, 40-second STT timeout, 65-second LLM timeout, and 45-second TTS timeout. No microphone recordings or transcripts are persisted by this path. Browser playback may need a user click if autoplay is blocked.

Voice sessions are **development-only**. The production voice-ticket endpoint returns 503 pending a production media service with distributed tickets, TLS, scaling and monitoring. Production REST authentication and tenant checks remain in place. The development bypass requires a development environment and loopback API access.

## Windows and connection diagnosis

- `loudness.cp312-win_amd64.pyd` belongs to `loudness 0.2.0`, which Pipecat requires. The installed file is a 200,192-byte x64 CPython 3.12 extension and is not Authenticode signed. Earlier Windows Code Integrity events 3033 and 3077 named this extension. Current import and the text agent smoke test succeed; the exact active policy behind the earlier denial was not established. Windows security settings were not changed.
- The raw `phonemizer-fork 3.3.2` eSpeak path still fails independently: it copies `espeak-ng.dll` from `espeakng-loader 0.2.4` into a new `%TEMP%` folder and receives `PermissionError [Errno 13]` writing the copied DLL. Volvox loads the bundled DLL directly from its stable package location and successfully synthesizes fresh audio. This is separate from the `loudness` extension issue.
- The dashboard and API use `127.0.0.1` consistently. State-changing Next.js routes accept the matching origin and reject `localhost`, opaque, malformed and external origins. The backend does not enable unrestricted CORS. The dashboard calls the API through same-origin server routes; browser microphone audio uses a ticketed WebSocket. The local proxy now marks JSON bodies as `application/json`, fixing agent create/edit 422 errors.
- `API unavailable` or `The local API could not be reached` indicates the health or proxy request failed at that moment. Check both server logs and `/health/services`. Next.js previously hit `spawn EPERM` while launching a worker inside a restricted process environment; the launcher now waits for `/api/status`, and the dashboard retries workspace/status loading every 15 seconds. This does not diagnose every future disconnection.
- WSL access returned `Wsl/EnumerateDistros/Service/E_ACCESSDENIED` in this environment. No WSL runtime or LiveKit server was installed or verified. The local WebSocket transport is the tested development path.

## Verification and limits

Fresh Kokoro audio transcribed by the cached `base.en` faster-whisper model as “Hello, how are you today?” Two consecutive manual turns and one Silero-delimited automatic turn each produced an Ollama response and a valid 24 kHz WAV. A live Uvicorn/Next.js network test returned a valid WAV after receiving real generated PCM frames. A separate interruption test canceled turn 1 and returned audio only for turn 3. Origin/tenant/ticket tests cover accepted, denied and reused tickets.

Headless Edge with a **synthetic WAV fed into its fake microphone** connected to the dashboard, sent audio, displayed a real transcript and agent response, and received a WAV Blob with a valid RIFF header. That fake-microphone browser profile did not decode/play the response WAV (`readyState 0`). In a clean headless Edge profile, Voice Studio decoded generated WAV metadata (`readyState 4`); browser playback in the new conversation page remains unverified. The physical microphone check failed with PortAudio MME error `-9999` in the restricted run. An elevated physical microphone check was rejected by the automatic approval reviewer because it interpreted the earlier text-only phase as forbidding microphone access, despite this phase's attached request. No claim of physical microphone or true audible barge-in verification is made.

Performance observations are from local development only. The three synthetic-audio turns completed in about 10.55, 4.37 and 5.75 seconds after the previous turn, respectively; no CPU/GPU capacity or concurrent-session benchmark was measured. Do not extrapolate these timings to production.

## Production work remaining

- Deploy a Linux voice runtime with verified native packages and real media transport, TLS and secure origins.
- Add distributed one-use media tickets, authenticated room/session lifecycle, shared limits, token revocation and audit logs.
- Run physical microphone, browser playback, auto turn-taking and barge-in tests on real devices and networks.
- Add monitoring, alerting, load tests, capacity targets, backups, restore drills, customer-data retention/consent controls and an incident plan.
- Configure managed PostgreSQL, secret management, Supabase provisioning and production deployment checks.

Volvox voice conversation is a verified local development path, **not** a production-ready media service.
