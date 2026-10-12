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

FastAPI runs in `.venv-api`; its TTS service loads the existing Kokoro packages and model assets from `.venv312`, so no duplicate model install is needed.

```powershell
$env:PYTHONPATH = (Resolve-Path services/api).Path
$env:VOLVOX_ENVIRONMENT = "development"
$env:VOLVOX_LOCAL_DEV_AUTH_BYPASS = "true"
\.venv-api\Scripts\python.exe -m uvicorn app.main:app --app-dir services/api --host 127.0.0.1 --port 8000
```

Apply the schema migration before using saved presets:

```powershell
$env:PYTHONPATH = (Resolve-Path services/api).Path
\.venv-api\Scripts\alembic.exe -c services/api/alembic.ini upgrade head
```

For your private local dashboard, set `$env:VOLVOX_ENVIRONMENT="development"` and `$env:VOLVOX_LOCAL_DEV_AUTH_BYPASS="true"` before API startup. The API creates an ignored `.volvox-local.db` with your personal workspace. No dashboard sign-in is shown or required. The bypass only accepts loopback requests in development; production API routes continue to require Supabase authentication and tenant membership.

Start Ollama locally and load the model:

```powershell
ollama serve
ollama pull llama3.2:3b
```

The Voice Studio uses `POST /v1/organizations/{organization_id}/speech` and returns `audio/wav`; typed chat uses local Ollama at `http://127.0.0.1:11434`. No microphone or media transport is used.

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

The repository's existing voice-agent smoke command uses local Ollama and native Python dependencies; it is separate from the API test suite.

## Dashboard (Next.js, Node.js)

The dashboard lives in [apps/web](apps/web/README.md), uses Next.js App Router, and calls the API through same-origin server routes. Start the API first, then in another PowerShell terminal:

```powershell
Set-Location apps/web
npm ci
$env:VOLVOX_LOCAL_DEV = "true"
$env:VOLVOX_API_URL = "http://127.0.0.1:8000"
npm run dev
```

### One-command localhost startup (Windows)

Install dashboard dependencies once with `Set-Location apps/web; npm ci`, then return to the repository root and run:

```powershell
Set-Location C:\Users\hassa\Desktop\volvox-voice-agent
.\start-volvox.ps1
```

The script checks for existing local services, starts Ollama if needed, launches FastAPI with `.venv-api` (which loads the installed Kokoro packages from `.venv312`), and starts Next.js. It keeps all listeners on loopback and enables the isolated auth bypass only for development. Dashboard URL: `http://127.0.0.1:3000`. Stop only the process trees started by the script with `.\stop-volvox.ps1`; logs and PID records are stored in the ignored `.volvox-runtime` directory. If the model is missing, install it with `ollama pull llama3.2:3b` before chatting. To start without a dashboard, run `.\start-volvox.ps1 -NoDashboard`.

The UI is available at `http://127.0.0.1:3000`. Local personal development uses a private localhost-only identity and does not need Supabase. Production API routes continue to require verified tokens and tenant membership. Calls and analytics are omitted from the active text-first interface.

Dashboard checks:

```powershell
Set-Location apps/web
npm ci
npm run lint
npm run typecheck
npm run build
```

For the isolated local browser demo, set `VOLVOX_ENVIRONMENT=development` and `VOLVOX_LOCAL_DEV_AUTH_BYPASS=true` in the API terminal before startup. The API provisions one local owner/workspace in the ignored `.volvox-local.db`; the bypass accepts only loopback requests in development.

The API and tests were verified against local SQLite; PostgreSQL integration remains separate. The Next.js production build and dashboard lint/type checks pass.

## Operations, security, and rollback

- Keep model services on private networks; terminate TLS and apply authentication, authorization, rate limiting, and request-size limits before exposing the API.
- Every organization-owned read/write must use the authenticated principal's organization ID. The schema uses composite foreign keys to block cross-tenant agent/session/event relationships; verify these on PostgreSQL before launch.
- Recordings are not stored by the new schema. Define explicit consent and retention before adding them.
- Store production secrets in a secret manager or protected deployment environment. `.env` is ignored by Git.
- Back up PostgreSQL, test restores, monitor migration rollout, and roll forward or restore a verified backup. During this initial stage, rollback is stopping the API and using the unchanged CLI.
- See [architecture](docs/architecture.md) for audit and gaps and [migration plan](docs/migration.md) for staged rollout.

## Current limitations

No Redis jobs, metering, billing, telephony, recording, production metrics, browser media transport, or Linux voice validation has been delivered. The dashboard has no sign-in/sign-up screen for local use; production API routes still require verified tokens, provisioned users, and tenant membership. Supabase token refresh is not implemented in the dashboard session. The checked-in Python dependency lock contains resolved version pins but is not hash-locked; generate a hash-enforced release lock and validate platform wheels before production use. PostgreSQL constraints and the cross-tenant tests must still be run against PostgreSQL before launch.
