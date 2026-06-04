# Script Runner - Pre-Development Recommendation & Ideas

**Project**: Script Runner  
**Goal**: A lightweight, always-on-top single launcher for any scripts or applications on Windows.  
**Date**: 2026

---

## Pre-Task: Recommended Language + Framework

### Requirements Context
- Primary runtime target: **Windows** machines.
- Development machine: **macOS** (current workspace).
- UI style: Small persistent floating widget (downward arrow) → hover to reveal animated vertical list of named buttons.
- Must support: always-on-top, configurable trigger size, add/edit dialog (name + parameters + enabled flag), launching EXEs / Python scripts / any apps.
- Distribution: Ideally a single executable users can run without installing Python/.NET/etc.

### Primary Recommendation: **Python 3 + PySide6**

**PySide6** (the official Qt for Python bindings, Qt 6) is the best fit.

#### Why Python + PySide6 wins here

| Criterion                        | Python + PySide6                                      | Notes / Fit to Spec |
|----------------------------------|-------------------------------------------------------|---------------------|
| Dev on macOS                     | Excellent (native Qt app runs on mac)                 | Full UI/animation testing without Windows |
| Always-on-top + frameless        | `Qt.WindowStaysOnTopHint \| Qt.FramelessWindowHint \| Qt.Tool` | Trivial and reliable |
| Hover enter/leave + no flicker   | `enterEvent`, `leaveEvent`, `setMouseTracking`, `QTimer` for delayed hide | Exactly what the hover dropdown requires |
| Smooth appear/disappear animations | `QPropertyAnimation` + `QParallelAnimationGroup` + easing | Slide, fade, height, opacity – all built-in, no extra libs |
| Add dialog (name, params, checkbox) | `QDialog` + `QFormLayout`, `QLineEdit`, `QCheckBox`, `QFileDialog` for browse | Perfect match |
| Launching EXE / .py / anything   | `subprocess.Popen`, `os.startfile`, shell=True, `py` launcher support | Python makes .py handling natural |
| Configurable UI size             | Simple QWidget resize + persisted settings            | Easy |
| System tray + context menu       | `QSystemTrayIcon` + `QMenu`                           | Required for good UX |
| Theming / button styles          | QSS (Qt Style Sheets) – CSS-like                      | Modern minimal look without native widget limits |
| Single-file Windows distribution | PyInstaller (`--onefile --noconsole`) or Nuitka       | Produces `ScriptRunner.exe` |
| Python script launching          | First-class (detect .py, choose interpreter, venvs later) | Aligns with your use case |
| Learning / iteration speed       | Very high                                             | Quick to prototype the tricky hover state machine |
| Future cross-platform            | Possible (with some Windows-specific launch code)     | Bonus |

**Packaging notes (Windows)**:
- `pyinstaller -w -F --icon=assets/icon.ico main.py` → single exe.
- Use `nuitka --onefile --windows-disable-console --include-data-files=...` for smaller/faster results if size matters.
- Add Windows manifest for DPI awareness and to avoid "python.exe" console flashes.
- Typical size: 20-50 MB (perfectly acceptable; can be optimized).

**License**: PySide6 is LGPL – fine for closed-source or open distribution. (PyQt6 is also an option if you prefer the Riverbank commercial license model.)

#### Potential downsides & mitigations
- Executable size larger than pure Win32/C# trimmed → Use Nuitka or `--exclude` modules you don't need.
- Qt "Fusion" style + custom QSS can look slightly non-native → We will design a very clean, minimal, Windows-like dark/light theme.
- No built-in "acrylic blur" on Win11 without extra work → Can add later with `win32` extensions if desired; not in initial scope.

---

### Strong Alternative: **C# + WPF** (or WinUI 3 + Windows App SDK)

**Use this if**:
- You (or the long-term maintainer) primarily develop on Windows.
- You want the most "native Windows" appearance and behavior with zero styling effort.
- You prefer a compiled language and the smallest possible final .exe size.

**Key strengths for this project**:
- `Topmost = true` + easy Win32 `SetWindowPos` for robust always-on-top (even vs fullscreen games in some cases).
- XAML + Storyboards = beautiful, declarative hover/expand animations.
- `Process.Start` (with `UseShellExecute`) handles everything (exes, urls, docs).
- Excellent designer in Visual Studio (on Windows).
- Single-file publish with trimming in modern .NET is very lean.

**Major drawback for current situation**:
- **You cannot run or visually test the app on macOS**. WPF/WinUI are Windows-only at runtime.
- Every UI tweak (hover timing, animation speed, layout of the add dialog, dragging behavior) would require building + copying to a Windows machine or VM.
- This slows development significantly given the macOS workspace.

**Packaging**: `dotnet publish -c Release -r win-x64 -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true --self-contained true` → nice .exe.

**Verdict**: Excellent technical choice for a Windows-only polished utility. **Not recommended as primary here** purely because of the macOS development environment.

---

### Options We Considered and Rejected (for now)

| Option                  | Why Not Primary |
|-------------------------|-----------------|
| **Tauri (Rust + web frontend)** | Small/fast final app + CSS animations are attractive, but stack complexity (Rust + Svelte/React + two build systems) is high for a simple 1-dialog + hover widget. Cross-compile from mac to Windows exe also requires more setup. Good evolution path later. |
| **Electron (any frontend)** | Launcher apps must feel *instant* and tiny. Electron is heavy on RAM, disk, and cold-start time. Ruled out. |
| **AutoHotkey v2**       | Fantastic for Windows scripting + simple GUIs + hotkeys. Many personal launchers are AHK. However, building smooth animated custom dropdowns + professional resizable dialogs is much more painful than Qt or WPF. |
| **Python + Tkinter**    | Too primitive for reliable hover state, smooth animations, or nice-looking buttons without huge effort. |
| **Python + Dear PyGui / imgui** | Great for tools, fast, but not ideal for traditional "dialog + form + persistent floating desktop widget" patterns. |
| **WinForms (C#)**       | Dated. Animations and custom drawing are clunky compared to WPF or Qt. |
| **Rust native (egui, Iced, Slint)** | Promising future, but current widget/form story and hover popup ergonomics lag behind Qt for this exact UI. |
| **.NET MAUI / Uno**     | Overkill, heavier, not optimized for tiny floating always-on-top desktop widgets. |

---

### Final Language Recommendation

**Start with Python 3.12+ + PySide6.**

This is the pragmatic winner given:
- macOS development reality
- The very specific hover + animation + always-on-top requirements (Qt handles the hard parts elegantly)
- Natural affinity for launching Python scripts
- Acceptable distribution story for Windows users

We can always extract the pure "launch command list" logic into a shared module later and rewrite the UI shell in C# or Tauri if the project proves popular and you want a smaller binary or deeper OS integration.

---

## Additional Ideas & Enhancements (Relevant & Valuable)

The spec is already solid and focused. Here are ideas I recommend considering (prioritized):

### High-Value Additions (should be in v1 or v1.1)

1. **System Tray Icon + Menu** (very important)
   - The small arrow widget can be tiny and easy to miss. Tray gives reliable access: Add New..., Manage Launchers..., Settings, Reload, Exit.
   - Also "Temporarily hide launcher".

2. **Draggable + Persisted Position**
   - Users must be able to move the trigger widget. Save x/y (and which monitor if possible) to config.

3. **"Add" from right-click or tray is mandatory** – already in spec, good.

4. **Full "Manage Launchers" dialog** (table view)
   - Besides the per-item add dialog, a list where you can edit/delete/reorder (drag rows), toggle enabled, test-launch a row, duplicate.
   - This makes maintenance of 10+ items pleasant.

5. **Global hotkey to force open the list**
   - e.g. `Ctrl + Alt + L` or `Win + Shift + Q`. Very useful when mouse is not near the widget.
   - Libraries: `keyboard` (simple, may need admin) or `pynput` or low-level RegisterHotKey via ctypes/win32.

6. **Click vs Hover mode**
   - Some users hate hover (accidental triggers). Setting: "Open on hover" vs "Open on click". The spec uses hover, but toggle is nice.

7. **Auto file icon + optional custom icon per launcher**
   - Windows users expect icons. Qt can get default exe icons reasonably well; pywin32 gives better.

8. **Search box in the dropdown** (when list gets long)
   - Live filter as you type. Huge usability win.

9. **Keyboard support in dropdown**
   - When list visible: Up/Down arrows, Enter to launch, Esc/click outside to close. Focus the first item automatically.

10. **Better launch options in the dialog**
    - Working directory
    - "Run as administrator" (per item)
    - "Show console / terminal window" (for .py/.bat/.cmd that print)
    - Optional "Start minimized" or hidden

### Nice-to-Haves (v2+)

- Drag .exe / .py files onto the arrow widget → auto-open pre-filled Add dialog.
- Categories / sections in the dropdown (Dev / Daily / Media).
- Launch history + "most used" smart ordering or separate recents section.
- Portable mode (config.json next to exe takes precedence over AppData).
- Add to Windows startup (checkbox creates .lnk in Startup folder).
- Simple logging of launches (timestamp, name, success/fail, error).
- Theme selector (Light / Dark / Follow Windows) with QSS.
- "Quick command" mode: a text field at bottom of dropdown to type any command and run it (like a mini run dialog).
- Export / import of launcher lists (great for sharing "my dev setup").
- Validate on add/edit: warn if local exe doesn't exist.
- Support for environment variable expansion in command/args/working dir (`%USERPROFILE%`, `$env:xxx` style).
- Single-instance enforcement (so double-clicking the exe doesn't spawn multiples).

### Ideas Specific to "running scripts"

- Smart Python handling: if command ends with `.py`, offer a dropdown of known Pythons (`py -3.12`, `py -3`, full path to venv python, etc.).
- Optional "Capture output" mode that runs the script and shows stdout in a small scrollable window (great for one-off tools).
- Button to "Edit script in default editor" next to launch (for .py files).

### Test Data (as requested)

Seed the initial config with at least these (user can edit/delete):

1. **Calculator**
   - Name: Calculator
   - Command: `calc`
   - Args: (empty)
   - Enabled: true

2. **Web Browser**
   - Name: Web Browser
   - Command: `https://www.google.com`
   - Args: (empty)
   - Enabled: true
   - (os.startfile or shell will open default browser)

3. **Calendar**
   - Name: Calendar
   - Command: `https://calendar.google.com`
   - Args: (empty)
   - Or attempt Windows Calendar: `explorer.exe` + args `shell:AppsFolder\Microsoft.WindowsAlarms_8wekyb3d8bbwe!App` (user can tweak).
   - Alternative simple: Notepad as "Quick Notes" for demo purposes.

Extra good seeds:
- Notepad (`notepad`)
- Command Prompt (`cmd` or `powershell`)
- File Explorer (`explorer .`)
- VS Code (if `code` is in PATH)

---

## Suggested Architecture Outline (Python + PySide6)

(High level – details can change after confirmation.)

### Data / Persistence
- `Launcher` dataclass (or Pydantic `BaseModel` for validation):
  ```python
  id: str
  name: str
  command: str
  args: str = ""
  enabled: bool = True
  working_dir: Optional[str] = None
  run_as_admin: bool = False
  show_console: bool = False
  ```
- `Settings`: trigger_width, trigger_height, dropdown_width, position_x, position_y, hover_delay_ms, animation_duration_ms, theme, hotkey, etc.
- JSON file in `platformdirs.user_config_dir("ScriptRunner") / "config.json"`
- Atomic write helper.
- Load on startup, save on changes + on exit.

### Core UI Pieces
- `MainWindow` / `TriggerWidget` (frameless, small, stays on top, transparent or styled bg).
  - Contains the downward arrow (QLabel with text or SVG, or QPushButton).
  - Mouse tracking + enter/leave.
  - Draggable (implement mouseMove with buttons).
  - Right-click → QMenu (Add..., Manage..., Settings, Exit).
- `DropdownWidget` (separate top-level widget or child that we show/hide/animate).
  - Positioned exactly below the trigger using `move(trigger.x(), trigger.y() + trigger.height())`.
  - Contains `QScrollArea` + `QVBoxLayout` of buttons.
  - Also tracks mouse leave (combined with trigger).
  - Animation: on show, set height 0 → target height with opacity 0→1 (or geometry animation).
- `LaunchButton` (QPushButton subclass or custom widget): shows name, maybe icon on left. Click → launch + hide dropdown.
- `AddEditDialog` (QDialog):
  - Name (required)
  - Command / Path (QLineEdit + "Browse..." button – QFileDialog.getOpenFileName with filters for exe/py/bat/all)
  - Parameters / Args (QLineEdit)
  - Checkbox: "Show in dropdown list" (maps to enabled)
  - (Later) Advanced: working dir, admin, console, etc.
  - On accept: create/update Launcher, persist, rebuild buttons.
- `LauncherManagerDialog` (future): QTableView or QListWidget with edit/delete/reorder buttons + test.
- `SystemTrayIcon`.

### Hover / Animation Logic (critical part)
- Use a `QTimer` (single shot, 80-150ms) on leave from *either* trigger or dropdown.
- On enter either → cancel hide timer, show/animate dropdown.
- When hiding: animate reverse, then `hide()` at end of animation.
- Keep a `mouse_in_area` flag or use `childAt` / `underMouse`.
- This is the trickiest part – we'll iterate with real testing.

### Launching
- Helper `launch(launcher)`:
  - Expand env vars.
  - If run_as_admin: use `ctypes.windll.shell32.ShellExecuteW` with "runas".
  - Else: `subprocess.Popen([command] + shlex.split(args), cwd=..., creationflags=... )`
  - Special case for URLs and shell protocols: `os.startfile(...)`
  - For .py convenience: if looks like python script and no explicit python, wrap with `py` or `sys.executable`.
- Catch errors, report via tray message or small error dialog.

### Other
- `QApplication.setQuitOnLastWindowClosed(False)` because tray + floating widget.
- Single instance guard (Qt or named mutex via win32).
- Clean shutdown: save config.
- Settings dialog (for size, animation speed, hotkey, startup, etc.).

### Project Layout (proposed)
```
script-runner/
├── docs/
│   └── LANGUAGE_RECOMMENDATION.md   (this file)
├── assets/
│   └── icon.ico
├── src/
│   ├── __init__.py
│   ├── main.py                 # entry, app setup, tray, main window
│   ├── config.py               # load/save, defaults, Launcher model
│   ├── launcher.py             # launch logic + process handling
│   ├── ui/
│   │   ├── trigger.py          # the arrow widget + drag + hover controller
│   │   ├── dropdown.py         # animated list panel
│   │   ├── button.py           # launch button
│   │   ├── add_dialog.py
│   │   └── manager_dialog.py   # optional
│   └── utils/
│       └── windows.py          # win32 helpers (admin, icons, hotkeys, startup)
├── tests/
├── pyproject.toml
├── requirements.txt
├── build.py                    # or pyinstaller spec
└── README.md
```

---

## Immediate Next Steps (Waiting on Your Confirmation)

1. **Review this document** and reply with:
   - Preferred language/framework (Python+PySide6 recommended, or C# WPF, or other).
   - Any must-have ideas from the list above to include in MVP.
   - Any constraints (e.g. no external deps beyond PySide, target .exe size limit, etc.).
   - Whether you want a design doc / wireframes before coding.

2. Once confirmed, we will:
   - Set up the project skeleton (`pyproject.toml`, gitignore, basic runnable stub).
   - Implement the floating always-on-top trigger widget first (the hardest visual/interaction piece).
   - Add hover + basic animated empty dropdown.
   - Then the add dialog + persistence + real buttons + launching + test data.
   - Polish (tray, drag, size config, icons, error handling).
   - Packaging + Windows-specific readme.

This pre-task is now complete from the research side.

**Ready when you are – what would you like to do next?**
