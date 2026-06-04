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
    QInputDialog,
    QMainWindow,
)

try:
    from pynput import keyboard
except ImportError:
    keyboard = None

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
                cfg: ConfigManager, set_hotkey_callback=None) -> QSystemTrayIcon:
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

    act_set_hotkey = QAction("Set hotkey...", menu)
    if set_hotkey_callback:
        act_set_hotkey.triggered.connect(set_hotkey_callback)

    act_reload = QAction("Reload config", menu)
    def do_reload():
        cfg.reload()
        dropdown.rebuild_buttons(cfg.get_enabled_launchers())
        trigger.update_size_from_settings()
        # reposition if needed
    act_reload.triggered.connect(do_reload)

    act_exit = QAction("Exit Script Runner", menu)
    act_exit.triggered.connect(app.quit)

    menu.addAction(act_add)
    menu.addAction(act_manage)
    menu.addAction(act_set_hotkey)
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
            dropdown.start_show_animation()

    tray.activated.connect(on_tray_activated)

    return tray


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Script Runner")
    app.setQuitOnLastWindowClosed(False)  # tray + floating widget

    if sys.platform == "darwin":
        # Make the app an "accessory" app on macOS: no dock icon, no app switcher entry.
        # Our floating trigger and tray will still be visible.
        app.setActivationPolicy(Qt.ApplicationAttribute.AA_ActivationPolicyAccessory)

    # On macOS (and to be safe cross-platform), keep a hidden QMainWindow alive.
    # This prevents the app from auto-quitting when using only frameless/Tool windows
    # and temporary dialogs (a common macOS + Qt gotcha).
    _hidden_main = QMainWindow()
    _hidden_main.setWindowTitle("Script Runner")
    _hidden_main.hide()
    app._hidden_main_window = _hidden_main  # keep reference

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
    # Auto-correct default hotkey for platform on first run / if still old default
    if sys.platform == "darwin" and cfg_mgr.config.settings.hotkey == "<ctrl>+<alt>+l":
        cfg_mgr.update_settings(hotkey="<cmd>+<alt>+l")
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

    def do_hide():
        dropdown.start_hide_animation()

    hide_timer.timeout.connect(do_hide)

    def on_trigger_enter():
        cancel_hide()
        dropdown.position_below(trigger)
        dropdown.rebuild_buttons(cfg_mgr.get_enabled_launchers())
        if not dropdown.isVisible():
            dropdown.start_show_animation()

    def on_trigger_leave():
        schedule_hide()

    def on_dropdown_enter():
        cancel_hide()

    def on_dropdown_leave():
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
            dropdown.force_hide()

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

    def show_manager_dialog():
        dropdown.force_hide()
        dlg = ManagerDialog(cfg_mgr, trigger)
        if dlg.exec():
            # Manager saves its own changes; just refresh the dropdown list
            dropdown.rebuild_buttons(cfg_mgr.get_enabled_launchers())

    trigger.request_add.connect(lambda: show_add_dialog())
    trigger.request_manage.connect(lambda: show_manager_dialog())

    # Global hotkey support (configurable)
    def _setup_hotkey(hotkey_str: str):
        if keyboard is None:
            return None
        def _force_show_dropdown():
            dropdown.position_below(trigger)
            dropdown.rebuild_buttons(cfg_mgr.get_enabled_launchers())
            dropdown.start_show_animation()
        try:
            listener = keyboard.GlobalHotKeys({hotkey_str: _force_show_dropdown})
            listener.start()
            print(f"Hotkey registered: {hotkey_str} to show launcher list")
            if sys.platform == "darwin":
                print("  On macOS you may need to grant Accessibility permissions to Terminal/Python")
                print("  in System Settings > Privacy & Security > Accessibility")
            return listener
        except Exception as exc:
            print(f"Warning: failed to register hotkey {hotkey_str}: {exc}")
            return None

    current_hotkey = cfg_mgr.config.settings.hotkey
    app._hotkey_listener = _setup_hotkey(current_hotkey)

    def change_hotkey():
        if keyboard is None:
            QMessageBox.information(trigger, "Hotkey", "pynput is not installed; hotkeys are disabled.\nInstall with: pip install pynput")
            return
        text, ok = QInputDialog.getText(
            None,  # use None as parent to avoid issues with the frameless Tool trigger window on macOS
            "Set Hotkey",
            "Enter hotkey in pynput format.\n"
            "Examples:\n"
            "  Windows/Linux: <ctrl>+<alt>+k\n"
            "  macOS:         <cmd>+<alt>+k\n\n"
            "Common modifiers: <ctrl>, <alt>, <shift>, <cmd> (mac)\n"
            "See pynput documentation for full syntax.",
            text=cfg_mgr.config.settings.hotkey
        )
        if ok and text:
            new_hotkey = text.strip()
            if new_hotkey:
                cfg_mgr.update_settings(hotkey=new_hotkey)
                # stop previous listener
                if hasattr(app, '_hotkey_listener') and app._hotkey_listener:
                    try:
                        app._hotkey_listener.stop()
                    except Exception:
                        pass
                app._hotkey_listener = _setup_hotkey(new_hotkey)

    trigger.request_set_hotkey.connect(change_hotkey)

    # Persist position when user drags the trigger
    def save_position(x: int, y: int):
        cfg_mgr.update_settings(position_x=x, position_y=y)

    trigger.position_changed.connect(save_position)

    # Exit request from trigger context menu
    trigger.request_exit.connect(app.quit)

    # System tray
    tray = create_tray(app, trigger, dropdown, cfg_mgr, set_hotkey_callback=change_hotkey)

    # Show the trigger (it starts at saved or default position)
    trigger.show()

    # On Windows we may want to hide from taskbar / Alt+Tab more aggressively.
    # Qt.Tool + frameless already helps a lot.

    # Run
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
