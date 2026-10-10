# Migration plan

1. Preserve `bot.py`, `local_speech.py`, model assets, and existing dependency inputs. Keep the existing CLI command paths valid.
2. Extract the Pipecat conversation runner into `services/voice/volvox_voice/agent.py`; retain `bot.py` as a compatibility facade and leave Windows microphone/playback helpers in the legacy CLI until a server transport is selected.
3. Introduce the FastAPI control plane with health endpoints and validated environment settings. Keep it independently installable from the Windows voice environment.
4. Add PostgreSQL models and Alembic migrations. Enforce organization ownership in schema constraints and tenant-scoped repository operations; test denial across tenants.
5. Add authentication and role policy before exposing business endpoints. Configure TLS, secret storage, rate limits, audit retention, observability, and backup/restore before production traffic.
6. Integrate API orchestration with the voice runtime in-process first; add Redis jobs only for work needing durable asynchronous retries. Keep Ollama private.
7. Validate Linux CPU inference and device/transport requirements separately. Select WebRTC or SIP transport before calling any capture path a production realtime call. Implement playback streaming, cancellation/barge-in, and echo control as a separately tested stage.

## Phase 1B continuation status (2026-10-09)

- The original `.venv312` and `.venv` were not changed. The voice CLI's text smoke and WAV-to-Whisper path pass in `.venv312`; Kokoro and the current WAV-to-LLM-to-TTS regression fail because the eSpeak native DLL cannot be written to the host's restricted temp/workspace directories. Push-to-talk was not re-run in this continuation and no live microphone result is claimed.
- A separate `.venv-api` was created; API tests report 21 passed and 2 PostgreSQL-only tests skipped. Ruff, mypy, and compileall pass. SQLite Alembic migration creates organizations, users, memberships, agents, sessions, events, and alembic_version at revision `0001_initial`.
- API process startup, liveness 200, SQLite readiness 200, PostgreSQL-default readiness 503, and unauthenticated organization request 401 were observed. The PostgreSQL integration suite was attempted against the host database on port 5432 and failed with password authentication before any schema drop. Docker Desktop named-pipe access was denied in both configured contexts, so no Compose/PostgreSQL migration was run.
- The Next.js dashboard source, API routes, login flow, and lockfile exist. Lint and TypeScript checks pass. The production build bundles successfully, then fails at Next's TypeScript worker spawn with `spawn EPERM`; the Next dev server fails at its initial child-process spawn. No HTTP/browser dashboard validation is claimed.
- A production deployment still requires PostgreSQL integration results, working Supabase project configuration and operator provisioning, session refresh, browser UI verification, Linux voice/model validation, and recording/consent, retention, metrics, backup, rate-limit, and deployment hardening.

Rollback during the foundation stage means stopping the API and continuing to run the unchanged CLI. For later schema releases, take a verified backup and roll application code forward or restore that backup; never delete tenant data to reverse a migration.
