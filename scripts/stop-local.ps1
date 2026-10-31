[CmdletBinding()]
param([int]$TimeoutSeconds = 20)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$metadataPath = Join-Path $repo "outputs\runtime\war-room-server.json"
if (-not (Test-Path $metadataPath)) { Write-Host "War Room is not running (no launcher metadata)."; return }
try { $metadata = Get-Content $metadataPath -Raw | ConvertFrom-Json }
catch { throw "Launcher metadata is unreadable at '$metadataPath'; no process was stopped." }
$process = Get-Process -Id ([int]$metadata.pid) -ErrorAction SilentlyContinue
if (-not $process) {
    Remove-Item -LiteralPath $metadataPath -Force
    Write-Warning "Removed stale launcher metadata; the recorded process was not running."
    return
}
$recordedStart = [DateTime]::Parse([string]$metadata.process_started_at_utc).ToUniversalTime()
$actualStart = $process.StartTime.ToUniversalTime()
if ([Math]::Abs(($actualStart - $recordedStart).TotalSeconds) -gt 2) {
    throw "PID $($metadata.pid) was reused by another process. It was not stopped."
}
[string]$metadata.run_id | Set-Content -LiteralPath ([string]$metadata.shutdown_file) -Encoding ASCII
$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
while ([DateTime]::UtcNow -lt $deadline -and -not $process.HasExited) { Start-Sleep -Milliseconds 200; $process.Refresh() }
if (-not $process.HasExited) { throw "Graceful shutdown did not complete within $TimeoutSeconds seconds. The process was left running; inspect '$($metadata.stderr_log)'." }
Remove-Item -LiteralPath $metadataPath -Force
Write-Host "War Room stopped cleanly. Persisted databases were preserved."
