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
- Menu order: **Add new launcher...**, **Manage launchers...**, **Reset position & size**, then the switches **Pin dropdown open (fully expanded)**, **Show filter box in dropdown**, **Show greeting message**, and **Show execute groups**. On Windows, **Launch at Windows startup** is there too. Then **Execute Groups**, **Container Groups**, **Add Execute Group**, **Add Container Group**, **Manage Execute Groups**, **Manage Container Groups**, and **Exit**.
- **Reset position & size** puts the arrow back to the default size (120×96) near the top-left. The same action is on the tray menu.
- While **Show greeting message** is on, every launch draws a flashing border around the arrow and a bubble that reads "Resize arrow to preferred size" and "Drag arrow to preferred location". Hovering, clicking, or resizing the arrow, or clicking the bubble, fades that hint for the rest of this run. The next launch shows it again. Turning the switch off hides it until you turn the switch back on. Later launches keep the saved arrow size. The large default size is used when Runner creates its config for the first time, and when you reset position and size.
- **Execute Groups** opens the execute-group list on its own. **Container Groups** opens the main popup, which is where the container rows live.
- **Show execute groups** is off until you turn it on. With it on, and with at least one execute group saved, hover shows a second list beside the launchers, toward the middle of the screen: to the left of the launchers when the arrow is on the right half, and to the right when the arrow is on the left. Both lists open downward at the top of the screen and upward at the bottom. The execute groups list has a small **Execute Groups** heading. With no execute groups saved, hover shows the launcher list alone. The **Execute Groups** menu item opens that list by itself when you have execute groups.
- An execute group runs its launchers in list order. Rows marked **Concurrent** that sit next to each other start together. Every other row starts on its own. Runner pauses briefly between those steps, then moves on. An execute group with nothing enabled reports that there is nothing to launch.
- Drag an execute group row to reorder the execute groups. Hover that row and a list of its launchers opens beside it. Click the group row to run the group. Click a launcher in the side list to run that one. Drag those launchers to reorder them, or drag one onto another open menu to move it. Dropping a launcher on the group row adds it to that group. **Show execute groups** has to be on for that list to be there beside the main popup. Right-click a group for **Edit** or **Delete**. Deleting an execute group leaves its launchers in place. Deleting a launcher removes it from every execute group and every container group.
- A container group holds launchers in a submenu. It does not run them. Its row is in the main popup, with a ›. Until you drag it, that row is at the top. A new container group also starts at the top. Hover the row and a second list opens beside it. Click a launcher there to start it. Drag the launchers in that list to reorder them. From the main popup, drag a launcher into that open list to move it into the container. From another menu, drop it on the container row to add it, or into the open list to choose the position. Dragging a launcher off the main popup into a container or an execute group hides it from the main popup. Dragging it back onto the main popup shows it there again. Right-click the container row for **Edit** or **Delete**.
- **Add Container Group** / **Edit Container Group** asks for a name. Click a launcher to include it. Selected rows turn dark grey and move to the top in click order. Drag a selected row to change the submenu order. Each selected row has an **Only in Container Group** switch. A launcher can belong to many container groups and many execute groups.
- Whether a launcher is on the main popup is one choice. **Include in dropdown list** on the launcher screen is that choice. **Only In Groups** on an execute group, and **Only in Container Group** on a container, are the same choice turned around: on means the launcher is off the main popup. The last place you change it updates the others. The launcher still runs inside an execute group and still appears in each container submenu.
- Add or edit a launcher with **Name**, **Command / Path** and **Browse...**, **Parameters / Args**, **Include in dropdown list**, **Working directory**, and, on Windows, **Run as administrator** and **Show console**. Below those are **Container groups I belong to** and **Execute groups I belong to**. Add puts the launcher in a group. Remove takes it out. The save button is **Save**. On macOS, Browse can select an `.app` bundle.
- Turning **Include in dropdown list** off hides that launcher from the main popup. It still runs inside an execute group and still appears in a container submenu. **Only In Groups** on the execute group page is saved immediately.
- **Manage Launchers** edits, deletes, reorders, and adds launchers. The pin, filter, greeting, and execute groups switches live on the arrow menu.
- **Add Execute Group** / **Edit Execute Group** asks for a name. The page says "These items will be executed in the order it appears in the list below." Click a launcher to include it. Selected rows turn dark grey, use light text, and move to the top in the order you clicked them. Click again to remove one. Removing it also clears **Concurrent**. Drag a selected row to change the run order: the row lifts with a yellow border and the new order is applied when you release. Buttons are **Add new Launcher**, **Save**, and **Cancel**. An empty name warns "Name is required." An execute group may contain no launchers.
- **Manage Execute Groups** and **Manage Container Groups** use **Edit...**, **Delete**, **Move Up**, **Move Down**, **Add New...**, and **Close**.
- Add, Edit, Manage, group dialogs, and the file and message windows they open stay above the arrow and the lists on macOS and Windows.
- The tray menu is **Add new launcher...**, **Manage launchers...**, **Reset position & size**, **Reload config**, and **Exit Runner**. A click on the tray icon opens the launcher list.
- One instance runs at a time. Starting Runner again brings the running arrow forward.
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

You can edit the JSON or use the in-app dialogs. The config version stays 1. Launchers, execute groups, and container groups are in that file.

## Installation (development)

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

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
source .venv/bin/activate
./scripts/build-mac.sh
```

That writes `dist/Runner.app` and `dist/Runner.dmg`. `dist/` is gitignored. An unsigned build will warn in Gatekeeper on first open. Right-click the app and choose Open, or approve it in System Settings → Privacy & Security.

**Windows**

```powershell
.\scripts\build-windows.ps1
```

That writes a portable `dist\Runner.exe` for 64-bit Windows 10 or 11 on Intel or AMD. The executable icon is `assets/icon.ico`, and the file properties use the product name Runner.

Build the Windows executable on Windows, or with the Windows workflow below.

**Linux**

```bash
pip install -e ".[dev]"
./scripts/build-linux.sh
```

That writes one file, `dist/Runner`, for x86_64. It includes Python. It runs on glibc 2.35 or newer: Ubuntu 22.04, Debian 12, Fedora 36, and later releases of those families. A normal desktop already has the graphics libraries it uses. Copy the file to the machine and run it.

Nuitka is an optional smaller Windows build. The workflows use the PyInstaller scripts:

```powershell
python -m nuitka --onefile --windows-disable-console --output-dir=dist --output-filename=Runner scripts/launch.py
```

### GitHub Actions

Four workflows run when someone starts them from the Actions tab (`workflow_dispatch`). Each one uploads a build artifact. Publishing a GitHub Release is a separate step.

- **Build Windows** (`.github/workflows/windows.yml`) uploads `dist/Runner.exe` as the artifact `Runner-windows-x64`.
- **Build Linux x64** (`.github/workflows/linux-x64.yml`) uploads `dist/Runner` as the artifact `Runner-linux-x64`.
- **Build Intel Mac** (`.github/workflows/macos-intel.yml`) uploads `Runner-intel.dmg`.
- **Build Apple silicon Mac** (`.github/workflows/macos-arm64.yml`) uploads `Runner-arm64.dmg`.

### Downloads

The download on a public GitHub Release is the Windows executable. The Linux workflow produces an Actions artifact for the same kind of one-file download. There is no published Mac build. Mac users clone the repo and run `./scripts/build-mac.sh`. An Apple Developer ID signature is required before a Mac download can open without an extra approval, and this project does not have one.

The bundled app still stores config in the user config directory above.

## Development notes

The interface is PySide6. Hover, pin, and list layout are the fragile parts. Windows-only launch behavior (run as administrator, show a console, the startup registry entry, and the single-instance mutex) lives in `launcher.py` and `src/runner/utils/windows.py`.

## Roadmap

Per-launcher icons (automatic and custom) are the open item. See the Unreleased section of [CHANGELOG.md](CHANGELOG.md).

## License

MIT (or whatever you choose at release).
