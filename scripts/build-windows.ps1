# Build Runner for Windows using PyInstaller
# Run this on a Windows machine (PowerShell)
#
# Prerequisites:
#   1. Clone the repo
#   2. cd to the repo root
#   3. python -m venv .venv
#   4. .\.venv\Scripts\Activate.ps1
#   5. pip install -e ".[dev]"
#   6. Icon is now included (assets\icon.ico - an arrow matching the trigger)
#
# Then run:
#   .\scripts\build-windows.ps1
#
# Output will be in dist\Runner.exe (onefile by default).
# Unused Qt modules (PDF, QML/Quick, Virtual Keyboard, SVG, extra codecs) are
# stripped by runner.spec so the exe stays Widgets-only.

param(
    [switch]$OneFile = $true
)

$ErrorActionPreference = "Stop"

Write-Host "==> Building Runner for Windows..."

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$projectRoot = Split-Path -Parent $scriptDir
Set-Location $projectRoot

# Canonical spec excludes unused Qt modules/plugins/translations and embeds
# the Windows icon + version info. Override onedir vs onefile via env var.
if ($OneFile) {
    $env:RUNNER_ONEFILE = "1"
} else {
    $env:RUNNER_ONEFILE = "0"
}

if (Test-Path "assets\icon.ico") {
    Write-Host "Using assets\icon.ico for exe icon and taskbar (via runner.spec)."
} else {
    Write-Host "Note: assets\icon.ico not found. The exe will use a default icon."
}

Write-Host "Running: pyinstaller --clean --noconfirm runner.spec"
pyinstaller --clean --noconfirm runner.spec

Write-Host ""
Write-Host "==> Build complete!"
if ($OneFile) {
    Write-Host "Executable: dist\Runner.exe"
    Write-Host "Right-click the exe -> Properties to verify 'Runner' as Product name."
} else {
    Write-Host "Folder: dist\Runner\"
}
Write-Host ""
Write-Host "To test: Copy Runner.exe to a real Windows machine and run it."
Write-Host "The app is designed as a portable single-file exe (config goes to AppData by default)."