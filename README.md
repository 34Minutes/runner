# Runner

A lightweight floating launcher for any scripts or applications. Single point to launch everything you need.

## Features
- Tiny draggable + resizable trigger widget (downward arrow) that lives on your desktop
- Hover the arrow → smoothly animated dropdown list of your configured launchers (with live filter/search box)
- "Pin dropdown open" and "Show filter box in dropdown" quick toggles available directly in the arrow's right-click menu (also reflected in the Manage dialog for discoverability)
- Dropdown auto-hides on mouse leave (unless pinned); hover handoff between trigger and list
- Add / edit / manage launchers (Name, Command/Path + Browse, Parameters/Args, Working dir, Run as admin, Show console, Include in list)
- Full Manage dialog: list view, edit, delete, reorder (Move Up/Down), add new
- Launch EXEs, Python scripts, URLs, protocols, or any shell-registered application
- Persistent config (JSON in platform user config dir, atomic writes)
- System tray icon + menu (Add, Manage, Reload config, Exit); tray click also opens list
- Cross-platform (solid on Windows + macOS; basic on Linux)
- Test data pre-seeded appropriate to platform (Calculator, Calendar, Web Browser, etc.)

See [CHANGELOG.md](CHANGELOG.md) for release history and [docs/LANGUAGE_RECOMMENDATION.md](docs/LANGUAGE_RECOMMENDATION.md) for the original pre-development analysis and many future ideas.

## Installation (Development)

```bash
# From repo root
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Running (after pip install -e . )

```bash
runner
# or from source tree
PYTHONPATH=src python -m runner
# or
python -m runner.main
```

First run creates `config.json` in your platform user config dir with the sample launchers (Calculator, Calendar, Web Browser, etc).
```

On first run it will create a config with sample launchers and position the widget near top-left.

## Packaging & Deployment (Client installs)

This app is a desktop utility (floating trigger + tray). Clients should **not** be told to `pip install` or run from source. They need a **standalone bundled app**.

PyInstaller is the supported bundler (already in dev dependencies). Both platforms use `runner.spec`, which keeps only the Qt Widgets stack this app uses (QtCore, QtGui, QtWidgets, QtNetwork, QtDBus) and strips unused Qt (PDF, QML/Quick, Virtual Keyboard, OpenGL, SVG, extra image codecs, translations). Nuitka is an alternative for smaller/faster Windows builds:
```powershell
python -m nuitka --onefile --windows-disable-console --output-dir=dist --output-filename=Runner scripts/launch.py
```

### Building (recommended: use the helper scripts)

**On macOS (current dev machine):**
```bash
source .venv/bin/activate
./scripts/build-mac.sh
```
This produces `dist/Runner.dmg` (ready for client "install" by dragging to Applications).

**On Windows:**
```powershell
# In PowerShell, from repo root, after activating venv and `pip install -e ".[dev]"`
.\scripts\build-windows.ps1
```
This produces `dist\Runner.exe` (portable single-file by default).

The build now embeds:
- A proper arrow icon (`assets/icon.ico`) matching the trigger widget.
- Rich version info with Product Name "Runner".

You can also use the spec directly:
```bash
pyinstaller --clean --noconfirm runner.spec
```

**Cross-building from macOS to Windows .exe is not reliably supported** with PyInstaller + PySide6 (no Windows bootloader in the macOS PyInstaller installation, plus Qt native libs). Use a real Windows machine (or Parallels/UTM VM) or CI.

### Automated builds with GitHub Actions (recommended for releases)
Add a `.github/workflows/build.yml` (example in the repo or standard PyInstaller + Nuitka workflows). This can build Windows exe, macOS .app/.dmg, etc. on every tag.

### Distribution to clients ("install" methods)

**For macOS clients (easiest test run from this machine):**

Create a `.dmg` (best user experience — feels like a real install):

```bash
hdiutil create -volname "Runner" \
  -srcfolder "dist/Runner.app" \
  -ov -format UDZO "dist/Runner.dmg"
```

Client experience:
1. Download `Runner.dmg`.
2. Double-click the .dmg.
3. Drag the "Runner" icon to the Applications folder (shown inside the dmg).
4. Eject the dmg. Launch from Applications or Spotlight.

Alternative for quick test: Just zip the .app (`zip -r Runner.zip "dist/Runner.app"`) and tell the client to unzip + drag to /Applications.

**For Windows clients:**

```powershell
.\scripts\build-windows.ps1
# or: pyinstaller --clean --noconfirm runner.spec
```

Give the client `dist/Runner.exe` (portable — they can run it from anywhere, or copy to a folder). Or put it in a .zip. Do not use a raw `pyinstaller --onefile` CLI invocation; that skips the unused-Qt strip in `runner.spec`.

For a more "installed" feel on Windows you can later add Inno Setup / NSIS to create a proper installer with shortcuts/uninstaller.

### Current artifacts (after build on this machine)
- `dist/Runner.app` — the macOS bundle (~58 MB after unused-Qt strip; copy to /Applications to test locally).
- `dist/Runner.dmg` — ready-to-send disk image (~23 MB) for mac clients.

**Important notes**
- First launch on a client's Mac will likely trigger a Gatekeeper warning ("unidentified developer") because the app is not code-signed/notarized. Client can right-click the app → Open, or approve in System Settings → Privacy & Security.
- For production distribution you'd want an Apple Developer ID + notarization + hardened runtime.
- The tray icon currently falls back to a screenshot of the arrow widget if no system icon is available. A proper `assets/icon.icns` (and .ico for Windows) would be a nice polish item.
- Config is still stored in the user's platformdirs location even in the bundled app (`~/Library/Application Support/Runner/config.json` on mac).
- `runner.spec` is the canonical packager for macOS and Windows. It drops Qt modules this Widgets app never imports.

Run `./scripts/build-mac.sh` from the repo root (it will auto-activate `.venv` if needed, as long as you have run `pip install -e '.[dev]'` at least once). This produces `dist/Runner.dmg`. The `dist/` directory is gitignored.

## Usage
1. The small arrow trigger widget lives on your screen (frameless tool window, no taskbar entry by default).
2. Hover the arrow → the list of buttons slides/fades in below it (or above it with matching animation if the arrow is near the bottom of the screen). The dropdown automatically flips direction and/or shifts horizontally so it is always fully visible on screen no matter where you drag or resize the trigger (left/right/top/bottom edges or corners).
3. Click a button to launch (list hides unless "pinned open" mode is active).
4. Right-click the arrow (or use tray icon) → quick toggles ("Pin dropdown open", "Show filter box"), "Add new launcher...", or "Manage launchers...".
5. Drag the widget to move; drag its edges/corners to resize (size persisted).
6. The "Pin dropdown open" and filter visibility settings are also available in the Manage dialog (for discoverability).

## Configuration
Stored in your platform user config dir, e.g.:
- Windows: `%APPDATA%\Runner\config.json`
- macOS: `~/Library/Application Support/Runner/config.json`

You can edit the JSON manually or use the in-app dialogs.

## Development Notes
- UI built with PySide6 (Qt).
- Hover/animation + pinned state machine + layout height calculations are the most delicate parts — test thoroughly on target platforms.
- Windows-only behaviors (run as admin, show console, ShellExecute fallbacks) live in launcher.py + guarded by platform checks. `src/runner/utils/windows.py` is a stub for future helpers (icons, startup, etc.).
- To test Windows launch behavior, run on Windows or use a VM.
- See CHANGELOG.md for what landed in ALPHA_1.0.0.

## Roadmap / Ideas
Many enhancements documented in [docs/LANGUAGE_RECOMMENDATION.md](docs/LANGUAGE_RECOMMENDATION.md) (search/filter in list, per-item icons, keyboard nav in dropdown, advanced launch options UI, categories, drag-to-add files, portable mode, startup integration, etc.).

See the "Unreleased" section of [CHANGELOG.md](CHANGELOG.md) for active work items.

## License
MIT (or whatever you choose at release).
