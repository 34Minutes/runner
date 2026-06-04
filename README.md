# Script Runner

A lightweight, always-on-top floating launcher for any scripts or applications. Single point to launch everything you need.

## Features (MVP + planned)
- Always stays on top of other windows
- Tiny trigger widget with downward arrow
- Hover the arrow → smoothly animated dropdown list of your configured launchers
- Dropdown hides automatically when mouse leaves
- Add new launchers via menu / tray (Name, Command/Path, Parameters, Include in list)
- Launch EXEs, Python scripts, URLs, or any shell-registered application
- Persistent config (JSON in user config dir)
- Draggable trigger
- System tray for reliable access
- Test data pre-seeded: Calculator, Calendar, Web Browser

See [docs/LANGUAGE_RECOMMENDATION.md](docs/LANGUAGE_RECOMMENDATION.md) for the pre-development analysis and additional ideas.

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

## On Windows (Target)

After developing on macOS/Linux:

### Quick single-file EXE (recommended for users)
```bash
pip install pyinstaller
pyinstaller --onefile --noconsole --name ScriptRunner --icon=assets/icon.ico src/script_runner/main.py
```

The resulting `dist/ScriptRunner.exe` is what you give users.

### Better size/performance (Nuitka)
```bash
pip install nuitka
python -m nuitka --onefile --windows-disable-console --output-dir=dist --output-filename=ScriptRunner src/script_runner/main.py
```

## Usage
1. The small arrow widget lives on your screen (always on top, no taskbar button by default).
2. Hover the arrow → the list of buttons slides/fades in below it.
3. Click a button to launch.
4. Right-click the arrow (or use tray icon) → "Add new launcher..." to configure more.
5. Move the widget by dragging it.

## Configuration
Stored in your platform user config dir, e.g.:
- Windows: `%APPDATA%\ScriptRunner\config.json`
- macOS: `~/Library/Application Support/ScriptRunner/config.json`

You can edit the JSON manually or use the in-app dialogs.

## Development Notes
- UI built with PySide6 (Qt).
- Hover/animation logic is the most delicate part — test thoroughly.
- Windows-only behaviors (run as admin, file icons, startup shortcut, hotkeys) live in `src/script_runner/utils/windows.py` and are guarded by platform checks.
- To test Windows launch behavior, run on Windows or use a VM.

## Roadmap / Ideas
Many enhancements documented in the language rec doc (global hotkey, search in list, icons, categories, manage dialog, drag-to-add, etc.).

## License
MIT (or whatever you choose at release).
