[CmdletBinding()]
param(
    [int]$TimeoutSeconds = 20,
    [string]$RuntimeDirectory = $(if ($env:WAR_ROOM_RUNTIME_DIRECTORY) { $env:WAR_ROOM_RUNTIME_DIRECTORY } else { "outputs\runtime" })
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
. (Join-Path $PSScriptRoot "local-runtime.ps1")
if ([IO.Path]::IsPathRooted($RuntimeDirectory)) {
    $runtimePath = [IO.Path]::GetFullPath($RuntimeDirectory)
} else {
    $runtimePath = [IO.Path]::GetFullPath((Join-Path $repo $RuntimeDirectory))
}
$metadataPath = Join-Path $runtimePath "war-room-server.json"
if (-not (Test-Path $metadataPath)) { Write-Host "War Room is not running (no launcher metadata)."; return }
$metadata = Read-WarRoomMetadata $metadataPath
$process = Get-WarRoomOwnedProcess $metadata
if (-not $process) {
    Remove-Item -LiteralPath $metadataPath -Force
    Write-Warning "Removed stale launcher metadata; the recorded process was not running."
    return
}
Assert-WarRoomPortOwner -Port ([int]$metadata.port) -ProcessId $process.Id
$null = Assert-WarRoomHealthIdentity -Port ([int]$metadata.port) -ExpectedRunId ([string]$metadata.run_id) -ExpectedProcessId $process.Id
[string]$metadata.run_id | Set-Content -LiteralPath ([string]$metadata.shutdown_file) -Encoding ASCII
$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
while ([DateTime]::UtcNow -lt $deadline -and -not $process.HasExited) { Start-Sleep -Milliseconds 200; $process.Refresh() }
if (-not $process.HasExited) { throw "Graceful shutdown did not complete within $TimeoutSeconds seconds. The process was left running; inspect '$($metadata.stderr_log)'." }
Remove-Item -LiteralPath $metadataPath -Force
Write-Host "War Room stopped cleanly. Persisted databases were preserved."
