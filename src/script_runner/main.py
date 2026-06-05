"""Main entry point for Script Runner.

Wires together:
- Config
- Trigger widget (always on top arrow)
- Animated dropdown
- Add/Edit dialog
- Launching
- System tray
- Test data seeding
"""

from __future__ import annotations

import sys
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QAction
from PySide6.QtWidgets import (
    QApplication,
    QSystemTrayIcon,
    QMenu,
    QMessageBox,
)

from .config import ConfigManager, Launcher, AppConfig
from .launcher import launch
from .ui.trigger import TriggerWidget
from .ui.dropdown import DropdownPanel
from .ui.add_dialog import AddEditDialog
from .ui.manager_dialog import ManagerDialog


def seed_test_data_if_needed(cfg: ConfigManager) -> None:
    """Add the requested test data on first run (calc, calendar, web browser)."""
    if cfg.config.launchers:
        return

    if sys.platform == "darwin":
        seeds: list[Launcher] = [
            Launcher.new(name="Calculator", command="Calculator", enabled=True),  # macOS Calculator.app name
            Launcher.new(name="Calendar", command="Calendar", enabled=True),
            Launcher.new(name="Web Browser", command="https://www.google.com", enabled=True),
            Launcher.new(name="TextEdit", command="TextEdit", enabled=True),
            Launcher.new(name="Finder", command="Finder", args="~", enabled=True),
            Launcher.new(name="Terminal", command="Terminal", enabled=True),
        ]
    else:
        seeds: list[Launcher] = [
            Launcher.new(
                name="Calculator",
                command="calc",
                enabled=True,
            ),
            Launcher.new(
                name="Calendar",
                command="ms-calendar:",   # Windows Calendar app via protocol (falls back to browser on other OS)
                enabled=True,
            ),
            Launcher.new(
                name="Web Browser",
                command="https://www.google.com",
                enabled=True,
            ),
            # Practical Windows-friendly examples
            Launcher.new(name="Notepad", command="notepad", enabled=True),
            Launcher.new(name="File Explorer", command="explorer", args=".", enabled=True),
            Launcher.new(name="Command Prompt", command="cmd", enabled=True),
        ]

    for s in seeds:
        cfg.add_launcher(s)


def create_tray(app: QApplication, trigger: TriggerWidget, dropdown: DropdownPanel,
                cfg: ConfigManager) -> QSystemTrayIcon:
    """Create and return a system tray icon with useful menu."""
    tray = QSystemTrayIcon()
    icon = QIcon.fromTheme("applications-system")
    if icon.isNull():
        # Fallback: use the trigger widget as a pixmap source (the arrow looks decent)
        icon = QIcon(trigger.grab())
    tray.setIcon(icon)

    menu = QMenu()

    act_add = QAction("Add new launcher...", menu)
    act_add.triggered.connect(trigger.request_add.emit)

    act_manage = QAction("Manage launchers...", menu)
    act_manage.triggered.connect(trigger.request_manage.emit)

    act_reload = QAction("Reload config", menu)
    def do_reload():
        cfg.reload()
        dropdown.rebuild_buttons(cfg.get_enabled_launchers())
        trigger.update_size_from_settings()
        if cfg.config.settings.pinned_open:
            dropdown.position_below(trigger)
            dropdown.ensure_visible_and_sized()
        # reposition if needed
    act_reload.triggered.connect(do_reload)

    act_exit = QAction("Exit Script Runner", menu)
    act_exit.triggered.connect(app.quit)

    menu.addAction(act_add)
    menu.addAction(act_manage)
    menu.addAction(act_reload)
    menu.addSeparator()
    menu.addAction(act_exit)

    tray.setContextMenu(menu)
    tray.setToolTip("Script Runner")
    tray.show()

    # Also allow left-click on tray to toggle the list (nice extra)
    def on_tray_activated(reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            # Force show the dropdown near trigger
            dropdown.position_below(trigger)
            dropdown.rebuild_buttons(cfg.get_enabled_launchers())
            if cfg.config.settings.pinned_open:
                dropdown.ensure_visible_and_sized()
            else:
                dropdown.start_show_animation()
            # Ensure arrow stays on top of its list.
            trigger.raise_()
            dropdown.stackUnder(trigger)

    tray.activated.connect(on_tray_activated)

    return tray


def main() -> int:
    app = QApplication(sys.argv)

    # Set activation policy as early as possible on macOS.
    # Use integer 1 (Accessory) to avoid enum lookup issues on older system PySide6.
    if sys.platform == "darwin":
        try:
            app.setActivationPolicy(1)  # 1 == ActivationPolicyAccessory
        except Exception:
            pass

    app.setApplicationName("Script Runner")
    app.setQuitOnLastWindowClosed(False)  # tray + floating widget

    # NOTE: We intentionally do NOT create a hidden QMainWindow here.
    # On macOS, a hidden main window + frameless Tool window + dialogs + activation policy
    # can easily trigger AppKit assertions (EXC_BREAKPOINT / SIGTRAP).
    # The setQuitOnLastWindowClosed(False) + early activation policy is usually sufficient.

    # Support for automated testing: script-runner --test-quit-after 1500
    test_quit_ms = 0
    if "--test-quit-after" in sys.argv:
        try:
            idx = sys.argv.index("--test-quit-after")
            test_quit_ms = int(sys.argv[idx + 1])
        except Exception:
            test_quit_ms = 1500
        if test_quit_ms > 0:
            QTimer.singleShot(test_quit_ms, app.quit)

    cfg_mgr = ConfigManager()
    seed_test_data_if_needed(cfg_mgr)

    # Create core widgets
    trigger = TriggerWidget(cfg_mgr.config)
    dropdown = DropdownPanel(cfg_mgr.config)

    # Initial button population
    dropdown.rebuild_buttons(cfg_mgr.get_enabled_launchers())

    # Hover coordination
    # We need to keep the dropdown visible while mouse is in *either* trigger or dropdown.
    # The widgets themselves emit hover_enter / hover_leave.
    # We use a small shared timer + state.

    hide_timer = QTimer()
    hide_timer.setSingleShot(True)
    hide_timer.setInterval(cfg_mgr.config.settings.hover_delay_ms)

    def schedule_hide():
        hide_timer.start()

    def cancel_hide():
        hide_timer.stop()
        dropdown.cancel_hide()  # also cancel dropdown's internal timer to keep list open when mouse is over trigger

    def do_hide():
        if not cfg_mgr.config.settings.pinned_open:
            dropdown.start_hide_animation()

    hide_timer.timeout.connect(do_hide)

    def on_trigger_enter():
        cancel_hide()  # cancels both main timer and dropdown's internal timer
        dropdown.position_below(trigger)
        dropdown.rebuild_buttons(cfg_mgr.get_enabled_launchers())
        if not dropdown.isVisible():
            dropdown.start_show_animation()
        # Keep the arrow handle above the dropdown list in the window stack.
        # The dropdown does raise_() when it shows; we re-raise the trigger so
        # its bottom (the pill/arrow) is not covered by the list's top border/frame.
        trigger.raise_()
        dropdown.stackUnder(trigger)

    def on_trigger_leave():
        if not cfg_mgr.config.settings.pinned_open:
            schedule_hide()

    def on_dropdown_enter():
        cancel_hide()

    def on_dropdown_leave():
        if not cfg_mgr.config.settings.pinned_open:
            schedule_hide()

    trigger.hover_enter.connect(on_trigger_enter)
    trigger.hover_leave.connect(on_trigger_leave)
    dropdown.hover_enter.connect(on_dropdown_enter)
    dropdown.hover_leave.connect(on_dropdown_leave)

    # Launch handling
    def on_launch(launcher: Launcher):
        try:
            launch(launcher)
            # Optional: could flash the button or show tray message
            if tray.isVisible():
                tray.showMessage(
                    "Launched", launcher.name, QSystemTrayIcon.MessageIcon.Information, 1200
                )
        except Exception as exc:
            QMessageBox.warning(
                None,
                "Launch failed",
                f"Could not launch '{launcher.name}':\n{exc}",
            )
        finally:
            if not cfg_mgr.config.settings.pinned_open:
                # short delay for click visual feedback, then hide (unless pinned)
                QTimer.singleShot(80, dropdown.start_hide_animation)
            else:
                # ensure it stays fully expanded/sized even after click (in case events caused partial state)
                QTimer.singleShot(50, dropdown.ensure_visible_and_sized)
                QTimer.singleShot(55, trigger.raise_)  # re-assert arrow on top after list re-ensure
                QTimer.singleShot(56, lambda: dropdown.stackUnder(trigger))

    dropdown.launch_requested.connect(on_launch)

    # Add dialog wiring
    def show_add_dialog(existing: Launcher | None = None):
        dlg = AddEditDialog(existing, trigger)
        if dlg.exec():
            new_or_updated = dlg.result_launcher
            if new_or_updated:
                if existing:
                    cfg_mgr.update_launcher(new_or_updated)
                else:
                    cfg_mgr.add_launcher(new_or_updated)
                dropdown.rebuild_buttons(cfg_mgr.get_enabled_launchers())

    def apply_pinned_state():
        pinned = cfg_mgr.config.settings.pinned_open
        if pinned:
            dropdown.position_below(trigger)
            dropdown.cancel_hide()
            dropdown.update_height_for_content()
            if not dropdown.isVisible():
                dropdown.start_show_animation()
            else:
                # already visible (e.g. re-apply after manager toggle), just make sure height is full
                dropdown.update_height_for_content()
            # Keep the arrow handle above the dropdown list (see on_trigger_enter for rationale).
            trigger.raise_()
            dropdown.stackUnder(trigger)  # explicit: force list window below the arrow handle
        else:
            dropdown.force_hide()

    def show_manager_dialog():
        def on_pinned_changed(checked):
            apply_pinned_state()
        dlg = ManagerDialog(cfg_mgr, trigger, pinned_changed_callback=on_pinned_changed)
        dlg.exec()
        # always rebuild after manager (launchers may have changed) and apply pin state
        dropdown.rebuild_buttons(cfg_mgr.get_enabled_launchers())
        apply_pinned_state()

    trigger.request_add.connect(lambda: show_add_dialog())
    trigger.request_manage.connect(lambda: show_manager_dialog())

    # Persist position when user drags the trigger
    def save_position(x: int, y: int):
        cfg_mgr.update_settings(position_x=x, position_y=y)
        if cfg_mgr.config.settings.pinned_open:
            dropdown.position_below(trigger)
            dropdown.ensure_visible_and_sized()
            trigger.raise_()
            dropdown.stackUnder(trigger)

    trigger.position_changed.connect(save_position)

    def save_size(w: int, h: int):
        cfg_mgr.update_settings(trigger_width=w, trigger_height=h)
        if cfg_mgr.config.settings.pinned_open:
            dropdown.position_below(trigger)
            dropdown.ensure_visible_and_sized()
            trigger.raise_()
            dropdown.stackUnder(trigger)

    trigger.size_changed.connect(save_size)

    # Exit request from trigger context menu
    trigger.request_exit.connect(app.quit)

    # System tray
    tray = create_tray(app, trigger, dropdown, cfg_mgr)

    # Show the trigger (it starts at saved or default position)
    trigger.show()
    trigger.raise_()

    # Defer the initial apply_pinned_state (and thus any position_below + show/anim of dropdown)
    # until after the event loop has processed the trigger.show(). This ensures that
    # trigger.width()/height() and mapToGlobal() reflect any persisted custom trigger size
    # (from previous resizes) rather than a default size that may be reported immediately
    # after construction/show on some platforms / with frameless widgets.
    # Prevents the dropdown from being placed too high, causing the arrow to appear
    # visually "under" the dropdown list on startup (especially with pinned_open=True
    # after the trigger was previously resized larger/smaller than the default).
    QTimer.singleShot(0, apply_pinned_state)

    # On Windows we may want to hide from taskbar / Alt+Tab more aggressively.
    # Qt.Tool + frameless already helps a lot.

    # Run
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
