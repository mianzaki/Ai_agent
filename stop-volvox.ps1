$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$runtimeDir = Join-Path $root ".volvox-runtime"
if (-not (Test-Path -LiteralPath $runtimeDir)) { Write-Host "No Volvox-managed processes are recorded."; exit 0 }

$processes = @(Get-CimInstance Win32_Process)
foreach ($name in @("dashboard", "api", "ollama")) {
    $pidPath = Join-Path $runtimeDir "$name.pid"
    if (-not (Test-Path -LiteralPath $pidPath)) { continue }
    $rootPid = 0
    if (-not [int]::TryParse((Get-Content -LiteralPath $pidPath -Raw).Trim(), [ref]$rootPid)) { Remove-Item -LiteralPath $pidPath -Force; continue }
    $rootProcess = $processes | Where-Object ProcessId -eq $rootPid | Select-Object -First 1
    if (-not $rootProcess) { Remove-Item -LiteralPath $pidPath -Force; continue }
    $expected = switch ($name) {
        "dashboard" { $rootProcess.CommandLine -match "npm|next|node" }
        "api" { $rootProcess.CommandLine -match "uvicorn|app\.main" }
        "ollama" { $rootProcess.Name -match "ollama" }
    }
    if (-not $expected) { Write-Warning "Recorded $name PID $rootPid no longer matches its expected command; leaving it running."; Remove-Item -LiteralPath $pidPath -Force; continue }

    $tree = [System.Collections.Generic.List[object]]::new()
    $pending = [System.Collections.Generic.Queue[object]]::new()
    $pending.Enqueue([pscustomobject]@{ Process = $rootProcess; Depth = 0 })
    while ($pending.Count -gt 0) {
        $node = $pending.Dequeue()
        $tree.Add($node)
        foreach ($child in ($processes | Where-Object ParentProcessId -eq $node.Process.ProcessId)) {
            $pending.Enqueue([pscustomobject]@{ Process = $child; Depth = $node.Depth + 1 })
        }
    }
    foreach ($node in ($tree | Sort-Object Depth -Descending)) {
        Stop-Process -Id $node.Process.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $pidPath -Force
    Write-Host "Stopped Volvox-started $name process tree (PID $rootPid)."
}
