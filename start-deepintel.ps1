param(
    [ValidateSet("docker", "local")]
    [string]$Mode = "docker",
    [switch]$Build,
    [switch]$SkipBuild,
    [switch]$SkipFrontend,
    [switch]$SkipDbChecks,
    [int]$ApiTimeoutSeconds = 180
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$PSNativeCommandUseErrorActionPreference = $false

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

function Write-Step {                                                       param([string]$Message)
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Invoke-Compose {
    param([string[]]$Arguments)

    & docker @Arguments | Out-Host
    return $LASTEXITCODE
}

function Test-CommandExists {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Test-PythonModule {
    param(
        [string]$PythonExe,
        [string]$ModuleName
    )

    & $PythonExe -c "import $ModuleName" | Out-Null
    return $LASTEXITCODE -eq 0
}

function Resolve-LocalPython {
    $preferredPython = $env:DEEPINTEL_PYTHON
    if ($preferredPython -and (Test-Path $preferredPython)) {
        return $preferredPython
    }

    $condaPython = "C:\Users\wblxr\anaconda3\envs\used_pytorch\python.exe"
    if (Test-Path $condaPython) {
        return $condaPython
    }

    $venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }

    if (Test-CommandExists "python") {
        return (Get-Command python).Source
    }

    throw "python is required for local mode."
}

function Test-ModuleInstalled {
    param(
        [string]$PythonExe,
        [string]$ModuleName
    )

    return Test-PythonModule -PythonExe $PythonExe -ModuleName $ModuleName
}

function Resolve-NpmCommand {
    $npmCmd = Get-Command "npm.cmd" -ErrorAction SilentlyContinue
    if ($npmCmd) {
        return $npmCmd.Source
    }

    $npmExe = Get-Command "npm" -ErrorAction SilentlyContinue
    if ($npmExe -and $npmExe.CommandType -eq "Application") {
        return $npmExe.Source
    }

    if ($npmExe) {
        return $npmExe.Source
    }

    throw "npm is required for local frontend startup."
}

function Test-PortInUse {
    param([int]$Port)

    try {
        $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction Stop
        return [bool]$connections
    } catch {
        return $false
    }
}

function Test-HttpOk {
    param(
        [string]$Uri,
        [int]$TimeoutSeconds = 3
    )

    try {
        $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec $TimeoutSeconds
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    } catch {
        return $false
    }
}

function Try-Remove-File {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        return
    }

    try {
        Remove-Item $Path -Force
    } catch {
        Write-Host "Warning: cannot remove $Path because it is in use; reusing existing log." -ForegroundColor Yellow
    }
}

function Wait-ForTcpPort {
    param(
        [string]$HostName,
        [int]$Port,
        [int]$TimeoutSeconds = 120
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            if (Test-NetConnection -ComputerName $HostName -Port $Port -InformationLevel Quiet) {
                return $true
            }
        } catch {
        }
        Start-Sleep -Seconds 2
    }

    return $false
}

function Ensure-DockerInfrastructure {
    param(
        [switch]$BuildImages
    )

    Write-Step "Checking Docker availability"
    docker version | Out-Null
    docker compose version | Out-Null

    Write-Step "Starting database and Redis"
    $composeArgs = @("compose", "up", "-d")
    if ($BuildImages) {
        $composeArgs += @("--build")
    } else {
        $composeArgs += @("--no-build")
    }
    $composeArgs += @("db", "redis")
    $exitCode = Invoke-Compose -Arguments $composeArgs
    if ($exitCode -ne 0) {
        throw "docker compose failed to start db/redis."
    }

    Write-Step "Waiting for database port"
    if (-not (Wait-ForTcpPort -HostName "localhost" -Port 5433 -TimeoutSeconds 120)) {
        throw "Database did not become reachable on localhost:5433."
    }

    Write-Step "Waiting for Redis port"
    if (-not (Wait-ForTcpPort -HostName "localhost" -Port 6379 -TimeoutSeconds 120)) {
        throw "Redis did not become reachable on localhost:6379."
    }
}

function Stop-DockerAppServices {
    Write-Step "Stopping Docker api/frontend to free local ports"
    try {
        & docker compose stop api frontend | Out-Host
    } catch {
        Write-Host "Warning: failed to stop docker api/frontend services: $_" -ForegroundColor Yellow
    }
}

function Set-LocalRuntimeEndpoints {
    $env:DATABASE_URL = "postgresql://deepintel:deepintel_secret@127.0.0.1:5433/deepintel"
    $env:REDIS_URL = "redis://127.0.0.1:6379/0"
}

function Start-LocalService {
    param(
        [string]$Name,
        [string[]]$Command,
        [string]$LogPath,
        [string]$WorkingDirectory = $repoRoot
    )

    if (Test-Path $LogPath) {
        Try-Remove-File -Path $LogPath
    }

    $errorLogPath = "${LogPath}.err"
    if (Test-Path $errorLogPath) {
        Try-Remove-File -Path $errorLogPath
    }

    return Start-Process -FilePath $Command[0] -ArgumentList $Command[1..($Command.Count - 1)] -WorkingDirectory $WorkingDirectory -WindowStyle Hidden -RedirectStandardOutput $LogPath -RedirectStandardError $errorLogPath -PassThru
}

function Fail-WithLogs {
    param(
        [string]$Message,
        [string]$Mode = "docker",
        [string]$BackendLogPath = "",
        [string]$FrontendLogPath = ""
    )

    Write-Host $Message -ForegroundColor Red
    Write-Host ""
    Write-Host "Recent service logs:" -ForegroundColor Yellow
    if ($Mode -eq "local") {
        foreach ($logPath in @($BackendLogPath, $FrontendLogPath)) {
            if ($logPath -and (Test-Path $logPath)) {
                Write-Host ""
                Write-Host "==> $logPath" -ForegroundColor Cyan
                Get-Content $logPath -Tail 100

                $errorLogPath = "${logPath}.err"
                if (Test-Path $errorLogPath) {
                    Write-Host ""
                    Write-Host "==> $errorLogPath" -ForegroundColor Cyan
                    Get-Content $errorLogPath -Tail 100
                }
            }
        }
    } else {
        docker compose logs --tail=100 db api frontend
    }
    exit 1
}

if (-not (Test-Path ".env") -and (Test-Path ".env.example")) {
    Write-Step "Creating .env from .env.example"
    Copy-Item ".env.example" ".env"
}

if ($Build -and $SkipBuild) {
    throw "Use either -Build or -SkipBuild, not both."
}

$envContent = if (Test-Path ".env") { Get-Content ".env" -Raw } else { "" }
if ($envContent -match "(?m)^LLM_API_KEY\s*=\s*$") {
    Write-Host "Warning: LLM_API_KEY is empty. Research tasks will fail until you fill it." -ForegroundColor Yellow
}

if ($Mode -eq "docker") {
    Ensure-DockerInfrastructure -BuildImages:($Build -or (-not $SkipBuild))

    if ($Build) {
        Write-Step "Starting DeepIntel services with rebuild"
        $exitCode = Invoke-Compose -Arguments @("compose", "up", "-d", "--build")
    } elseif ($SkipBuild) {
        Write-Step "Starting DeepIntel services without rebuild"
        $exitCode = Invoke-Compose -Arguments @("compose", "up", "-d", "--no-build")
    } else {
        Write-Step "Starting DeepIntel services with rebuild to avoid stale images"
        $exitCode = Invoke-Compose -Arguments @("compose", "up", "-d", "--build")
    }

    if ($exitCode -ne 0) {
        Write-Host "Warning: docker compose returned exit code $exitCode. Continuing with health checks." -ForegroundColor Yellow
    }

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
        Fail-WithLogs -Message "DeepIntel API did not become healthy within $ApiTimeoutSeconds seconds." -Mode $Mode
    }
} else {
    Write-Step "Starting local services"
    Stop-DockerAppServices
    Set-LocalRuntimeEndpoints
    $pythonExe = Resolve-LocalPython
    if (-not $SkipDbChecks) {
        if (-not (Wait-ForTcpPort -HostName "localhost" -Port 5433 -TimeoutSeconds 15)) {
            Ensure-DockerInfrastructure -BuildImages:$false
        }
    }

    $backendLog = Join-Path $repoRoot "backend.local.log"
    $frontendLog = Join-Path $repoRoot "frontend.local.log"
    $requiredModules = @("asyncpg", "fastapi", "uvicorn", "sse_starlette", "structlog", "pydantic", "redis", "openai", "langgraph", "torch", "sentence_transformers", "transformers", "accelerate", "playwright")
    $missingModules = @()
    foreach ($module in $requiredModules) {
        if (-not (Test-ModuleInstalled -PythonExe $pythonExe -ModuleName $module)) {
            $missingModules += $module
        }
    }

    $venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"

    if ($missingModules.Count -gt 0) {
        if (-not (Test-Path $venvPython)) {
            Write-Step "Creating local virtual environment"
            & $pythonExe -m venv .venv
            if ($LASTEXITCODE -ne 0) {
                Fail-WithLogs -Message "Failed to create .venv." -Mode $Mode -BackendLogPath $backendLog -FrontendLogPath $frontendLog
            }
            $pythonExe = $venvPython
        }

        Write-Step "Installing backend dependencies into local venv"
        & $pythonExe -m pip install --upgrade pip
        if ($LASTEXITCODE -ne 0) {
            Fail-WithLogs -Message "Failed to upgrade pip in local venv." -Mode $Mode -BackendLogPath $backendLog -FrontendLogPath $frontendLog
        }
        & $pythonExe -m pip install -r requirements-local.txt
        if ($LASTEXITCODE -ne 0) {
            Fail-WithLogs -Message ("Failed to install backend dependencies: " + ($missingModules -join ", ")) -Mode $Mode -BackendLogPath $backendLog -FrontendLogPath $frontendLog
        }
    } elseif (Test-Path $venvPython) {
        $pythonExe = $venvPython
    }

    $startupChecks = @("asyncpg", "fastapi", "uvicorn", "sse_starlette", "structlog", "pydantic", "redis", "openai", "langgraph", "torch", "sentence_transformers", "transformers", "accelerate", "playwright")
    $stillMissing = @()
    foreach ($module in $startupChecks) {
        if (-not (Test-ModuleInstalled -PythonExe $pythonExe -ModuleName $module)) {
            $stillMissing += $module
        }
    }
    if ($stillMissing.Count -gt 0) {
        Fail-WithLogs -Message ("Local backend dependencies are still missing: " + ($stillMissing -join ", ")) -Mode $Mode -BackendLogPath $backendLog -FrontendLogPath $frontendLog
    }

    if (-not (Test-HttpOk -Uri "http://localhost:8000/api/v1/health")) {
        Write-Step "Starting backend with uvicorn"
        Start-LocalService -Name "backend" -Command @($pythonExe, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000") -LogPath $backendLog | Out-Null
    } else {
        Write-Host "Backend health endpoint is already available; reusing existing process." -ForegroundColor Yellow
    }

    if (-not $SkipFrontend) {
        if (-not (Test-Path "frontend\package.json")) {
            throw "frontend/package.json not found."
        }
        if (-not (Test-HttpOk -Uri "http://localhost:5173")) {
            Write-Step "Starting frontend with Vite"
            $npmCommand = Resolve-NpmCommand
            Start-LocalService -Name "frontend" -Command @($npmCommand, "run", "dev", "--", "--host", "0.0.0.0") -LogPath $frontendLog -WorkingDirectory (Join-Path $repoRoot "frontend") | Out-Null
        } else {
            Write-Host "Frontend is already available; reusing existing process." -ForegroundColor Yellow
        }
    } else {
        Write-Host "Frontend startup skipped." -ForegroundColor Yellow
    }

    Write-Step "Waiting for local API health endpoint"
    $deadline = (Get-Date).AddSeconds($ApiTimeoutSeconds)
    $apiHealthy = $false
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 3
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
        if (Test-Path $backendLog) {
            $backendTail = Get-Content $backendLog -Tail 100
            if ($backendTail -match "ConnectionRefusedError|could not connect to server|relation .* does not exist|gen_random_uuid|vector") {
                Write-Host "Detected backend startup failure related to database initialization." -ForegroundColor Yellow
            }
        }
        Write-Host "Backend log: $backendLog" -ForegroundColor Yellow
        Fail-WithLogs -Message "Local backend did not become healthy within $ApiTimeoutSeconds seconds." -Mode $Mode -BackendLogPath $backendLog -FrontendLogPath $frontendLog
    }
}

Write-Host ""
Write-Host "DeepIntel is up." -ForegroundColor Green
Write-Host "Frontend: http://localhost:5173"
Write-Host "API:      http://localhost:8000"
Write-Host "Docs:     http://localhost:8000/docs"
Write-Host "Health:   http://localhost:8000/api/v1/health"
Write-Host "Postgres: localhost:5433"
Write-Host "Redis:    localhost:6379"
