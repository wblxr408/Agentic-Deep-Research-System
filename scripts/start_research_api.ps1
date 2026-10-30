param(
    [int]$Port = 8000,
    [string]$LogDirectory = 'outputs/runtime'
)
$ErrorActionPreference = 'Stop'
$researchWorkspace = Split-Path -Parent $PSScriptRoot
$researchLogRoot = [System.IO.Path]::GetFullPath((Join-Path $researchWorkspace $LogDirectory))
New-Item -ItemType Directory -Path $researchLogRoot -Force | Out-Null
$researchPython = Join-Path $researchWorkspace '.venv/Scripts/python.exe'
# Runtime settings come from the existing environment/.env. Credentials never
# appear in command arguments; detaching the API also preserves its child jobs.
$researchApi = Start-Process -WindowStyle Hidden -FilePath $researchPython `
    -WorkingDirectory $researchWorkspace `
    -ArgumentList @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port',"$Port",'--no-access-log') `
    -RedirectStandardOutput (Join-Path $researchLogRoot 'api.stdout.log') `
    -RedirectStandardError (Join-Path $researchLogRoot 'api.stderr.log') -PassThru
@{pid=$researchApi.Id;port=$Port;log_directory=$researchLogRoot} | ConvertTo-Json
