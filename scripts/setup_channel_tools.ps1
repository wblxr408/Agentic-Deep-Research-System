param(
    [string]$NodePath = (Get-Command node.exe -ErrorAction Stop).Source,
    [string]$PythonPath = (Join-Path $PSScriptRoot '../.venv/Scripts/python.exe'),
    [string]$UvPath = (Get-Command uv.exe -ErrorAction Stop).Source
)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location $projectRoot
try {
    & $PythonPath -m pip install bilibili-cli==0.6.2 'yt-dlp[default]==2026.8.19'
    if ($LASTEXITCODE -ne 0) { throw 'Public collection tools installation failed' }
    $npmPath = Join-Path (Split-Path $NodePath) 'npm.cmd'
    New-Item -ItemType Directory -Force .channel-tools | Out-Null
    Copy-Item -LiteralPath config/channel-tools.package.json -Destination .channel-tools/package.json
    Set-Location (Join-Path $projectRoot '.channel-tools')
    & $npmPath install
    $npmExit = $LASTEXITCODE
    Set-Location $projectRoot
    if ($npmExit -ne 0) { throw 'Node collection tools installation failed' }
    & $UvPath venv .channel-tools/python --python 3.13 --allow-existing
    if ($LASTEXITCODE -ne 0) { throw 'Isolated Python environment creation failed' }
    $loginPython = Join-Path $projectRoot '.channel-tools/python/Scripts/python.exe'
    & $UvPath pip install --python $loginPython boss-agent-cli==3.0.0 twitter-cli==0.8.5 mcp-server-linkedin==4.27.0
    if ($LASTEXITCODE -ne 0) { throw 'Login channel tools installation failed' }
    $localMcpPath = Join-Path $projectRoot 'config/mcporter.local.json'
    $mcp = Get-Content (Join-Path $projectRoot 'config/mcporter.json') -Raw | ConvertFrom-Json -AsHashtable
    $mcp.mcpServers.linkedin = @{
        command = (Join-Path $projectRoot '.channel-tools/python/Scripts/mcp-server-linkedin.exe')
        args = @('--transport','stdio','--no-auto-import','--user-data-dir',(Join-Path $projectRoot '.channel-tools/linkedin/profile'))
        allowedTools = @('search_jobs','get_person_profile','get_company_profile')
        env = @{ LOGIN_INLINE_WAIT='0'; LOGIN_TIMEOUT='1' }
    }
    $mcp | ConvertTo-Json -Depth 10 | Set-Content -Encoding utf8 $localMcpPath
    $nativeTools = @{
        bili = @((Join-Path $projectRoot '.venv/Scripts/bili.exe'))
        'yt-dlp' = @($PythonPath, '-m', 'yt_dlp', '--js-runtimes', "node:$NodePath")
        mcporter = @($NodePath,(Join-Path $projectRoot '.channel-tools/node_modules/mcporter/dist/cli.js'),'--config',$localMcpPath)
        opencli = @($NodePath,(Join-Path $projectRoot '.channel-tools/node_modules/@jackwener/opencli/dist/src/main.js'),'--profile','deepintel-test')
        twitter = @((Join-Path $projectRoot '.channel-tools/python/Scripts/twitter.exe'))
        boss = @((Join-Path $projectRoot '.channel-tools/python/Scripts/boss.exe'),'--data-dir',(Join-Path $projectRoot '.channel-tools/boss'))
    }
    $nativeTools | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 (Join-Path $projectRoot 'config/channel-tools.local.json')
    Write-Output 'Installed fixed collection tools and local native/MCP configuration. Platform login is a separate manual step.'
} finally { Pop-Location }
