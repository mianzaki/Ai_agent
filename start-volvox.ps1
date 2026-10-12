[CmdletBinding()]
param(
    [switch]$NoDashboard,
    [switch]$NoOllama
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$runtimeDir = Join-Path $root ".volvox-runtime"
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
$kokoroModel = Join-Path $root "models\kokoro-v1.0.onnx"
$kokoroVoices = Join-Path $root "models\voices-v1.0.bin"
if (-not (Test-Path -LiteralPath $kokoroModel) -or -not (Test-Path -LiteralPath $kokoroVoices)) {
    throw "Kokoro model assets are missing from models/. Restore kokoro-v1.0.onnx and voices-v1.0.bin before starting Volvox."
}
$whisperCache = Join-Path $root "models\whisper"
if (-not (Test-Path -LiteralPath $whisperCache) -or -not (Get-ChildItem -LiteralPath $whisperCache -Recurse -File -Filter "model.bin" -ErrorAction SilentlyContinue | Select-Object -First 1)) {
    Write-Warning "The local Whisper base.en checkpoint is missing. Voice Conversation will report unavailable until it is installed."
}

function Test-LocalPort([int]$Port) {
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $pending = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        if (-not $pending.AsyncWaitHandle.WaitOne(300)) { return $false }
        $client.EndConnect($pending)
        return $true
    } catch { return $false }
    finally { $client.Dispose() }
}

function Start-VolvoxProcess([string]$Name, [string]$File, [string[]]$Arguments, [string]$WorkingDirectory) {
    $stdout = Join-Path $runtimeDir "$Name.out.log"
    $stderr = Join-Path $runtimeDir "$Name.err.log"
    $process = Start-Process -FilePath $File -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    Set-Content -LiteralPath (Join-Path $runtimeDir "$Name.pid") -Value $process.Id -Encoding ascii
    Write-Host "Started $Name (PID $($process.Id)); logs: $stdout"
}

if (-not $NoOllama) {
    $ollamaReady = $false
    try { $ollamaReady = (Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 2) -ne $null } catch { }
    if ($ollamaReady) {
        Write-Host "Ollama is already running at http://127.0.0.1:11434"
    } else {
        $ollama = Get-Command ollama -ErrorAction SilentlyContinue
        if (-not $ollama) { throw "Ollama is not running and 'ollama.exe' is not on PATH. Install Ollama or start it manually, then run this script again." }
        Start-VolvoxProcess "ollama" $ollama.Source @("serve") $root
        $deadline = (Get-Date).AddSeconds(30)
        do {
            Start-Sleep -Milliseconds 500
            try { $ollamaReady = (Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 2) -ne $null } catch { }
        } while (-not $ollamaReady -and (Get-Date) -lt $deadline)
        if (-not $ollamaReady) { throw "Ollama did not become ready. Check .volvox-runtime/ollama.err.log." }
    }
    try {
        $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 3
        if ($tags.models.name -notcontains "llama3.2:3b") { Write-Warning "Ollama is running but llama3.2:3b is missing. Run: ollama pull llama3.2:3b" }
    } catch { Write-Warning "Could not inspect installed Ollama models." }
}

$apiListening = Test-LocalPort 8000
if ($apiListening) {
    try {
        $apiHealth = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health/live" -TimeoutSec 2
        if ($apiHealth.status -ne "alive") { throw "unexpected health response" }
    } catch { throw "Port 8000 is in use by a service that is not the Volvox API." }
    try {
        $localOrganizations = @(Invoke-RestMethod -Uri "http://127.0.0.1:8000/v1/organizations" -Headers @{ Authorization = "Bearer local-development" } -TimeoutSec 3)
        if (-not $localOrganizations.Count) { throw "No personal workspace is provisioned." }
    } catch { throw "The existing API is not configured for the local development identity. Stop it and rerun this script, or start it with VOLVOX_LOCAL_DEV_AUTH_BYPASS=true." }
}
if (-not $apiListening) {
    $python = Join-Path $root ".venv312\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $python)) { throw "Python environment not found: $python" }
    & $python -c "import fastapi, sqlalchemy, faster_whisper, kokoro_onnx, pipecat; from pipecat.audio.vad.silero import SileroVADAnalyzer"
    if ($LASTEXITCODE -ne 0) { throw "The voice API environment is incomplete. Install services/api/requirements.in and requirements-speech.txt into .venv312." }
    $env:VOLVOX_ENVIRONMENT = "development"
    $env:VOLVOX_LOCAL_DEV_AUTH_BYPASS = "true"
    $env:VOLVOX_DATABASE_URL = "postgresql+psycopg://volvox:volvox@localhost:5432/volvox"
    $env:VOLVOX_API_BIND_HOST = "127.0.0.1"
    $env:VOLVOX_API_BIND_PORT = "8000"
    $env:VOLVOX_OLLAMA_HOST = "http://127.0.0.1:11434"
    $env:VOLVOX_CHAT_MODEL = "llama3.2:3b"
    $env:VOLVOX_VOICE_LOG_PATH = Join-Path $runtimeDir "voice-runtime.log"
    Start-VolvoxProcess "api" $python @("-m", "uvicorn", "app.main:app", "--app-dir", "services/api", "--host", "127.0.0.1", "--port", "8000") $root
    $deadline = (Get-Date).AddSeconds(60)
    $apiReady = $false
    do {
        Start-Sleep -Milliseconds 500
        try { $apiReady = (Invoke-RestMethod -Uri "http://127.0.0.1:8000/health/live" -TimeoutSec 2).status -eq "alive" } catch { }
    } while (-not $apiReady -and (Get-Date) -lt $deadline)
    if (-not $apiReady) { throw "FastAPI did not become ready. Check .volvox-runtime/api.err.log." }
} else { Write-Host "FastAPI is already listening at http://127.0.0.1:8000" }

if (-not $NoDashboard) {
    $dashboardListening = Test-LocalPort 3000
    if ($dashboardListening) {
        try {
            $dashboardStatus = Invoke-RestMethod -Uri "http://127.0.0.1:3000/api/status" -TimeoutSec 3
            if ($null -eq $dashboardStatus.api) { throw "unexpected status response" }
        } catch { throw "Port 3000 is in use by a service that is not the Volvox dashboard." }
    }
    if (-not $dashboardListening) {
        $webDir = Join-Path $root "apps\web"
        if (-not (Test-Path (Join-Path $webDir "node_modules"))) { throw "Dashboard dependencies are missing. Run 'npm ci' in apps/web once." }
        $cmd = $env:ComSpec
        $env:VOLVOX_LOCAL_DEV = "true"
        $env:VOLVOX_API_URL = "http://127.0.0.1:8000"
        Start-VolvoxProcess "dashboard" $cmd @("/d", "/c", "npm.cmd run dev") $webDir
        $deadline = (Get-Date).AddSeconds(45)
        $dashboardReady = $false
        do {
            Start-Sleep -Milliseconds 500
            try { $dashboardReady = $null -ne (Invoke-RestMethod -Uri "http://127.0.0.1:3000/api/status" -TimeoutSec 2).api } catch { }
        } while (-not $dashboardReady -and (Get-Date) -lt $deadline)
        if (-not $dashboardReady) { throw "Next.js did not become ready. Check .volvox-runtime/dashboard.err.log." }
    } else { Write-Host "Dashboard is already listening at http://127.0.0.1:3000" }
}

Write-Host ""
Write-Host "Volvox Voice Studio: http://127.0.0.1:3000"
Write-Host "FastAPI health:      http://127.0.0.1:8000/health/live"
Write-Host "API voices:          http://127.0.0.1:8000/v1/voices"
Write-Host "Stop only processes started by this script: .\stop-volvox.ps1"
