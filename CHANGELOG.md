# Changelog

All notable changes to Runner will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- Per-launcher icons (auto + custom).

## [1.1.0] - 2026-11-23

### Changed
- Add, Edit, and Manage windows, message boxes, and the date and repeat pickers follow the colour scheme (Dark, Medium, Bright) like the lists do, instead of the system's light look.
- One button order everywhere: **Cancel** then **Save**. Menu rows and buttons that open a window end in …, and labels use one capitalisation (**Add Launcher…**, **Manage Launchers…**, **Only in Groups**).
- The arrow menu groups the group actions into three submenus, **Schedules**, **Execute Groups**, and **Container Groups**, each with **Show**, **Add…**, and **Manage…**.
- The launcher screen: fields use the window's full width; **Run as administrator** and **Show console window** show only on Windows; **Include in dropdown list** sits under the fields; group membership is a tick list per kind, with schedules marked "(schedule)".
- Manage windows: **Edit**, **Delete**, and **Move** are greyed out until a row is selected, none of them acts as the default button, and an empty list says so.
- Schedule rows line up whether or not they carry the "next" tag. **Concurrent** and **Only in Groups** explain themselves on hover.
- Container groups can be dragged into a new order in **Show Container Groups**, and that order is saved. A container row only changes place; it can't be dropped into another container group, and other containers' submenus stay shut while one is dragged.
- The container group screen's switches no longer repeat "Only in Container Group" on every row; the column heading says it once.

## [1.0.14] - 2026-11-22

### Added
- Schedules: an execute group can run on dates you set. The **Schedule** switch on the execute group screen turns it into a schedule. **+** adds a date on the metal date dial, and the button beside each date sets how often it repeats on the interval rollers. Dates are listed by their next run; a new date stays at the top until the screen is reopened. **×** removes a date. Turning **Schedule** off returns the group to **Execute Groups** and greys its dates out, keeping them.
- **Schedules** on the arrow menu lists the scheduled groups with their next run; click one to edit it. **Add new Schedule...** and **Manage Schedules...** sit under **Add new launcher...** and **Manage launchers...**.
- Scheduled groups run while Runner is open. A run missed while Runner was closed or the computer was asleep is skipped.

## [1.0.13] - 2026-11-22

### Changed
- **Container Groups** on the arrow menu opens the container-group list on its own, beside the arrow, the same way **Execute Groups** opens the execute-group list. Hover a container group to open its launchers. It used to open the main popup.

### Fixed
- A list's right-click menu (**Edit**, **Delete**) could open behind the list on macOS. It now opens above every list.
- Dialogs, confirmations, and the file browser opened centred on the arrow, covering it and any open list. They now open beside the arrow and lists when the screen has room. Lists that were only open because the pointer was over them close when a dialog opens; a pinned list stays, and the dialog opens clear of it.
- The greeting's flashing rim could sit under an open list, and its bubble could open where a list was. The rim and bubble now sit above the lists and under the arrow, and the bubble opens on a side with no list.
- On macOS a list that took focus as it opened, such as a pinned list at start-up, could cover the bottom edge of the arrow. The arrow now goes back on top.
- With an arrow wider than the launcher list, the execute-groups list beside it opened under the arrow's corner. It now opens clear of the arrow.
- Choosing **Container Groups** or **Execute Groups** could close that list a moment later, because the launcher list it replaced still reported the pointer leaving.

## [1.0.12] - 2026-11-19

### Changed
- **Opacity** applies to the arrow only. The lists are always solid, so their rows are easy to read.
- The lists open and close with a fade, at their full size and in place. They used to grow out of the arrow and shrink back into it. A list closing toward the arrow could move its rows under the pointer, and the list then reopened as if you had moved onto it, making it bounce.

### Fixed
- The arrow menu and tray menu showed "Reset position  size" with a double space, because `&` in a menu label marks a keyboard shortcut and is not shown. It now reads **Reset position and size**.
- A list that needed a little more than 420 px, such as twelve launchers and a container group, stopped at 420 px and scrolled the last few pixels; the scrollbar appeared just after the list opened. A list now uses the room on the roomier side of the arrow before it scrolls.
- A list opening above the arrow sat one pixel too high while it faded in, then dropped into place.
- Resizing or moving the arrow could get stuck. On macOS the launcher list opening under the pointer could take the mouse release, so the arrow never learned the button was up: it kept resizing toward the pointer with nothing held, and the new size or position was not saved until Runner quit. This is also what made **Reset position and size** seem not to work: the stuck resize pulled the arrow straight back out. A move with the button up now ends the gesture and saves it, and Reset drops any gesture in progress.
- Dragging the very edge of the arrow on macOS resized it through the system, not through Runner: no press or release reached Runner, so the size was not saved until quit and resizing did not dismiss the greeting. A size the arrow did not drag to itself is now saved once it stops changing.

### Added
- Dragging the arrow closes every open list as soon as it starts to move, and nothing reopens until it is dropped. On the drop they open again where the arrow lands, as a hover opens them. A click without a move closes nothing.
- **Reset position and size** shows the greeting bubble again ("Resize arrow to preferred size", "Drag arrow to preferred location"), even if it was dismissed or **Show greeting message** is off.

## [1.0.11] - 2026-11-18

### Changed
- **License.** Runner is now licensed under the PolyForm Strict License 1.0.0, with added permissions for use for any purpose (including at work) and for rebuilding with your own version of the LGPL libraries. You may use it free of charge, but not change it or redistribute it. Earlier metadata said MIT; this replaces it. See `LICENSE`.
- Dependencies are pinned to exact versions (PySide6-Essentials 6.12.0, platformdirs 4.14.6, PyInstaller 6.22.3), so every build uses the Qt that was tested. Runner depends on `PySide6-Essentials` instead of `PySide6`, which skips about 175 MB of Qt add-ons (WebEngine, Pdf, and others) Runner never used; the built app is unchanged. Python 3.11 or newer is required; the pinned Qt already needed it.
- Pushing a version tag publishes the release: a new Release workflow checks the tag against the version, runs the tests, builds Windows and Linux from that commit, and attaches both files with the changelog notes.
- `build-windows.ps1` and `build-linux.sh` work like `build-mac.sh`: they use the project's `.venv` when it exists, check the version, and run the lint check and the tests first (`-SkipTests` / `--skip-tests`). A failed PyInstaller run now stops the Windows script; it used to print "Build complete!" anyway. `-OneDir` replaces `-OneFile:$false`.
- The Windows file properties take their version from `pyproject.toml` at build time, and the Windows build checks the finished exe reports it. `file_version_info.txt`, which had to be edited by hand for every release, is gone.
- UPX compression is off. It could break Qt DLLs and trip antivirus, and made a build depend on whether UPX was installed.
- A lint check (`ruff`, unused and undefined names) runs before the tests, in `build-mac.sh` and on GitHub. The tests now also run on Linux.

### Added
- `THIRD-PARTY-NOTICES.txt`, with the licenses of Qt, PySide6, and Shiboken6 (LGPL 3), Python and the libraries it includes, platformdirs, and the PyInstaller bootloader. It and `LICENSE` are inside every build, in the Mac disk image, and attached to every release. The Windows file properties and the Mac app name 34minutespast12 as the copyright holder.

### Security
- Runner works from your home folder. Windows looks for a bare program name such as `notepad` in the current folder before PATH, and double-clicking `Runner.exe` in Downloads made Downloads that folder, so a downloaded `notepad.exe` could run in place of the real one. A launcher with no working directory now starts in the home folder.
- The single-instance socket is per user and only its owner can connect. On Linux it lives in `XDG_RUNTIME_DIR` instead of the shared `/tmp`, where another user could claim the name first and stop Runner from starting. On Windows the sign-in session's mutex alone decides whether Runner is already running.
- Runner warns when it is started as administrator (Windows) or root (macOS, Linux), because every program it launches would get the same rights without asking. **Quit Runner** is the default; **Keep Running** continues.
- Releases include `SHA256SUMS.txt` and a signed build attestation for each file. `gh attestation verify <file> --repo 34Minutes/runner` confirms a download was built by the release workflow from this repository.
- GitHub Actions are pinned to full commit IDs instead of tags such as `@v4`, which their owners can move. They are also updated to current releases that run on Node.js 24.
- On macOS and Linux the config file and its backups are readable only by you (0600), and the config folder is 0700. Launcher arguments can hold tokens or passwords. An existing file is tightened the next time Runner saves.

### Fixed
- Windows: if Windows refuses to add or remove Runner from the startup list, **Launch at Windows startup** says so. It failed silently.
- Errors that were caught and ignored everywhere are now caught only where they are expected (a row already deleted, a missing Windows API). An unexpected error is no longer hidden. A launch failure is still shown to the user and does not stop an execute group.

### Removed
- The `box_opacity` setting. Its only control was the Opacity window removed in 1.0.10. The arrow's box uses the color scheme's own opacity; an old config that has the key still loads, and the key is dropped on the next save.

## [1.0.10] - 2026-11-17

### Changed
- A config file with a bad entry no longer resets everything. Bad launchers and groups are skipped, a setting with the wrong type goes back to its default, and Runner lists what it skipped. The original file is copied to `config.<date>.bak.json` first. A file that cannot be read at all is moved to a dated backup, and earlier backups are never overwritten.
- The arrow's position is saved when a drag ends, not on every mouse move.
- `scripts/build-mac.sh` works from any folder, runs the tests first, takes its version from `pyproject.toml`, and installs to `/Applications` with `--deploy`. A test workflow runs the suite on macOS and Windows on every push.
- Internal: the window wiring moved from one long `main()` function into `RunnerController` (`controller.py`). The execute-group and container-group screens share one base dialog, and so do their manager screens.
- Whether a launcher is on the main popup is stored once, as `show_in_main`. Include in dropdown list, Only In Groups, and Only in Container Group all show that one setting, so they can no longer disagree. The config version is now 2, and a version 1 file is converted on load with the same result it had before. A launcher hidden from the main popup now always runs in its execute groups and appears in its containers; an old hand-edited `"enabled": false` used to drop it from them silently.
- The Opacity and Decay rate sliders write the config once they stop moving, not on every tick.
- Tests can no longer read or write the real config file. Some did, and replaced the user's launchers during a test run.

### Fixed
- **Reload config** applies everything in the file. The arrow and the lists were still reading the settings from before the reload, so Pin and the menu switches stopped matching.
- On macOS, a command on PATH (`say`, `python3`, `code`) runs as a program. It was sent to `open -a` as an app name. A path with spaces is no longer mistaken for an app name either.
- The Command field can hold a program and its arguments, such as `python3 tool.py`.
- A `.py` launcher in the packaged app runs with Python. It started a second copy of Runner instead.
- **Run as administrator** quotes arguments that contain spaces, and reports a failure or a declined UAC prompt.
- Windows: launchers no longer run through `cmd.exe`, so arguments containing `&`, `|`, `^`, or `%` reach the program as typed. A program on PATH starts directly; any other name (an App Paths name such as `brave`, a shortcut, or a document) opens the way the Run dialog would, and a name Windows cannot find is reported instead of failing silently.
- A `~` argument, such as the Finder sample's, opens the home folder.
- The arrow can be dragged onto any monitor. It was held to the primary screen.
- Add, Edit, and Manage dialogs are raised again when the arrow or a list comes to the front. The check that skips popup menus also skipped every Runner window, because Qt's Tool window type shares its bits with Popup, so this never ran. On Windows a dialog could end up behind the arrow.
- Programs started from the packaged Runner no longer inherit its internal `QT_PLUGIN_PATH`. A terminal opened from Runner passed that on, and any Qt program run from it crashed while loading two copies of Qt.

### Removed
- The second **Opacity** item on the arrow menu, under Color Schemes, and the separate window it opened for the arrow's box. The **Opacity** and **Decay rate** sliders inside the menu stay. A box opacity already saved in the config is still used.

## [1.0.9] - 2026-11-17

### Changed
- A list that is closing on its own fades in place. It no longer slides or shrinks while the opacity changes. Moving the pointer off the list still closes it. With **Show execute groups** on, the main popup and the execute-groups list still open and close together.
- **Exit** is the last item on the arrow menu, under its own separator.
- The arrow menu has an **Opacity** slider and a **Decay rate** slider above **Color Schemes**. That Opacity is how solid the arrow and the lists are. Decay rate is how fast a list fades after the pointer leaves. Dragging the slider to the right makes the fade faster. **Opacity** under **Color Schemes** is unchanged: it opens the slider for the arrow's box.

### Fixed
- Clicking a launcher in the main popup also closes the execute groups list. The two lists close together.
- A long list scrolls inside its frame. The scrollbar was missing because the list grew to the full content height and then got clipped.
- The greeting bubble and flashing border line up with the arrow. The first placement of those windows was a title bar too high.
- Choosing a launcher or an execute group closes the open lists immediately. A fade was cancelled when the pointer was still over the list, which happened when the launched app was already focused.

## [1.0.8] - 2026-11-17

### Added
- Color schemes. Right-click the arrow and choose **Color Schemes**, then **Dark**, **Medium**, or **Bright**. Dark is the original look and the default. The startup greeting stays yellow on every scheme.
- **Show group contents** on an execute group. It stays off until turned on, and hovering that group stays collapsed until then.
- **Opacity**, under **Color Schemes**. It opens a slider for how solid the arrow's box is. The chevron keeps the color scheme's own opacity.

### Changed
- With **Show execute groups** on, hovering the arrow opens and closes the main popup and the execute-groups list together. They share one fade and one height. A list that is already fully open stays open. Container submenus and an execute group's side list still move on their own.

## [1.0.7] - 2026-11-16

### Changed
- The main popup, the groups list, and a group's side list fade out over a quarter of a second when the pointer leaves. Moving onto a list while it is fading brings it back open. Opening is unchanged.

## [1.0.6] - 2026-11-13

### Added
- Drag a container row among the launchers in the main popup. Drag the launchers inside a container to reorder that container. Drag a launcher from any open menu onto another menu to move it, including from a container to an execute group and from an execute group onto the main popup. Hover an execute group to open its launchers. A click on the group row still runs the group.

### Changed
- The arrow menu lists **Execute Groups**, **Container Groups**, **Add Execute Group**, **Add Container Group**, **Manage Execute Groups**, then **Manage Container Groups**. **Container Groups** opens the main popup.
- **Include in dropdown list**, **Only In Groups**, and **Only in Container Group** are one choice per launcher. The last change updates the other two. The edit-launcher screen no longer has an **Only In Groups** switch.

## [1.0.5] - 2026-11-13

### Added
- Container groups. **Add Container Group** on the arrow menu names a submenu and picks launchers for it. The row appears at the top of the main popup. Hovering it opens those launchers, and a click starts one. **Only in Container Group** hides a launcher from the main popup while any container it belongs to has that switch on. When the switch is off on every one of those containers, the launcher shows in the main popup again. It can belong to many container groups and many execute groups.
- Add and edit launcher show **Container groups I belong to** and **Execute groups I belong to**, with add and remove.

### Changed
- Groups that run their launchers are called **Execute Groups**. The list heading, the arrow menu, and the add, edit, and manage windows use that name.

### Fixed
- The launcher list, the execute-group list, and a container submenu open with no row highlighted. Arrow keys, Home, and End choose a row. Enter launches only a row that is already highlighted.

## [1.0.4] - 2026-11-12

### Added
- Linux x86_64 build. `.github/workflows/linux-x64.yml` builds one `dist/Runner` file on Ubuntu 22.04 (glibc 2.35) for current desktop distros. `scripts/build-linux.sh` is the same build locally.

### Changed
- The arrow is slightly more transparent. The dark pill alpha is 170, and the chevron alpha is 210.

## [1.0.3] - 2026-11-05

### Added
- Groups. The arrow menu has **Add group**, **Manage groups**, and **Groups**. A group runs its launchers in list order. Neighbouring rows marked **Concurrent** start together. Every other row starts on its own, after a short pause. Runner then moves on.
- **Show groups**, under **Show greeting message**. When it is on, hover shows the groups list beside the launchers, toward the middle of the screen, with a **Groups** heading. With no groups, nothing is shown for groups. The **Groups** menu item still opens that list on its own. A new group appears on the next hover and on a list that is already open.
- **Only In Groups** on Add/Edit Launcher and on the group page. That launcher stays off the hover list and still runs inside a group. On the group page the switch is saved immediately.
- Drag on the launcher list and the groups list lifts the pressed row, yellow border included when that row is already highlighted, and slides the other rows apart. A short click still launches. Dragging a group reorders groups only.
- On Add Group and Edit Group, selected rows are dark grey and move to the top in click order. Dragging one lifts it with a yellow border. The new order is applied on release. Clearing a row also clears **Concurrent**. Deleting a group leaves its launchers in place.

### Changed
- While **Show greeting message** is on, every launch shows the flashing border and a bubble with two lines: "Resize arrow to preferred size" and "Drag arrow to preferred location". Dismissing it lasts for that launch. The next launch shows it again. A saved arrow size is left alone. The large default size is only for a brand-new config and for **Reset position & size**.
- The arrow menu stays open while its switches are clicked. It closes when the pointer leaves the menu, or when a normal action is chosen. After it closes, the lists hide when the pointer is outside the arrow and the lists. A pinned dropdown stays open.

### Fixed
- Add, Edit, Manage, the group dialogs, and the file and message windows they open stay above the arrow and the lists on macOS and Windows.

## [1.0.2] - 2026-11-05

### Added
- A startup hint. The first launch uses a large arrow, a flashing border, and a resize bubble. Later launches keep the saved size and position and show the border only, until **Show greeting message** is turned off. Hover, click, or resize fades the hint for that launch.
- **Reset position & size** on the arrow menu and the tray menu.
- Drag a dropdown row to reorder the launchers. Right-click a row for **Edit** and **Delete**.

### Fixed
- On macOS, Browse in Add/Edit Launcher can select an `.app` bundle instead of opening it as a folder.

## [1.0.1] - 2026-10-16

### Fixed
- Windows: Add, Edit, and Manage opened behind the always-on-top arrow. Those dialogs, and the file and message windows they open, now stay above the arrow.

## [1.0.0] - 2026-10-16

First stable release.

### Changed
- Version set to 1.0.0. The alpha and beta tags remain the test builds that led here.
- The project name is Runner. The package, spec, docs, and macOS app are no longer called script-runner.

## [BETA_1.0.1] - 2026-09-01

Second beta release of Runner.

### Added
- Keyboard navigation in the dropdown: Up/Down arrows to move selection, Home/End for first/last, Enter/Return to launch the current item, Esc to clear filter or hide list. Down arrow from the filter search box jumps focus into the results list. Live filter auto-selects the first matching launcher for immediate keyboard launch. Selection is visually highlighted (distinct border/background) and scrolls into view. Works in both pinned and hover-triggered modes.
- Windows: "Launch at Windows startup" toggle in the arrow right-click menu (persisted, creates/updates a HKCU Run entry). The entry is re-created on launch if enabled (survives moving the exe).
- Windows: Improved single-instance handling using a named mutex (in addition to the existing local socket "wake up" mechanism).
- Proper Windows executable metadata: `Runner` as Product Name (visible in File Properties, Task Manager, etc.) via `file_version_info.txt`.
- `assets/icon.ico`: Multi-resolution arrow icon (dark rounded background + blue chevron) matching the trigger widget style. Used for the .exe icon and taskbar.

### Changed
- Version bump to 1.0.1b1 for BETA_1.0.1.
- PyInstaller builds strip unused Qt (PDF, QML/Quick, Virtual Keyboard, OpenGL, SVG, extra image codecs, translations). macOS `.app` is ~58 MB (was ~88 MB); `.dmg` is ~23 MB (was ~36 MB). `runner.spec` is now the canonical packager for macOS and Windows.

## [BETA_1.0.0] - 2026-06-05

First beta release of Runner.

### Added
- Toggle switches (animated sliding on/off style) replace all QCheckBox controls for settings.
- "Pin dropdown open" and "Show filter box in dropdown" are now available directly as sliding toggle switches inside the arrow's right-click context menu (via QWidgetAction) for quick access. (The Manage dialog now focuses purely on launcher list management; the toggles remain available there too for discoverability.)
- Right-click context menu on the arrow now auto-closes when the mouse moves away from it (250ms grace period to allow moving between items), for a lighter floating-widget UX. Includes the embedded toggle switches.

### Changed
- Smart dropdown placement relative to the trigger arrow: defaults to expanding below (with horizontal centering), but automatically flips to expand above (with upward grow animation from the arrow) when near the bottom of the screen, and/or shifts left/right to keep the full dropdown visible when near screen edges (including bottom-right corner cases etc.). The list is now guaranteed to stay on-screen no matter where the (draggable/resizable) arrow is placed.
- Version bump to 1.0.0b1 for the beta.

### Fixed
- Various menu and toggle integration polish from alpha (text color, sizing of switches in menu, positioning robustness).

## [ALPHA_1.0.1] - 2026-06-05

### Added
- Live search/filter box at top of dropdown ("Filter launchers..."): type to narrow visible buttons by name or command; Esc in filter clears it (second Esc hides list if not pinned); height adjusts to filtered set; filter cleared on hide.
- Full exposure of advanced launcher options (working directory + browse, run as administrator, show console) in the Add/Edit dialog and reflected in Manage list (flags like (admin), [wd] in item text, wd in tooltip).

### Fixed
- Arrow positioning on startup (and re-shows) with pinned_open or after custom trigger resize: the dropdown could appear to cover the arrow ("arrow behind list"). Root cause was macOS Frameless+Tool window creation ignoring pre-show `move()` (leading to ~20px wrong y) plus z-order (dropdown `raise_()` winning).
  Fixed comprehensively:
  - Defer initial `apply_pinned_state()` with `QTimer.singleShot(0)` after `trigger.show()`, plus `showEvent` re-apply size and `raise_()` on trigger.
  - Dropdown remembers anchor trigger; re-calls `position_below()` (with 3px overlap for visual tuck) *right after* internal `show()` in `start_show_animation()` and `ensure_visible_and_sized()`.
  - `trigger.raise_()` + `dropdown.stackUnder(trigger)` after every list show/re-show path (startup, hover, tray, drag-while-pinned, post-launch, etc.).
  - 3px negative y overlap so arrow tucks over list top; arrow on top in stacking produces clean "handle on list" look.
- (earlier) Initial startup y-calc for custom trigger sizes when pinned (addressed as part of the above robustness).

### Changed
- Version bump to 1.0.0a2 for the alpha.

## [ALPHA_1.0.0] - 2026-06-04

First public alpha release.

### Added
- Pinned "always expanded" dropdown mode (initially toggled in Manage dialog; later moved to arrow right-click menu as direct sliding toggle). The list stays visible after launches and mouse leaves.
- Resizable trigger widget: drag any edge or corner of the small arrow widget; size persisted in settings.
- Robust dropdown layout and hover/pinned interactions:
  - List stays fully expanded (with proper button spacing) when pinned, even after clicking launchers or moving/resizing the trigger.
  - Improved hover handoff between trigger and list without premature collapse.
  - Post-launch behavior respects pinned state.
- Fix button spacing in the dropdown list (was squished/zero or negative gaps due to QScrollArea + dynamic rebuild + height calc; now uses explicit child min+spacing sum + viewport chrome buffer).
- System tray icon + menu (Add, Manage, Reload config, Exit); left-click tray also toggles list.
- Full "Manage launchers..." dialog with edit/delete/reorder (up/down), add new. (Global toggles for pinning and filter visibility were later moved to the arrow's right-click menu.)
- Draggable + resizable + persisted position/size for the trigger.
- Cross-platform launching (Windows primary, solid macOS support with .app / name handling, Linux basics).
- Test data seeds appropriate per platform (macOS uses app names like Calculator/Terminal; Windows uses calc, notepad, explorer, etc.).
- Config persistence via JSON in platformdirs user config dir (atomic writes, corruption recovery).
- Animated show/hide for dropdown (fade + height with easing).
- Add/Edit launcher dialog (Name, Command/Path + Browse, Parameters/Args, Include in list).
- Context menu on trigger (right-click) and tray for Add/Manage/Exit.
- Launching support for URLs/protocols, bare commands, full paths, Python scripts (with platform py launcher on Win), working dir, run-as-admin (Win), show-console (Win).

### Changed
- Global hotkey support removed (was added then reverted for alpha; pynput dependency dropped for cross-platform reliability and macOS dialog quit issues). Simplification for v1 alpha.
- Removed aggressive always-on-top behavior (earlier experiments with WindowStaysOnTopHint and recovery logic were dialed back to avoid focus stealing and menu problems).
- "Manage launchers..." moved to right-click / tray only (no longer a link inside the dropdown itself).
- Add/Edit dialog "Ok" button text changed to "Save".
- Improved macOS stability: early ActivationPolicyAccessory, no hidden QMainWindow, better custom context menu handling for frameless Tool windows, QInputDialog fixes to prevent app quit.
- Trigger tooltip updated to mention right-click for Manage.
- Many hover/animation/timer robustness fixes.

### Fixed
- macOS file dialog for .app bundles.
- Reliable context menu on trigger (custom policy + zero-delay popup).
- Prevent app from quitting on macOS when using QInputDialog (or other native dialogs like for hotkey).
- Improve macOS app launching with URL/args for browsers like Brave (open -a ... --args).
- Improve Windows launching for browser + URL in parameters (shell=True + list2cmdline).
- Robust Windows launching via ShellExecute for bare commands like 'calc'.
- UnboundLocalError for QTimer on normal startup.
- Always-on-top recovery issues (ultimately removed).
- Focus/menu disappear issues.
- Button layout/spacing calculation bugs in dropdown.
- Various small polish and edge cases in drag, leave events, pinned state.

### Notes
- Initial implementation work spanned multiple iterations from basic floating widget through full feature set.
- Target distribution remains single-file exe on Windows via PyInstaller (spec provided).
- Developed primarily on macOS targeting Windows users (and macOS users).

[ALPHA_1.0.0]: https://github.com/... (tag ALPHA_1.0.0)
