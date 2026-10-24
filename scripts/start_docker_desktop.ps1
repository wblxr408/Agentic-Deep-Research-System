[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
# WMI creates the application outside the caller's inherited desktop environment.
# No socket rotations, no process kills, no data changes.
$exe=Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
$startup=New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ShowWindow=[uint16]0}
$created=Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
 CommandLine=('"'+$exe+'"');
 CurrentDirectory=(Split-Path -Parent $exe);
 ProcessStartupInformation=$startup
}
if($created.ReturnValue -ne 0){throw "Windows native Docker launch failed: WMI=$($created.ReturnValue)"}
Write-Output "Docker Desktop launched through Windows native process $($created.ProcessId)."
