param([switch]$NoBrowser, [ValidateRange(1024,65535)][int]$Port = 8765)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$env:PYTHONUTF8 = '1'
$dataRoot = Join-Path $projectRoot 'learning_data'
New-Item -ItemType Directory -Force -Path $dataRoot | Out-Null
$url = "http://127.0.0.1:$Port"

function Get-OwnedServer([int]$ServingId) {
    $candidate = Get-CimInstance Win32_Process -Filter "ProcessId = $ServingId" -ErrorAction SilentlyContinue
    if ($candidate -and $candidate.CommandLine -like '* -m uvicorn learning.app:*' -and $candidate.CommandLine.Contains(('"' + $projectRoot + '"'))) {
        return $candidate
    }
    return $null
}

function Save-ServerRecord([int]$ServingId) {
    @{ pid = $ServingId; port = $Port; root = $projectRoot } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $dataRoot 'server.json') -Encoding UTF8
}

# Serialize launch attempts for this project, including requests using different ports.
$sha = [System.Security.Cryptography.SHA256]::Create()
try { $projectKey = [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($projectRoot.ToLowerInvariant()))).Replace('-', '') } finally { $sha.Dispose() }
$launchMutex = [System.Threading.Mutex]::new($false, ('Local\DouyinLearning-' + $projectKey))
if (-not $launchMutex.WaitOne(0)) { $launchMutex.Dispose(); throw 'Another launch is in progress. Retry shortly.' }
try {
$recordPath = Join-Path $dataRoot 'server.json'
if (Test-Path -LiteralPath $recordPath) {
    try { $recorded = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json } catch { throw 'Invalid server record; check learning_data/server.json before starting.' }
    if (Get-OwnedServer $recorded.pid) {
        $recordedUrl = "http://127.0.0.1:$($recorded.port)"
        try { $recordedHealth = Invoke-RestMethod "$recordedUrl/api/health" -TimeoutSec 2 } catch { throw 'The recorded project process is still alive but not responding. Stop it before restarting.' }
        if ($recordedHealth.app -ne 'douyin-learning' -or $recordedHealth.pid -ne $recorded.pid) { throw 'Recorded server identity does not match the responding service.' }
        Write-Output "Already running: $recordedUrl (one instance per project)"
        if (-not $NoBrowser) { Start-Process $recordedUrl }
        exit 0
    }
}

try { $existing = Invoke-RestMethod "$url/api/health" -TimeoutSec 2 } catch { $existing = $null }
if ($existing -and $existing.app -eq 'douyin-learning') {
    if (-not (Get-OwnedServer $existing.pid)) { throw "Port $Port belongs to a different project instance." }
    Save-ServerRecord $existing.pid
    Write-Output "Already running: $url"
    if (-not $NoBrowser) { Start-Process $url }
    exit 0
}
if ($existing) { throw "Port $Port is used by another application. Choose -Port 8766." }

$sharedPython = [System.IO.Path]::GetFullPath((Join-Path $projectRoot '../../work/venv/Scripts/python.exe'))
$localPython = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (Test-Path -LiteralPath $localPython) { $pythonExe = $localPython }
elseif (Test-Path -LiteralPath $sharedPython) { $pythonExe = $sharedPython }
else {
    Write-Output 'Preparing Python environment...'
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.12 -m venv .venv
        if ($LASTEXITCODE -ne 0) { & py -3 -m venv .venv }
    } else { & python -m venv .venv }
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 or newer, then retry.' }
    $pythonExe = $localPython
    & $pythonExe -m pip install -r requirements-learning.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
}
& $pythonExe -c 'import fastapi,uvicorn,playwright,httpx'
if ($LASTEXITCODE -ne 0) { throw 'Missing dependencies. Install requirements-learning.txt in the selected environment.' }
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'api/webui/index.html'))) {
    Push-Location (Join-Path $projectRoot 'webui')
    try {
        & npm.cmd ci --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw 'npm ci failed.' }
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    } finally { Pop-Location }
}
$arguments = @('-m', 'uvicorn', 'learning.app:create_app', '--factory', '--app-dir', ('"' + $projectRoot + '"'), '--host', '127.0.0.1', '--port', "$Port")
$serverProcess = Start-Process -FilePath $pythonExe -ArgumentList $arguments -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $dataRoot 'server.out.log') -RedirectStandardError (Join-Path $dataRoot 'server.err.log')
$ready = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    if ($serverProcess.HasExited) { throw "Server exited. See $dataRoot/server.err.log" }
    try {
        $health = Invoke-RestMethod "$url/api/health" -TimeoutSec 1
        if ($health.app -eq 'douyin-learning') {
            $servingProcess = Get-OwnedServer $health.pid
            if ($servingProcess -and ($servingProcess.ProcessId -eq $serverProcess.Id -or $servingProcess.ParentProcessId -eq $serverProcess.Id)) {
                Save-ServerRecord $health.pid
                $ready = $true
                break
            }
        }
    } catch { }
    Start-Sleep -Milliseconds 300
}
if (-not $ready) { throw "Server not ready. See $dataRoot/server.err.log" }
Write-Output "Ready: $url"
Write-Output 'Data is saved in learning_data. Run stop.ps1 to stop the server.'
if (-not $NoBrowser) { Start-Process $url }
} finally {
    $launchMutex.ReleaseMutex()
    $launchMutex.Dispose()
}
