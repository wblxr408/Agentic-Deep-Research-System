param(
    [switch]$SkipBuild,
    [int]$ApiTimeoutSeconds = 180
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$PSNativeCommandUseErrorActionPreference = $false

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

function Write-Step {
    param([string]$Message)
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Fail-WithLogs {
    param([string]$Message)
    Write-Host $Message -ForegroundColor Red
    Write-Host ""
    Write-Host "Recent service logs:" -ForegroundColor Yellow
    docker compose logs --tail=100 db api frontend
    exit 1
}

Write-Step "Checking Docker availability"
docker version | Out-Null
docker compose version | Out-Null

if (-not (Test-Path ".env") -and (Test-Path ".env.example")) {
    Write-Host "Note: .env not found. The stack can still start, but LLM-related features may need extra configuration." -ForegroundColor Yellow
}

$composeArgs = @("compose", "up", "-d")
if (-not $SkipBuild) {
    $composeArgs += "--build"
}

Write-Step "Starting DeepIntel services"
docker @composeArgs

Write-Step "Waiting for API health endpoint"
$deadline = (Get-Date).AddSeconds($ApiTimeoutSeconds)
$apiHealthy = $false

while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 3

    $apiState = docker compose ps api --format json 2>$null
    if ($apiState -and $apiState -match '"State":"running"' -and $apiState -match '"Health":"healthy"') {
        $apiHealthy = $true
        break
    }

    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8000/api/v1/health" -UseBasicParsing -TimeoutSec 5
        if ($response.StatusCode -eq 200) {
            $apiHealthy = $true
            break
        }
    } catch {
    }
}

if (-not $apiHealthy) {
    Fail-WithLogs "DeepIntel API did not become healthy within $ApiTimeoutSeconds seconds."
}

Write-Host ""
Write-Host "DeepIntel is up." -ForegroundColor Green
Write-Host "Frontend: http://localhost:5173"
Write-Host "API:      http://localhost:8000"
Write-Host "Docs:     http://localhost:8000/docs"
Write-Host "Health:   http://localhost:8000/api/v1/health"
Write-Host "Postgres: localhost:5433"
Write-Host "Redis:    localhost:6379"
