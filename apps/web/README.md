# Volvox dashboard

The local dashboard has four sections: Voice Studio, AI Chat + Voice, Agents, and Settings. It has no sign-in/sign-up screen for personal localhost development. Text-to-speech uses the installed Kokoro voices; typed chat uses local Ollama.

## Start on Windows

Install dependencies once from the repository root:

```powershell
Set-Location apps/web
npm ci
Set-Location ../..
```

Then start Ollama (if needed), the FastAPI service, and the dashboard together:

```powershell
.\start-volvox.ps1
```

Open `http://127.0.0.1:3000`. Stop only the processes started by the script with `.\stop-volvox.ps1`. Logs are in `.volvox-runtime`. The local auth bypass is enabled only for development requests from loopback. Production API routes continue to require authenticated tenant membership.

For manual startup, use `.venv-api\Scripts\python.exe -m uvicorn app.main:app --app-dir services/api --host 127.0.0.1 --port 8000`. The API loads the installed Kokoro packages from `.venv312`. Then set `VOLVOX_LOCAL_DEV=true` and `VOLVOX_API_URL=http://127.0.0.1:8000` in the dashboard shell before `npm run dev` inside `apps/web`.

## Checks

```powershell
npm run lint
npm run typecheck
npm run build
```
