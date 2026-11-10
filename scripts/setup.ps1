param([string]$PythonPath = "")
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path '.venv/Scripts/python.exe')) {
    if ($PythonPath) { & $PythonPath -m venv .venv }
    elseif (Get-Command py -ErrorAction SilentlyContinue) { & py -3 -m venv .venv }
    elseif (Get-Command python -ErrorAction SilentlyContinue) { & python -m venv .venv }
    else { throw 'Python 3.11+ required. Run setup.ps1 -PythonPath C:/path/to/python.exe' }
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed. Specify -PythonPath explicitly.' }
}
& .venv/Scripts/python.exe -m ensurepip --upgrade
if ($LASTEXITCODE -ne 0) { throw 'pip setup failed' }
& .venv/Scripts/python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
Write-Host 'Ready. Run: ./scripts/start.ps1'
