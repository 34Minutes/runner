# Canonical PyInstaller spec for Runner (macOS .app, Windows .exe).
#
# The app only imports QtCore, QtGui, QtWidgets, and QtNetwork. PyInstaller's
# Qt hooks still collect every image/input plugin under QtGui, which then pulls
# QtPdf, QtSvg, QtQuick/QML, and Qt Virtual Keyboard. This spec excludes those
# unused bindings and strips the leftover binaries/translations after Analysis.
#
# Usage:
#   pyinstaller --clean --noconfirm runner.spec
#   ./scripts/build-mac.sh
#   .\scripts\build-windows.ps1
#
# Windows onedir instead of onefile:
#   $env:RUNNER_ONEFILE = "0"; pyinstaller --clean --noconfirm runner.spec

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from PyInstaller.building.api import COLLECT, EXE, PYZ
from PyInstaller.building.build_main import Analysis
from PyInstaller.building.osx import BUNDLE

block_cipher = None

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"
# macOS always ships an .app bundle (onedir). Windows defaults to a single exe.
ONEFILE = (not IS_MAC) and os.environ.get("RUNNER_ONEFILE", "1") != "0"

# Qt modules this app actually uses (plus DBus, which QtGui links on macOS).
KEEP_QT_MODULES = frozenset({"Core", "Gui", "Widgets", "Network", "DBus"})

# Plugin types required to show a desktop Widgets window and talk over QtNetwork.
KEEP_PLUGIN_TYPES = frozenset({"platforms", "styles", "tls", "imageformats"})

# Image-format plugins that pull extra Qt modules or unused codecs.
# PNG is built into QtGui; jpeg/ico/icns/gif stay for icons and file dialogs.
DROP_IMAGEFORMAT_PLUGINS = frozenset({
    "qpdf",       # pulls QtPdf (~8 MB)
    "qsvg",       # pulls QtSvg
    "qtga",
    "qwbmp",
    "qtiff",
    "qwebp",
    "qmacheif",
    "qmacjp2",
})

# Windows-only Qt Quick / ANGLE extras collected by the PySide6 hook.
DROP_NAME_SUBSTRINGS = (
    "opengl32sw",
    "libegl",
    "libglesv2",
    "d3dcompiler",
)

# QtFoo / Qt6Foo / libQt6Foo in a collected dest or source path.
_QT_MODULE_RE = re.compile(r"(?:^|[/\\])(?:lib)?Qt(?:5|6)?([A-Z][A-Za-z0-9]+)")


def _norm(path: str) -> str:
    return path.replace("\\", "/")


def _pyside_excludes() -> list[str]:
    """Exclude every PySide6.Qt* binding except the ones the app imports."""
    excludes = [
        "tkinter",
        "matplotlib",
        "numpy",
        "PyQt5",
        "PyQt6",
    ]
    try:
        import PySide6

        root = Path(PySide6.__file__).resolve().parent
        names: set[str] = set()
        for pattern in ("Qt*.abi3.so", "Qt*.pyd", "Qt*.so"):
            for path in root.glob(pattern):
                names.add(path.name.split(".")[0])
        for name in sorted(names):
            if name not in {f"Qt{m}" for m in KEEP_QT_MODULES}:
                excludes.append(f"PySide6.{name}")
    except Exception:
        # Fallback if PySide6 cannot be inspected at spec-compile time.
        excludes.extend(
            [
                "PySide6.QtPdf",
                "PySide6.QtPdfWidgets",
                "PySide6.QtQml",
                "PySide6.QtQuick",
                "PySide6.QtQuickWidgets",
                "PySide6.QtQuick3D",
                "PySide6.QtQuickControls2",
                "PySide6.QtVirtualKeyboard",
                "PySide6.QtOpenGL",
                "PySide6.QtOpenGLWidgets",
                "PySide6.QtSvg",
                "PySide6.QtSvgWidgets",
                "PySide6.QtMultimedia",
                "PySide6.QtWebEngineCore",
                "PySide6.QtWebEngineWidgets",
                "PySide6.QtSql",
                "PySide6.QtPrintSupport",
                "PySide6.QtTest",
                "PySide6.QtXml",
            ]
        )
    return excludes


def _plugin_type_and_name(path: str) -> tuple[str, str] | None:
    parts = _norm(path).split("/")
    try:
        idx = parts.index("plugins")
    except ValueError:
        return None
    if idx + 2 >= len(parts):
        return None
    plugin_type = parts[idx + 1]
    plugin_name = Path(parts[idx + 2]).stem.lower()
    if plugin_name.startswith("lib"):
        plugin_name = plugin_name[3:]
    return plugin_type, plugin_name


def keep_collected(dest: str, src: str = "") -> bool:
    """Return False for unused Qt modules, plugins, translations, and GL extras."""
    hay = _norm(dest) + "\n" + _norm(src)
    hay_l = hay.lower()

    if hay_l.endswith(".qm") or "/translations/" in hay_l:
        return False

    for snippet in DROP_NAME_SUBSTRINGS:
        if snippet in hay_l:
            return False

    plugin = _plugin_type_and_name(hay)
    if plugin is not None:
        plugin_type, plugin_name = plugin
        if plugin_type not in KEEP_PLUGIN_TYPES:
            return False
        if plugin_type == "imageformats" and plugin_name in DROP_IMAGEFORMAT_PLUGINS:
            return False
        return True

    modules = _QT_MODULE_RE.findall(hay)
    if modules and not all(mod in KEEP_QT_MODULES for mod in modules):
        return False

    return True


def _file_size(src: str) -> int:
    try:
        return Path(src).stat().st_size
    except OSError:
        return 0


def _filter_toc(toc, label: str):
    kept = []
    dropped = []
    for entry in toc:
        dest, src = entry[0], entry[1]
        if keep_collected(dest, src):
            kept.append(entry)
        else:
            dropped.append((dest, _file_size(src)))
    dropped_bytes = sum(sz for _, sz in dropped)
    print(
        f"==> Qt strip ({label}): kept {len(kept)}, "
        f"dropped {len(dropped)} ({dropped_bytes / (1024 * 1024):.1f} MB)",
        flush=True,
    )
    for dest, sz in sorted(dropped, key=lambda item: item[1], reverse=True)[:20]:
        print(f"    - {sz / (1024 * 1024):5.1f} MB  {dest}", flush=True)
    if len(dropped) > 20:
        print(f"    ... {len(dropped) - 20} more", flush=True)
    return kept


a = Analysis(
    ["scripts/launch.py"],
    pathex=["src", "scripts"],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=_pyside_excludes(),
    cipher=block_cipher,
    noarchive=False,
)

a.binaries = _filter_toc(a.binaries, "binaries")
a.datas = _filter_toc(a.datas, "datas")

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

APP_NAME = "Runner"

exe_kwargs = dict(
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=IS_WIN,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
if IS_WIN:
    if Path("assets/icon.ico").is_file():
        exe_kwargs["icon"] = "assets/icon.ico"
    if Path("file_version_info.txt").is_file():
        exe_kwargs["version"] = "file_version_info.txt"

if ONEFILE:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name=APP_NAME,
        upx_exclude=[],
        runtime_tmpdir=None,
        **exe_kwargs,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=APP_NAME,
        **exe_kwargs,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=IS_WIN,
        upx_exclude=[],
        name=APP_NAME,
    )
    if IS_MAC:
        app = BUNDLE(
            coll,
            name="Runner.app",
            icon=None,
            bundle_identifier="com.douglie.runner",
            info_plist={
                "LSUIElement": True,
                "CFBundleName": "Runner",
                "CFBundleDisplayName": "Runner",
                "CFBundleShortVersionString": "1.0.0",
                "CFBundleVersion": "1.0.0",
                "NSHighResolutionCapable": True,
            },
        )
