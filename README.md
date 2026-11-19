# Runner

A lightweight floating launcher for scripts and applications. One arrow on the desktop opens everything you want to start.

## Features

- A small frameless arrow stays above other windows. Drag it to move it. Drag an edge or corner to resize it. Position and size are saved.
- Hover the arrow to open the launcher list. The list opens downward, or upward when the arrow is near the bottom of the screen, and shifts so it stays on screen.
- The list hides when the pointer leaves, unless **Pin dropdown open** is on. A press that moves less than about 10 pixels still launches. A longer drag reorders the row, or moves that launcher onto another open menu.
- Drag a row to reorder it. The row lifts out of the list with a yellow border, including the row that is already highlighted, and the other rows slide apart to open a gap. Release saves the new order. Rows hidden by the filter stay where they are. A container row drags the same way and can sit between launchers. Drag a launcher into another open menu to move it there.
- Right-click a row for **Edit** or **Delete**.
- A filter box at the top narrows the list by name or command. The placeholder is "Filter launchers...". The list opens with no row highlighted. Arrow keys move the highlight, Home and End jump to the ends, Enter launches the highlighted row, and Esc clears the filter or hides the list.
- Right-click the arrow for actions and switches. The menu stays open while you click a switch. It closes when the pointer leaves the menu, or when you choose a normal action.
- Menu order: **Add new launcher...**, **Manage launchers...**, **Reset position and size**, then the switches **Pin dropdown open (fully expanded)**, **Show filter box in dropdown**, **Show greeting message**, and **Show execute groups**. On Windows, **Launch at Windows startup** is there too. Then **Execute Groups**, **Container Groups**, **Add Execute Group**, **Add Container Group**, **Manage Execute Groups**, **Manage Container Groups**, an **Opacity** slider, a **Decay rate** slider, **Color Schemes**, and **Exit**. **Opacity** is how solid the arrow is; the lists are always solid. **Decay rate** is how fast a list fades after the pointer leaves. **Exit** is last, under its own separator.
- **Reset position and size** puts the arrow back to the default size (120×96) near the top-left. The same action is on the tray menu.
- While **Show greeting message** is on, every launch draws a flashing border around the arrow and a bubble that reads "Resize arrow to preferred size" and "Drag arrow to preferred location". Hovering, clicking, or resizing the arrow, or clicking the bubble, fades that hint for the rest of this run. The next launch shows it again. Turning the switch off hides it until you turn the switch back on. Later launches keep the saved arrow size. The large default size is used when Runner creates its config for the first time, and when you reset position and size.
- **Execute Groups** opens the execute-group list on its own. **Container Groups** opens the main popup, which is where the container rows live.
- **Show execute groups** is off until you turn it on. With it on, and with at least one execute group saved, hover shows a second list beside the launchers, toward the middle of the screen: to the left of the launchers when the arrow is on the right half, and to the right when the arrow is on the left. Both lists open downward at the top of the screen and upward at the bottom. The execute groups list has a small **Execute Groups** heading. With no execute groups saved, hover shows the launcher list alone. The **Execute Groups** menu item opens that list by itself when you have execute groups.
- An execute group runs its launchers in list order. Rows marked **Concurrent** that sit next to each other start together. Every other row starts on its own. Runner pauses briefly between those steps, then moves on. An execute group with no launchers reports that there is nothing to launch.
- Drag an execute group row to reorder the execute groups. Hover that row and a list of its launchers opens beside it. Click the group row to run the group. Click a launcher in the side list to run that one. Drag those launchers to reorder them, or drag one onto another open menu to move it. Dropping a launcher on the group row adds it to that group. **Show execute groups** has to be on for that list to be there beside the main popup. Right-click a group for **Edit** or **Delete**. Deleting an execute group leaves its launchers in place. Deleting a launcher removes it from every execute group and every container group.
- A container group holds launchers in a submenu. It does not run them. Its row is in the main popup, with a ›. Until you drag it, that row is at the top. A new container group also starts at the top. Hover the row and a second list opens beside it. Click a launcher there to start it. Drag the launchers in that list to reorder them. From the main popup, drag a launcher into that open list to move it into the container. From another menu, drop it on the container row to add it, or into the open list to choose the position. Dragging a launcher off the main popup into a container or an execute group hides it from the main popup. Dragging it back onto the main popup shows it there again. Right-click the container row for **Edit** or **Delete**.
- **Add Container Group** / **Edit Container Group** asks for a name. Click a launcher to include it. Selected rows turn dark grey and move to the top in click order. Drag a selected row to change the submenu order. Each selected row has an **Only in Container Group** switch. A launcher can belong to many container groups and many execute groups.
- Whether a launcher is on the main popup is one choice. **Include in dropdown list** on the launcher screen is that choice. **Only In Groups** on an execute group, and **Only in Container Group** on a container, are the same choice turned around: on means the launcher is off the main popup. All three show the same setting, so changing one changes the others. The launcher still runs inside an execute group and still appears in each container submenu.
- Add or edit a launcher with **Name**, **Command / Path** and **Browse...**, **Parameters / Args**, **Include in dropdown list**, **Working directory**, and, on Windows, **Run as administrator** and **Show console**. Below those are **Container groups I belong to** and **Execute groups I belong to**. Add puts the launcher in a group. Remove takes it out. The save button is **Save**. On macOS, Browse can select an `.app` bundle.
- Turning **Include in dropdown list** off hides that launcher from the main popup. It still runs inside an execute group and still appears in a container submenu. **Only In Groups** on the execute group page is saved immediately.
- **Manage Launchers** edits, deletes, reorders, and adds launchers. The pin, filter, greeting, and execute groups switches live on the arrow menu.
- **Add Execute Group** / **Edit Execute Group** asks for a name. The page says "These items will be executed in the order it appears in the list below." Click a launcher to include it. Selected rows turn dark grey, use light text, and move to the top in the order you clicked them. Click again to remove one. Removing it also clears **Concurrent**. Drag a selected row to change the run order: the row lifts with a yellow border and the new order is applied when you release. Buttons are **Add new Launcher**, **Save**, and **Cancel**. An empty name warns "Name is required." An execute group may contain no launchers.
- **Manage Execute Groups** and **Manage Container Groups** use **Edit...**, **Delete**, **Move Up**, **Move Down**, **Add New...**, and **Close**.
- Add, Edit, Manage, group dialogs, and the file and message windows they open stay above the arrow and the lists on macOS and Windows.
- The tray menu is **Add new launcher...**, **Manage launchers...**, **Reset position and size**, **Reload config**, and **Exit Runner**. A click on the tray icon opens the launcher list.
- One instance runs at a time. Starting Runner again brings the running arrow forward.
- Started as administrator (Windows) or root (macOS, Linux), Runner warns that every program it launches would get the same rights, and offers **Quit Runner** or **Keep Running**. Use **Run as administrator** on a launcher instead; it asks each time.
- Launch executables, scripts, URLs, protocols, macOS app names, or any command the system can start.
- Config is JSON in the platform user config directory, written atomically. Old files that have no groups still load.
- macOS and Windows are the supported platforms. Linux can start basic commands.

See [CHANGELOG.md](CHANGELOG.md) for release history. [docs/LANGUAGE_RECOMMENDATION.md](docs/LANGUAGE_RECOMMENDATION.md) records the original technology choice, from before the app was built.

## Usage

1. The arrow sits on the screen. The app stays out of the Dock, and on Windows it stays off the taskbar.
2. Hover it to open the launcher list. Container groups start at the top of that list. Drag one to move it among the launchers. Hover one to open its launchers. With **Show execute groups** on, the execute groups list opens beside the launchers when you have execute groups. Hover an execute group to open its launchers.
3. Click a launcher to start it, including one in a container submenu or an execute group's side list. Click an execute group row to start that group. Drag a launcher onto another open menu to move it. The lists hide when the dropdown is unpinned.
4. Drag a row to reorder it. Right-click a row to edit or delete it.
5. Right-click the arrow for the switches and for add, manage, groups, reset, and exit. Or use the tray icon.
6. Drag the arrow to move it. Drag its edges or corners to resize it.

The first run creates a config and sample launchers (Calculator, Calendar, a web browser, and a few platform tools) and uses the default arrow size. Later runs keep the arrow where you left it.

## Configuration

Stored in the platform user config directory:

- Windows: `%APPDATA%\Runner\config.json`
- macOS: `~/Library/Application Support/Runner/config.json`

On macOS and Linux only you can read the file (0600), because launcher arguments may hold tokens or passwords. Anything that can write this file decides what your launchers run, so treat a config file from someone else like a program from them. A launcher with no working directory starts in your home folder.

You can edit the JSON or use the in-app dialogs. Launchers, execute groups, and container groups are in that file. The config version is 2; a version 1 file is converted when Runner loads it.

## Installation (development)

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Versions are pinned exactly in `pyproject.toml`, so every build uses the Qt that was tested. To update one, change the number, reinstall, and run `ruff check src tests` and `pytest`.

## Running

```bash
runner
# or from the source tree
PYTHONPATH=src python -m runner
```

## Packaging

Give clients a bundled app. PyInstaller is the supported bundler. `runner.spec` keeps the Qt modules this app uses (QtCore, QtGui, QtWidgets, QtNetwork, QtDBus) and leaves out the rest. Use the spec. A raw `pyinstaller --onefile` command skips that strip.

**macOS**

```bash
./scripts/build-mac.sh            # test, then build
./scripts/build-mac.sh --deploy   # also install to /Applications and start it
```

It runs the lint check and the tests first (`--skip-tests` to skip them), then writes `dist/Runner.app` and `dist/Runner.dmg`. It works from any folder. `--deploy` quits a running installed Runner, replaces `/Applications/Runner.app`, and opens the new one. The version comes from `pyproject.toml`; the build stops if `src/runner/__init__.py` disagrees. `dist/` is gitignored. An unsigned build will warn in Gatekeeper on first open. Right-click the app and choose Open, or approve it in System Settings → Privacy & Security.

**Windows**

```powershell
.\scripts\build-windows.ps1
```

It runs the lint check and the tests first (`-SkipTests` to skip them), then writes a portable `dist\Runner.exe` for 64-bit Windows 10 or 11 on Intel or AMD. `-OneDir` writes a `dist\Runner\` folder instead. The executable icon is `assets/icon.ico`. The file properties show the product name Runner and the version from `pyproject.toml`, and the build stops if the finished exe reports a different version. The project's `.venv` is used when it exists.

Build the Windows executable on Windows, or with the Windows workflow below.

**Linux**

```bash
./scripts/build-linux.sh
```

It runs the lint check and the tests first (`--skip-tests` to skip them; without a display it uses `xvfb-run`), then writes one file, `dist/Runner`, for x86_64. It includes Python. It needs the glibc of the machine that built it, or newer, and the script prints which one that is. The GitHub workflow builds on Ubuntu 22.04 (glibc 2.35), so its file runs on Ubuntu 22.04, Debian 12, Fedora 36, and later releases of those families. A normal desktop already has the graphics libraries it uses. Copy the file to the machine and run it.

Nuitka is an optional smaller Windows build. The workflows use the PyInstaller scripts:

```powershell
python -m nuitka --onefile --windows-disable-console --output-dir=dist --output-filename=Runner scripts/launch.py
```

### GitHub Actions

- **Tests** (`.github/workflows/tests.yml`) runs on every branch push and pull request: a lint check (`ruff`), then the test suite on macOS, Windows, and Linux.
- **Release** (`.github/workflows/release.yml`) runs when a version tag is pushed:

  ```bash
  git tag -a 1.0.11 -m 1.0.11 && git push origin 1.0.11
  ```

  The tag must match the version in `pyproject.toml` and `src/runner/__init__.py`, and `CHANGELOG.md` must have a `## [1.0.11]` section. It runs the tests, builds Windows and Linux from the tagged commit, and publishes the GitHub Release with that changelog section as its notes and `Runner-<version>-windows-x64.exe`, `Runner-<version>-linux-x64`, and `SHA256SUMS.txt` attached. Each file also gets a signed build attestation, so anyone can check a download came from this workflow with `gh attestation verify <file> --repo 34Minutes/runner`. Starting **Release** from the Actions tab is a dry run for the version in `pyproject.toml`: it does everything except publish.
- **Build Windows**, **Build Linux x64**, **Build Intel Mac**, and **Build Apple silicon Mac** can also be started from the Actions tab. Each uploads a build artifact (`Runner-windows-x64`, `Runner-linux-x64`, `Runner-intel.dmg`, `Runner-arm64.dmg`) without publishing anything.

Every action is pinned to a full commit ID, with its version in a comment, so a moved tag cannot change what runs. To update one, look up the new release's commit and replace both.

### Downloads

Each GitHub Release has the Windows executable, the Linux one-file program, `LICENSE`, and `THIRD-PARTY-NOTICES.txt`. There is no published Mac build. Mac users clone the repo and run `./scripts/build-mac.sh`. An Apple Developer ID signature is required before a Mac download can open without an extra approval, and this project does not have one.

The bundled app still stores config in the user config directory above.

## Development notes

The interface is PySide6. `main.py` starts Qt and the single-instance check, then `RunnerController` in `controller.py` owns the arrow, the four lists, the dialogs, and the tray. Hover, pin, and list layout are the fragile parts. Windows-only launch behavior (run as administrator, show a console, the startup registry entry, and the single-instance mutex) lives in `launcher.py` and `src/runner/utils/windows.py`.

## Roadmap

Per-launcher icons (automatic and custom) are the open item. See the Unreleased section of [CHANGELOG.md](CHANGELOG.md).

## License

Copyright (c) 2026 34minutespast12. See [LICENSE](LICENSE).

- You may download and use Runner free of charge, for any purpose, including at work.
- You may not change it, build new works from it, or give copies of it to others. Point people to the [releases page](https://github.com/34Minutes/runner/releases) instead.
- Runner comes as is, without warranty.

The source code is public so you can read it and check what Runner does. It is source-available, not open source: a GitHub fork is only a copy and grants no extra rights.

Runner includes Qt, PySide6, and Shiboken6 under the GNU LGPL version 3, plus Python and other components under their own licenses. Those parts keep their own terms, and you may rebuild Runner with your own version of the LGPL libraries. See [THIRD-PARTY-NOTICES.txt](THIRD-PARTY-NOTICES.txt). Both files are attached to every release and included in the builds.
