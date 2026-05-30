param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs
)

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    Write-Error "Project virtualenv python not found: $pythonExe"
    exit 1
}

& $pythonExe -m pytest @PytestArgs
exit $LASTEXITCODE
