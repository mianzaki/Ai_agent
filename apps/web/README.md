# Volvox AI dashboard

The Next.js App Router application is a local control-plane UI for the FastAPI backend. It provides Overview, My Agents, Agent Builder, Voice Playground, Calls, Analytics, and Settings sections. It does not implement browser calling, telephony, billing, or recordings.

## Install and run (Windows PowerShell)

From the repository root:

```powershell
Set-Location apps/web
npm ci
Copy-Item .env.example .env.local
npm run dev
```

The development server binds to `127.0.0.1:3000`. The API defaults to `http://127.0.0.1:8000`; set `VOLVOX_API_URL` in `.env.local` if it is elsewhere. To connect real identity, set `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` to the project's public URL and anon/publishable key. Never put a Supabase service-role key in this app. Sign-in calls Supabase Auth's password grant. The access token is stored in an HttpOnly, SameSite=Lax cookie and is sent only from the server-side proxy to FastAPI. The API independently verifies the Supabase JWT and resolves the provisioned user and organization memberships in its database.

Without valid Supabase and API configuration, the UI clearly labels sample agent configurations as Preview. Preview changes are held in browser memory and are not saved to the API. Calls, analytics, billing, and usage are shown as empty/unavailable, not generated sample results. A workspace with no organization membership has no agent write scope. Playground controls remain disabled until a real browser media transport is implemented.

## Checks

```powershell
npm ci
npm run lint
npm run typecheck
npm run build
```

The dashboard uses pinned dependencies and `package-lock.json`. This initial foundation has no browser-driven UI test suite yet. In the current restricted Windows host, Node child-process creation returns `spawn EPERM`, so Next dev and the production build's type-check subprocess could not be started here; standalone lint and TypeScript checks do run.
