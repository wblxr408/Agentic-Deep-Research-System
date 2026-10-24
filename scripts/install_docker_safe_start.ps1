# Install the recovery launcher at the user's actual Windows launch entry points.
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$desktopExe = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
$supportRoot = [System.IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'DockerSafeStart'))
$source = Join-Path $PSScriptRoot 'start_docker_desktop.ps1'
$launcherPath = Join-Path $supportRoot 'Start-DockerDesktop.ps1'
$powershellExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$settingsPath = Join-Path $env:APPDATA 'Docker\settings-store.json'
$runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$runName = 'Docker Desktop'
$stamp = (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)

if (-not [System.IO.File]::Exists($desktopExe)) { throw 'Docker Desktop is not installed.' }
$settings = Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json
if ($settings.AutoStart -isnot [bool]) {
    throw 'Docker AutoStart preference is unknown; refusing to guess the login startup setting.'
}
$oldRun = (Get-Item -LiteralPath $runKey).GetValue($runName, $null)
if ($oldRun) {
    $knownOriginal = @($desktopExe, ('"' + $desktopExe + '"'))
    $knownRecovery = $oldRun.Contains($launcherPath)
    if ($oldRun -notin $knownOriginal -and -not $knownRecovery) {
        throw 'Unrecognized Docker login command; inspect it before replacing it.'
    }
}

[System.IO.Directory]::CreateDirectory($supportRoot) | Out-Null
if ((Get-Item -LiteralPath $supportRoot).Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
    throw 'Refusing to install into a redirected support directory.'
}
$backupDirectory = Join-Path $supportRoot ('entrypoints-before-' + $stamp)
[System.IO.Directory]::CreateDirectory($backupDirectory) | Out-Null
[pscustomobject]@{AutoStart=$settings.AutoStart; RegistryPath=$runKey; Name=$runName; Value=$oldRun} |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $backupDirectory 'login-startup.json') -Encoding UTF8
if ([System.IO.File]::Exists($launcherPath)) {
    Copy-Item -LiteralPath $launcherPath -Destination (Join-Path $backupDirectory 'Start-DockerDesktop.ps1')
}
Copy-Item -LiteralPath $source -Destination $launcherPath -Force

$arguments = '-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $launcherPath + '"'
$desktopDirectory = [Environment]::GetFolderPath('Desktop')
$startMenuDirectory = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
$taskbarLink = Join-Path $env:APPDATA 'Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar\Docker Desktop.lnk'
$entries = @(
    @{Name='desktop'; Path=(Join-Path $desktopDirectory 'Docker Desktop.lnk')},
    @{Name='start-menu'; Path=(Join-Path $startMenuDirectory 'Docker Desktop.lnk')}
)
# Repair the existing pin; do not add a taskbar pin the user did not request.
if ([System.IO.File]::Exists($taskbarLink)) {
    $entries += @{Name='taskbar'; Path=$taskbarLink}
}
$shell = New-Object -ComObject WScript.Shell
foreach ($entry in $entries) {
    if ([System.IO.File]::Exists($entry.Path)) {
        Copy-Item -LiteralPath $entry.Path -Destination (Join-Path $backupDirectory ($entry.Name + '.lnk'))
    }
    $shortcut = $shell.CreateShortcut($entry.Path)
    $shortcut.TargetPath = $powershellExe
    $shortcut.Arguments = $arguments
    $shortcut.WorkingDirectory = $supportRoot
    $shortcut.IconLocation = $desktopExe + ',0'
    $shortcut.Description = 'Docker Desktop with native Windows process launch'
    $shortcut.WindowStyle = 7
    $shortcut.Save()
    Write-Output ('Updated ' + $entry.Name + ': ' + $entry.Path)
}

if ($settings.AutoStart) {
    $newRun = '"' + $powershellExe + '" ' + $arguments
    New-ItemProperty -LiteralPath $runKey -Name $runName -Value $newRun -PropertyType String -Force | Out-Null
    Write-Output 'Login startup enabled through the same recovery launcher, following Docker AutoStart=true.'
}
elseif ($oldRun) {
    Remove-ItemProperty -LiteralPath $runKey -Name $runName
    Write-Output 'Removed stale Docker login command, following Docker AutoStart=false.'
}
Write-Output ('Original entry points preserved in: ' + $backupDirectory)
