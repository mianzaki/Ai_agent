# Volvox voice agent

This repository keeps the original Windows local agent runnable while adding a local FastAPI control plane and a Next.js dashboard foundation. The API and dashboard are not production-ready: deployment hardening, secret lifecycle, rate limiting, external identity provisioning, monitoring, and restore drills remain necessary.

## Existing voice prototype (Windows)

Keep using the existing Python 3.12 environment and instructions in [SETUP.md](SETUP.md). Examples:

```powershell
.\.venv312\Scripts\python.exe .\bot.py --mode text --smoke-test
.\.venv312\Scripts\python.exe .\bot.py --mode push-to-talk
.\.venv312\Scripts\python.exe .\bot.py --mode realtime
```

The local Ollama server and `llama3.2:3b` model must be installed. Do not expose Ollama's port publicly. `bot.py` remains the CLI entry point; its reusable Pipecat runner now lives in `services/voice/volvox_voice/agent.py`.

## API development (Python 3.12)

```powershell
py -3.12 -m venv .venv-api
.\.venv-api\Scripts\python.exe -m pip install -r services/api/requirements.lock
$env:PYTHONPATH = (Resolve-Path services/api).Path
\.venv-api\Scripts\uvicorn.exe app.main:app --app-dir services/api --host 127.0.0.1 --port 8000
```

Health routes: `GET /health/live` and `GET /health/ready`. Readiness performs `SELECT 1` and returns 503 when the configured database is unreachable. Copy `.env.example` to `services/api/.env` and fill local PostgreSQL credentials before starting. For local iteration without Docker, set `VOLVOX_DATABASE_URL` to an absolute SQLite URL, for example `sqlite:///C:/Users/you/volvox-local.db`; SQLite is for local development only. Alembic reads `VOLVOX_DATABASE_URL` directly when provided.

Start a local database, then run migration from the API directory:

```powershell
$env:POSTGRES_PASSWORD = 'local-development-password'
$env:VOLVOX_APP_SECRET = 'a-local-secret-at-least-32-characters-long'
docker compose -f infra/compose.yaml up -d postgres
$env:VOLVOX_DATABASE_URL = "postgresql+psycopg://volvox:$($env:POSTGRES_PASSWORD)@localhost:5432/volvox"
Push-Location services/api
..\..\.venv-api\Scripts\alembic.exe upgrade head
Pop-Location
```

Supabase JWT verification uses RS256/ES256 keys from JWKS, validates issuer/audience and required `sub`, `exp`, `iat`, and caches the JWKS set for five minutes. Configure `VOLVOX_SUPABASE_URL`, or explicit `VOLVOX_SUPABASE_JWT_ISSUER` and `VOLVOX_SUPABASE_JWKS_URL`. It makes no network call until a token is verified. Legacy HS256 is disabled by default and rejected in production; the opt-in is for a controlled local migration only. User IDs and memberships are loaded from the database. Tests use generated keys and local database fixtures without contacting Supabase.

## Container development

Docker is optional and unrelated to the original Windows CLI. With Docker Compose available, set `POSTGRES_PASSWORD` and `VOLVOX_APP_SECRET` in the shell and run `docker compose -f infra/compose.yaml up --build`. The API is bound to host loopback. The Ollama container is opt-in under the `inference` profile and is not exposed on a host port. Compose is a development configuration, not a hardened production deployment. For text inference, start Ollama with `docker compose -f infra/compose.yaml --profile inference up -d ollama`, then pull the desired model inside that private container.

## Checks

From repository root, run the API checks:

```powershell
.\.venv-api\Scripts\ruff.exe check services/api/app services/api/alembic tests
.\.venv-api\Scripts\mypy.exe services/api/app
$env:PYTHONPATH = (Resolve-Path services/api).Path
.\.venv-api\Scripts\pytest.exe -q -p no:cacheprovider tests
```

Set `VOLVOX_TEST_DATABASE_URL` to a disposable PostgreSQL database to enable migration and PostgreSQL lifecycle tests; those tests drop/recreate its `public` schema. Without that variable, SQLite-backed API tests run and the PostgreSQL cases skip.

For a disposable local database in PowerShell:

```powershell
$env:POSTGRES_PASSWORD = 'local-development-password'
docker compose -f infra/compose.yaml up -d postgres
$env:VOLVOX_TEST_DATABASE_URL = "postgresql+psycopg://volvox:$($env:POSTGRES_PASSWORD)@localhost:5432/volvox"
$env:PYTHONPATH = (Resolve-Path services/api).Path
.\.venv-api\Scripts\pytest.exe -q -p no:cacheprovider tests/test_postgres_integration.py
```

The integration suite intentionally drops and recreates the configured database's `public` schema. Point it only at a disposable local test DB. The integration migration test expects an empty database. The current session generated PostgreSQL migration SQL offline but did not apply it because Docker/PostgreSQL was unavailable.

The repository's existing smoke scripts use local Ollama, model files, or microphone hardware and are not part of GPU-independent CI. CI checks the API and schema only.

## Dashboard (Next.js, Node.js)

The dashboard lives in [apps/web](apps/web/README.md), uses Next.js App Router, and calls the API through server routes. Start the API first, then in another PowerShell terminal:

```powershell
Set-Location apps/web
npm ci
Copy-Item .env.example .env.local
npm run dev
```

The UI is available at `http://127.0.0.1:3000`. Supabase URL and anon/publishable key are required for real sign-in; no credentials are checked in. Without a connected identity/API, the dashboard presents explicitly labeled preview agent configurations and does not invent call, usage, or billing data. See `apps/web/README.md` for the authentication flow and limitations.

Dashboard checks:

```powershell
Set-Location apps/web
npm ci
npm run lint
npm run typecheck
npm run build
```

The API startup and migration were verified with local SQLite because this host's Docker engine is inaccessible. Do not treat SQLite validation as the PostgreSQL integration run; the PostgreSQL migration and two destructive-schema integration tests remain pending. The current host also returns `spawn EPERM` when Node attempts to start a child process, blocking Next dev/build runtime here.

## Operations, security, and rollback

- Keep model services on private networks; terminate TLS and apply authentication, authorization, rate limiting, and request-size limits before exposing the API.
- Every organization-owned read/write must use the authenticated principal's organization ID. The schema uses composite foreign keys to block cross-tenant agent/session/event relationships; verify these on PostgreSQL before launch.
- Recordings are not stored by the new schema. Define explicit consent and retention before adding them.
- Store production secrets in a secret manager or protected deployment environment. `.env` is ignored by Git.
- Back up PostgreSQL, test restores, monitor migration rollout, and roll forward or restore a verified backup. During this initial stage, rollback is stopping the API and using the unchanged CLI.
- See [architecture](docs/architecture.md) for audit and gaps and [migration plan](docs/migration.md) for staged rollout.

## Current limitations

No Redis jobs, metering, billing, telephony, recording, production metrics, external Supabase provisioning/webhook, browser media transport, or Linux voice validation has been delivered. The dashboard provides Supabase password login but does not manage users; an operator must provision the matching `auth_subject` in `users` before API access. Supabase token refresh is not implemented in the dashboard session. The checked-in Python dependency lock contains resolved version pins but is not hash-locked; generate a hash-enforced release lock and validate platform wheels before production use. PostgreSQL constraints and the cross-tenant tests must still be run against PostgreSQL before launch.
