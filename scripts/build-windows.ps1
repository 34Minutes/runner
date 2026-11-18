# Build Runner for Windows: dist\Runner.exe, one portable file.
#
# Usage, from any folder:
#   .\scripts\build-windows.ps1              lint, test, then build
#   .\scripts\build-windows.ps1 -SkipTests   build without the lint check and tests
#   .\scripts\build-windows.ps1 -OneDir      build a folder, dist\Runner\, instead
#
# First time, from the repo root:
#   python -m venv .venv
#   .\.venv\Scripts\python -m pip install -e ".[dev]"
#
# The project's .venv is used when it exists, whatever venv the shell has
# active; otherwise the python on PATH (as on GitHub Actions). The version
# comes from pyproject.toml and runner.spec writes it into the exe's file
# properties.

param(
    [switch]$OneDir,
    [switch]$SkipTests,
    [switch]$Help
)

$ErrorActionPreference = "Stop"

if ($Help) {
    Get-Content $MyInvocation.MyCommand.Path | Select-Object -Skip 2 -First 4 |
        ForEach-Object { $_ -replace '^# ?', '' }
    exit 0
}

# "Stop" does not cover programs like python. Check each exit code.
function Invoke-Checked {
    param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Exe $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
    }
}

$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $projectRoot

$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $py = $venvPython
} else {
    $py = (Get-Command python -ErrorAction Stop).Source
}

$version = & $py scripts\check_version.py
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "==> Runner $version"
Write-Host "==> Python: $py ($(& $py --version 2>&1))"

if (-not $SkipTests) {
    Write-Host "==> Lint (ruff)..."
    Invoke-Checked $py @("-m", "ruff", "check", "src", "tests")
    Write-Host "==> Running tests (some briefly open windows)..."
    # --capture=sys lets Qt's own error messages through if Qt aborts.
    Invoke-Checked $py @("-m", "pytest", "-q", "--capture=sys")
}

if ($OneDir) { $env:RUNNER_ONEFILE = "0" } else { $env:RUNNER_ONEFILE = "1" }

Write-Host "==> Building..."
Invoke-Checked $py @("-m", "PyInstaller", "--clean", "--noconfirm", "runner.spec")

if ($OneDir) {
    $exe = Join-Path $projectRoot "dist\Runner\Runner.exe"
} else {
    $exe = Join-Path $projectRoot "dist\Runner.exe"
}
if (-not (Test-Path $exe)) {
    throw "The build finished but $exe is missing."
}

# The file properties must carry the version just built.
$shown = (Get-Item $exe).VersionInfo.ProductVersion
if ($shown -ne $version) {
    throw "$exe reports version '$shown', expected '$version'."
}

$sizeMb = [math]::Round((Get-Item $exe).Length / 1MB, 1)
Write-Host ""
Write-Host "==> Built Runner $version"
Write-Host "    $exe ($sizeMb MB)"
if ($OneDir) {
    Write-Host "    Copy the whole dist\Runner folder; Runner.exe needs the files beside it."
} else {
    Write-Host "    One portable file. Config is stored in %APPDATA%\Runner."
}
