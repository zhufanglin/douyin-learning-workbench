$ErrorActionPreference = 'Stop'
$pythonExe = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    $pythonExe = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../work/venv/Scripts/python.exe'))
}
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Run start.ps1 first to prepare Python.' }
& $pythonExe -m playwright install chromium --no-shell
if ($LASTEXITCODE -ne 0) { throw 'Browser installation failed. Check network access.' }
