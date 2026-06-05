# Script Runner

A lightweight floating launcher for any scripts or applications. Single point to launch everything you need.

## Features (BETA)
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
script-runner
# or from source tree
PYTHONPATH=src python -m script_runner
# or
python -m script_runner.main
```

First run creates `config.json` in your platform user config dir with the sample launchers (Calculator, Calendar, Web Browser, etc).
```

On first run it will create a config with sample launchers and position the widget near top-left.

## Packaging (Windows target)

After developing on macOS/Linux:

### Quick single-file EXE (recommended for users)
```bash
pip install pyinstaller
pyinstaller script-runner.spec
# or one-off:
pyinstaller --onefile --noconsole --name ScriptRunner --icon=assets/icon.ico src/script_runner/main.py
```

The resulting `dist/ScriptRunner.exe` is what you give users.

### Better size/performance (Nuitka)
```bash
pip install nuitka
python -m nuitka --onefile --windows-disable-console --output-dir=dist --output-filename=ScriptRunner src/script_runner/main.py
```

Note: assets/icon.ico is recommended for a nice taskbar/tray icon (currently placeholder).

## Usage
1. The small arrow trigger widget lives on your screen (frameless tool window, no taskbar entry by default).
2. Hover the arrow → the list of buttons slides/fades in below it (or above it with matching animation if the arrow is near the bottom of the screen). The dropdown automatically flips direction and/or shifts horizontally so it is always fully visible on screen no matter where you drag or resize the trigger (left/right/top/bottom edges or corners).
3. Click a button to launch (list hides unless "pinned open" mode is active).
4. Right-click the arrow (or use tray icon) → quick toggles ("Pin dropdown open", "Show filter box"), "Add new launcher...", or "Manage launchers...".
5. Drag the widget to move; drag its edges/corners to resize (size persisted).
6. The "Pin dropdown open" and filter visibility settings are also available in the Manage dialog (for discoverability).

## Configuration
Stored in your platform user config dir, e.g.:
- Windows: `%APPDATA%\ScriptRunner\config.json`
- macOS: `~/Library/Application Support/ScriptRunner/config.json`

You can edit the JSON manually or use the in-app dialogs.

## Development Notes
- UI built with PySide6 (Qt).
- Hover/animation + pinned state machine + layout height calculations are the most delicate parts — test thoroughly on target platforms.
- Windows-only behaviors (run as admin, show console, ShellExecute fallbacks) live in launcher.py + guarded by platform checks. `src/script_runner/utils/windows.py` is a stub for future helpers (icons, startup, etc.).
- To test Windows launch behavior, run on Windows or use a VM.
- See CHANGELOG.md for what landed in ALPHA_1.0.0.

## Roadmap / Ideas
Many enhancements documented in [docs/LANGUAGE_RECOMMENDATION.md](docs/LANGUAGE_RECOMMENDATION.md) (search/filter in list, per-item icons, keyboard nav in dropdown, advanced launch options UI, categories, drag-to-add files, portable mode, startup integration, etc.).

See the "Unreleased" section of [CHANGELOG.md](CHANGELOG.md) for active work items.

## License
MIT (or whatever you choose at release).
