# Changelog

All notable changes to Runner will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- (planning) Per-launcher icons (auto + custom).

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
