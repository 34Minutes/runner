# PyInstaller spec (primarily for Windows .exe builds).
# This is legacy / Windows-oriented.
#
# Recommended for current development (especially macOS builds):
#   See the "Packaging & Deployment" section in README.md
#   (uses modern pyinstaller CLI + post-processing for .app / .dmg).
#
# Usage on Windows:
#   pyinstaller script-runner.spec

from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT
import os

block_cipher = None

a = Analysis(
    ["src/script_runner/main.py"],
    pathex=["src"],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "PyQt5", "PyQt6"],  # reduce size
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="ScriptRunner",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,           # no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.ico",  # provide a real .ico for nice taskbar/tray
    version="file_version_info.txt",  # optional: create a version file
)
