# Build Script Runner for Windows using PyInstaller
# Run this on a Windows machine (PowerShell)
#
# Prerequisites:
#   1. Clone the repo
#   2. cd to the repo root
#   3. python -m venv .venv
#   4. .\.venv\Scripts\Activate.ps1
#   5. pip install -e ".[dev]"
#   6. (Optional) Place a Windows icon at assets\icon.ico
#
# Then run:
#   .\scripts\build-windows.ps1
#
# Output will be in dist\ScriptRunner.exe (onefile by default in this script for simplicity)
# or adjust to onedir.

param(
    [switch]$OneFile = $true
)

$ErrorActionPreference = "Stop"

Write-Host "==> Building Script Runner for Windows..."

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$projectRoot = Split-Path -Parent $scriptDir
Set-Location $projectRoot

$pyinstallerArgs = @(
    "--clean",
    "--noconfirm",
    "--name", "ScriptRunner",
    "--windowed",
    "--paths", "src",
    "--paths", "scripts",
    "scripts/launch.py"
)

if ($OneFile) {
    $pyinstallerArgs += "--onefile"
} else {
    $pyinstallerArgs += "--onedir"
}

# Icon (optional)
if (Test-Path "assets\icon.ico") {
    $pyinstallerArgs += "--icon", "assets\icon.ico"
} else {
    Write-Host "Note: No assets\icon.ico found. Using default icon."
}

# Common excludes to reduce size
$pyinstallerArgs += "--exclude-module", "tkinter"
$pyinstallerArgs += "--exclude-module", "matplotlib"
$pyinstallerArgs += "--exclude-module", "numpy"
$pyinstallerArgs += "--exclude-module", "PyQt5"
$pyinstallerArgs += "--exclude-module", "PyQt6"

Write-Host "Running: pyinstaller $($pyinstallerArgs -join ' ')"
pyinstaller @pyinstallerArgs

Write-Host ""
Write-Host "==> Build complete!"
if ($OneFile) {
    Write-Host "Executable: dist\ScriptRunner.exe"
} else {
    Write-Host "Folder: dist\ScriptRunner\"
}
Write-Host ""
Write-Host "To test: Run the exe on a Windows machine."
Write-Host "For distribution, consider wrapping in an installer (Inno Setup recommended)."