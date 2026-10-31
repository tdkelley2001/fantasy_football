[CmdletBinding()]
param(
    [string]$PythonLauncher = "py",
    [string]$VirtualEnvironment = ".venv",
    [switch]$VerifyOnly
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venv = [IO.Path]::GetFullPath((Join-Path $repo $VirtualEnvironment))
$python = Join-Path $venv "Scripts\python.exe"

function Invoke-Checked([string]$File, [string[]]$Arguments, [string]$Failure) {
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Failure (exit code $LASTEXITCODE)." }
}

Push-Location $repo
try {
    if (-not $VerifyOnly) {
        try { $version = & $PythonLauncher -3.12 -c "import sys; print('.'.join(map(str, sys.version_info[:3])))" }
        catch { throw "Python 3.12 was not found. Install 64-bit Python 3.12 and ensure the 'py' launcher is available." }
        if ($LASTEXITCODE -ne 0 -or -not ($version -match '^3\.12\.')) {
            throw "Python 3.12 is required; detected '$version'."
        }
        if (-not (Test-Path $python)) {
            Invoke-Checked $PythonLauncher @("-3.12", "-m", "venv", $venv) "Unable to create the local virtual environment"
        }
        Invoke-Checked $python @("-m", "pip", "install", "--disable-pip-version-check", "-r", "requirements.lock") "Locked Python dependency installation failed"
        Invoke-Checked $python @("-m", "pip", "install", "--disable-pip-version-check", "--no-deps", "-e", ".") "Local package installation failed"

        if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw "Node.js is required to build the frontend." }
        if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw "npm is required to build the frontend." }
        $nodeParts = (& node --version).TrimStart('v').Split('.')
        $nodeMajor = [int]$nodeParts[0]
        $nodeMinor = [int]$nodeParts[1]
        if (($nodeMajor -eq 20 -and $nodeMinor -lt 19) -or $nodeMajor -lt 20 -or $nodeMajor -eq 21 -or ($nodeMajor -eq 22 -and $nodeMinor -lt 12)) {
            throw "Vite requires Node.js 20.19+ or 22.12+; detected $(& node --version)."
        }
        Push-Location (Join-Path $repo "frontend")
        try {
            Invoke-Checked "npm.cmd" @("ci", "--no-audit", "--no-fund") "Reproducible frontend dependency installation failed"
            Invoke-Checked "npm.cmd" @("run", "build") "Production frontend build failed"
        } finally { Pop-Location }
    }

    if (-not (Test-Path $python)) { throw "Prepared Python environment is missing at '$python'. Run setup without -VerifyOnly." }
    New-Item -ItemType Directory -Force -Path (Join-Path $repo "outputs"), (Join-Path $repo "outputs\logs"), (Join-Path $repo "outputs\runtime") | Out-Null
    if (-not (Test-Path (Join-Path $repo "frontend\dist\index.html"))) { throw "Production frontend assets are missing. Run setup to build them." }
    Invoke-Checked $python @("-c", "from fantasy_football.app.http import create_app; print('Python application import verified')") "Application import verification failed"
    Write-Host "War Room setup verified. Start with: .\scripts\start-local.ps1"
} finally { Pop-Location }
