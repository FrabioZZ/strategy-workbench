param([int]$Port = 8765)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path '.venv/Scripts/python.exe')) { throw 'Run ./scripts/setup.ps1 first.' }
& .venv/Scripts/python.exe scripts/run.py --port $Port
exit $LASTEXITCODE
