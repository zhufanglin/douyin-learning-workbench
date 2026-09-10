$ErrorActionPreference = 'Stop'
$stateFile = Join-Path $PSScriptRoot 'learning_data/server.json'
if (-not (Test-Path -LiteralPath $stateFile)) { Write-Output 'No owned server record.'; exit 0 }
$serverState = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
$ownedProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $($serverState.pid)" -ErrorAction SilentlyContinue
if (-not $ownedProcess) { Write-Output 'Server already stopped.'; exit 0 }
if ($ownedProcess.CommandLine -notlike '* -m uvicorn learning.app:*' -or -not $ownedProcess.CommandLine.Contains(('"' + $PSScriptRoot + '"'))) {
    throw 'Process identity changed. Refusing to stop an unrelated process.'
}
# Only stop descendants of this verified server (its Playwright driver and browser).
$processSnapshot = @(Get-CimInstance Win32_Process)
$ownedIds = [System.Collections.Generic.List[int]]::new()
$ownedIds.Add([int]$serverState.pid)
for ($index = 0; $index -lt $ownedIds.Count; $index++) {
    foreach ($child in $processSnapshot) {
        if ($child.ParentProcessId -eq $ownedIds[$index] -and -not $ownedIds.Contains([int]$child.ProcessId)) {
            $ownedIds.Add([int]$child.ProcessId)
        }
    }
}
for ($index = $ownedIds.Count - 1; $index -ge 0; $index--) {
    $targetId = $ownedIds[$index]
    $before = $processSnapshot | Where-Object { $_.ProcessId -eq $targetId } | Select-Object -First 1
    $current = Get-CimInstance Win32_Process -Filter "ProcessId = $targetId" -ErrorAction SilentlyContinue
    if ($current -and $before -and $current.CreationDate -eq $before.CreationDate) {
        Stop-Process -Id $targetId -ErrorAction SilentlyContinue
    }
}
Write-Output 'Learning server stopped. Saved data is retained.'
