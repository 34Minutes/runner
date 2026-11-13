"""Main entry point for Runner.

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
from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer, QPoint, QSize, QRect
from PySide6.QtGui import QCursor, QIcon, QAction, QPainter, QPen, QColor, QPixmap
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QApplication,
    QSystemTrayIcon,
    QMenu,
    QMessageBox,
)

from .config import (
    DEFAULT_TRIGGER_HEIGHT,
    DEFAULT_TRIGGER_WIDTH,
    AppConfig,
    ConfigManager,
    ContainerGroup,
    Group,
    Launcher,
)
from .containers import submenu_launchers
from .groups import GROUP_STEP_GAP_MS, execution_steps, run_group_steps
from .ui.greeting import StartupGreeting, clamp_trigger_to_screen, ensure_visible_trigger_size
from .launcher import launch
from .ui.trigger import TriggerWidget
from .ui.dropdown import DropdownPanel
from .ui.add_dialog import AddEditDialog
from .ui.container_dialog import ContainerDialog
from .ui.container_manager import ContainerManagerDialog
from .ui.group_dialog import GroupDialog
from .ui.group_manager import GroupManagerDialog
from .ui.manager_dialog import ManagerDialog
from .ui.stay_on_top import question as stay_on_top_question
from .ui.stay_on_top import warning as stay_on_top_warning

if sys.platform == "win32":
    from .utils import windows as win_utils  # type: ignore
else:
    win_utils = None  # type: ignore


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


def _fill_main_dropdown(dropdown: DropdownPanel, cfg: ConfigManager) -> None:
    """Launcher rows, with container groups above them."""
    dropdown.set_submenu_items(
        [(group.id, group.name) for group in cfg.config.container_groups]
    )
    dropdown.rebuild_buttons(cfg.get_main_view_launchers())


def create_tray(
    app: QApplication,
    trigger: TriggerWidget,
    dropdown: DropdownPanel,
    cfg: ConfigManager,
    *,
    before_show: Callable[[], None] | None = None,
    on_reloaded: Callable[[], None] | None = None,
) -> QSystemTrayIcon:
    """Create and return a system tray icon with useful menu."""
    tray = QSystemTrayIcon()

    # Draw a crisp small downward arrow for the menu bar / tray.
    # This looks consistent and professional without needing external icon files.
    icon_size = 18
    pix = QPixmap(icon_size, icon_size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor("#0a84ff"), 2.0)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    m = 3
    cx = icon_size // 2
    p.drawLine(m, m + 1, cx, icon_size - m)
    p.drawLine(cx, icon_size - m, icon_size - m, m + 1)
    p.end()
    tray.setIcon(QIcon(pix))

    menu = QMenu()

    act_add = QAction("Add new launcher...", menu)
    act_add.triggered.connect(trigger.request_add.emit)

    act_manage = QAction("Manage launchers...", menu)
    act_manage.triggered.connect(trigger.request_manage.emit)

    act_reset = QAction("Reset position & size", menu)
    act_reset.triggered.connect(trigger.request_reset.emit)

    act_reload = QAction("Reload config", menu)
    def do_reload():
        cfg.reload()
        _fill_main_dropdown(dropdown, cfg)
        trigger.update_size_from_settings()
        if on_reloaded is not None:
            on_reloaded()
        elif cfg.config.settings.pinned_open:
            dropdown.position_adjacent(trigger)
            dropdown.ensure_visible_and_sized()
        # reposition if needed
    act_reload.triggered.connect(do_reload)

    act_exit = QAction("Exit Runner", menu)
    act_exit.triggered.connect(app.quit)

    menu.addAction(act_add)
    menu.addAction(act_manage)
    menu.addAction(act_reset)
    menu.addAction(act_reload)
    menu.addSeparator()
    menu.addAction(act_exit)

    tray.setContextMenu(menu)
    tray.setToolTip("Runner")
    tray.show()

    # Also allow left-click on tray to toggle the list (nice extra)
    def on_tray_activated(reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            # Force show the dropdown near trigger
            if before_show is not None:
                before_show()
            dropdown.position_adjacent(trigger)
            _fill_main_dropdown(dropdown, cfg)
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

    # --- Single instance enforcement ---
    # Windows: try a named mutex first (very reliable even across elevation differences).
    if sys.platform == "win32" and win_utils is not None:
        if not win_utils.acquire_single_instance_mutex():
            # Another instance is running — try to wake it via the socket and exit.
            server_name = "Runner_SingleInstance_v1"
            socket = QLocalSocket()
            socket.connectToServer(server_name)
            if socket.waitForConnected(300):
                socket.write(b"show")
                socket.waitForBytesWritten(300)
            socket.close()
            return 0

    # If another copy is running (non-Windows or mutex passed), tell it to show/raise the trigger and exit.
    server_name = "Runner_SingleInstance_v1"
    socket = QLocalSocket()
    socket.connectToServer(server_name)
    if socket.waitForConnected(300):
        socket.write(b"show")
        socket.waitForBytesWritten(300)
        socket.close()
        return 0

    # No other instance running — become the server.
    local_server = QLocalServer()
    # Remove any stale socket file (common on macOS after crashes)
    QLocalServer.removeServer(server_name)
    if not local_server.listen(server_name):
        # Fallback: just continue (rare)
        pass

    _trigger_ref = [None]  # mutable holder so handler can see it later

    def _handle_new_connection():
        while local_server.hasPendingConnections():
            client = local_server.nextPendingConnection()
            client.waitForReadyRead(300)
            _ = client.readAll()
            # Any message means "show me"
            trig = _trigger_ref[0]
            if trig is not None:
                trig.show()
                trig.raise_()
                trig.activateWindow()
            client.close()

    local_server.newConnection.connect(_handle_new_connection)

    # Keep server alive
    app._local_server = local_server
    app._trigger_ref = _trigger_ref
    # --- end single instance ---

    # Keep a reference so the handler can always find it (in case of timing)
    # The mutable list above already handles this.

    # Set activation policy as early as possible on macOS.
    # Use integer 1 (Accessory) to avoid enum lookup issues on older system PySide6.
    if sys.platform == "darwin":
        try:
            app.setActivationPolicy(1)  # 1 == ActivationPolicyAccessory
        except Exception:
            pass

    app.setApplicationName("Runner")
    app.setQuitOnLastWindowClosed(False)  # tray + floating widget

    # NOTE: We intentionally do NOT create a hidden QMainWindow here.
    # On macOS, a hidden main window + frameless Tool window + dialogs + activation policy
    # can easily trigger AppKit assertions (EXC_BREAKPOINT / SIGTRAP).
    # The setQuitOnLastWindowClosed(False) + early activation policy is usually sufficient.

    # Support for automated testing: runner --test-quit-after 1500
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
    app._trigger_ref[0] = trigger  # for single-instance handler
    dropdown = DropdownPanel(cfg_mgr.config)
    group_panel = DropdownPanel(cfg_mgr.config, honor_pin=False)
    group_panel.set_list_copy(
        placeholder="Filter execute groups...",
        empty_hint="",
    )
    group_panel.set_order_ids(lambda: [group.id for group in cfg_mgr.config.groups])
    group_panel.set_row_tooltip(
        lambda row: (
            f"Run execute group: {row.name}\n"
            "Drag up or down to reorder\n"
            "Right-click to edit or delete"
        )
    )
    group_panel.set_heading("Execute Groups")

    container_panel = DropdownPanel(
        cfg_mgr.config,
        honor_pin=False,
        allow_reorder=False,
    )
    container_panel.set_list_copy(
        placeholder="Filter launchers...",
        empty_hint="Nothing in this container.",
    )

    # Initial button population. Launchers hidden by a group stay off this list.
    _fill_main_dropdown(dropdown, cfg_mgr)

    # Validate that saved position is still on screen (e.g. after monitor changes)
    # If not, reset to a safe default.
    def _validate_trigger_position():
        pos = trigger.pos()
        sz = trigger.size()
        on_screen = False
        for screen in QApplication.screens():
            if screen.availableGeometry().intersects(QRect(pos, sz)):
                on_screen = True
                break
        if not on_screen:
            default_w, default_h = DEFAULT_TRIGGER_WIDTH, DEFAULT_TRIGGER_HEIGHT
            default_x, default_y = 100, 100
            trigger.resize(default_w, default_h)
            trigger.move(default_x, default_y)
            cfg_mgr.update_settings(
                trigger_width=default_w,
                trigger_height=default_h,
                position_x=default_x,
                position_y=default_y,
            )

    # First launch on this machine uses the large default arrow. Later launches
    # keep the size and position already stored in the config file.
    if not cfg_mgr.had_saved_config:
        ensure_visible_trigger_size(cfg_mgr, trigger)
    _validate_trigger_position()
    if clamp_trigger_to_screen(trigger):
        cfg_mgr.update_settings(position_x=trigger.x(), position_y=trigger.y())
    dropdown.refresh_filter_visibility()

    greeting = StartupGreeting()
    app._startup_greeting = greeting

    # Hover coordination
    # We need to keep the dropdown visible while mouse is in *either* trigger or dropdown.
    # The widgets themselves emit hover_enter / hover_leave.
    # We use a small shared timer + state.

    hide_timer = QTimer()
    hide_timer.setSingleShot(True)
    hide_timer.setInterval(cfg_mgr.config.settings.hover_delay_ms)
    showing_groups = False
    open_container_id: str | None = None
    container_hide_timer = QTimer()
    container_hide_timer.setSingleShot(True)
    container_hide_timer.setInterval(180)

    def schedule_hide():
        hide_timer.start()

    def cancel_hide():
        hide_timer.stop()
        dropdown.cancel_hide()  # also cancel dropdown's internal timer to keep list open when mouse is over trigger
        group_panel.cancel_hide()
        container_panel.cancel_hide()

    def _show_groups_enabled() -> bool:
        return bool(getattr(cfg_mgr.config.settings, "show_groups", False))

    def _hide_container_menu() -> None:
        nonlocal open_container_id
        container_hide_timer.stop()
        open_container_id = None
        container_panel.use_position_hook(None)
        if container_panel.isVisible():
            container_panel.force_hide()

    def do_hide():
        _hide_container_menu()
        if showing_groups:
            group_panel.start_hide_animation()
            return
        if group_panel.isVisible():
            group_panel.start_hide_animation()
        if not cfg_mgr.config.settings.pinned_open:
            dropdown.start_hide_animation()

    hide_timer.timeout.connect(do_hide)

    def _refresh_group_list() -> None:
        rows = [
            Launcher(id=group.id, name=group.name, command="")
            for group in cfg_mgr.config.groups
        ]
        group_panel.rebuild_buttons(rows)
        if group_panel.isVisible():
            group_panel.update_height_for_content()

    def _place_groups_beside() -> None:
        group_panel.position_beside(dropdown, trigger)

    def _show_groups_beside() -> None:
        """Launcher list stays. Groups sit beside it, toward the middle of the screen.

        An empty group list stays hidden, including the old empty-state message.
        """
        if showing_groups or not _show_groups_enabled():
            return
        if not cfg_mgr.config.groups:
            _hide_groups_beside()
            return
        _refresh_group_list()
        group_panel.use_position_hook(_place_groups_beside)
        if group_panel.isVisible():
            group_panel.ensure_visible_and_sized()
        else:
            group_panel.start_show_animation()
        trigger.raise_()
        dropdown.stackUnder(trigger)
        group_panel.stackUnder(trigger)

    def _hide_groups_beside() -> None:
        if showing_groups:
            return
        group_panel.use_position_hook(None)
        if group_panel.isVisible():
            group_panel.force_hide()

    def _show_group_panel() -> None:
        nonlocal showing_groups
        _hide_container_menu()
        if not cfg_mgr.config.groups:
            showing_groups = False
            _hide_groups_beside()
            return
        showing_groups = True
        cancel_hide()
        group_panel.use_position_hook(None)
        if dropdown.isVisible():
            dropdown.force_hide()
        _refresh_group_list()
        group_panel.position_adjacent(trigger)
        if group_panel.isVisible():
            group_panel.ensure_visible_and_sized()
        else:
            group_panel.start_show_animation()
        trigger.raise_()
        group_panel.stackUnder(trigger)

    def on_group_panel_closed() -> None:
        nonlocal showing_groups
        # A hide that was already running can finish after the list is shown again.
        if group_panel.isVisible():
            return
        showing_groups = False
        if cfg_mgr.config.settings.pinned_open:
            apply_pinned_state()

    def on_trigger_enter():
        cancel_hide()  # cancels both main timer and dropdown's internal timer
        _hide_container_menu()
        if showing_groups:
            group_panel.position_adjacent(trigger)
            if group_panel.is_closing() or not group_panel.isVisible():
                _show_group_panel()
            trigger.raise_()
            group_panel.stackUnder(trigger)
            return
        dropdown.position_adjacent(trigger)
        _fill_main_dropdown(dropdown, cfg_mgr)
        if not dropdown.isVisible():
            dropdown.start_show_animation()
        trigger.raise_()
        dropdown.stackUnder(trigger)
        if _show_groups_enabled():
            _show_groups_beside()
        else:
            _hide_groups_beside()

    def _pointer_over(widget) -> bool:
        return widget.isVisible() and widget.frameGeometry().contains(QCursor.pos())

    def on_trigger_leave():
        # Moving from the arrow menu onto a list must not start a hide.
        # The list's own leave collapses it.
        if _pointer_over(dropdown) or _pointer_over(group_panel) or _pointer_over(container_panel):
            return
        if showing_groups or not cfg_mgr.config.settings.pinned_open:
            schedule_hide()

    def on_dropdown_enter():
        cancel_hide()

    def on_dropdown_leave():
        if _pointer_over(container_panel):
            return
        _schedule_container_hide()
        if not cfg_mgr.config.settings.pinned_open:
            schedule_hide()

    def on_group_enter():
        cancel_hide()
        if showing_groups and group_panel.is_closing():
            group_panel.start_show_animation()
        elif not showing_groups and _show_groups_enabled() and group_panel.is_closing():
            _show_groups_beside()

    def on_group_leave():
        if showing_groups or (_show_groups_enabled() and not cfg_mgr.config.settings.pinned_open):
            schedule_hide()

    def _container_by_id(group_id: str) -> ContainerGroup | None:
        for group in cfg_mgr.config.container_groups:
            if group.id == group_id:
                return group
        return None

    def _container_prefer_right() -> bool:
        """Open on the side opposite the execute-groups list when that list is up."""
        if group_panel.isVisible() and group_panel.x() >= dropdown.x():
            return False
        return True

    def _place_container() -> None:
        if not open_container_id:
            return
        button = dropdown.submenu_button(open_container_id)
        if button is None or not button.isVisible():
            return
        container_panel.position_next_to(
            dropdown,
            button,
            prefer_right=_container_prefer_right(),
        )

    def _show_container_menu(group_id: str) -> None:
        nonlocal open_container_id
        group = _container_by_id(group_id)
        if group is None or not dropdown.isVisible():
            _hide_container_menu()
            return
        button = dropdown.submenu_button(group_id)
        if button is None or not button.isVisible():
            _hide_container_menu()
            return
        container_hide_timer.stop()
        open_container_id = group_id
        container_panel.set_heading(group.name)
        container_panel.rebuild_buttons(submenu_launchers(group, cfg_mgr.config.launchers))
        container_panel.use_position_hook(_place_container)
        container_panel.cancel_hide()
        if container_panel.isVisible() and not container_panel.is_closing():
            container_panel.ensure_visible_and_sized()
        else:
            container_panel.start_show_animation()
        trigger.raise_()
        dropdown.stackUnder(trigger)
        container_panel.stackUnder(trigger)

    def _on_submenu_left(group_id: str) -> None:
        if group_id == open_container_id:
            _schedule_container_hide()

    def _schedule_container_hide() -> None:
        if open_container_id:
            container_hide_timer.start()

    def _hide_container_if_left() -> None:
        if _pointer_over(container_panel):
            return
        if open_container_id:
            button = dropdown.submenu_button(open_container_id)
            if (
                button is not None
                and button.isVisible()
                and button.rect().contains(button.mapFromGlobal(QCursor.pos()))
            ):
                return
        _hide_container_menu()

    def on_container_enter():
        cancel_hide()
        container_hide_timer.stop()

    def on_container_leave():
        _schedule_container_hide()
        if _pointer_over(dropdown) or _pointer_over(trigger):
            return
        if showing_groups or not cfg_mgr.config.settings.pinned_open:
            schedule_hide()

    container_hide_timer.timeout.connect(_hide_container_if_left)

    def reset_position_and_size():
        """Reset the trigger to a sensible default location and size."""
        default_w, default_h = DEFAULT_TRIGGER_WIDTH, DEFAULT_TRIGGER_HEIGHT
        default_x, default_y = 100, 100
        cfg_mgr.update_settings(
            trigger_width=default_w,
            trigger_height=default_h,
            position_x=default_x,
            position_y=default_y,
        )
        trigger.resize(default_w, default_h)
        trigger.move(default_x, default_y)
        trigger.raise_()
        _follow_trigger()

    trigger.hover_enter.connect(on_trigger_enter)
    trigger.hover_leave.connect(on_trigger_leave)
    dropdown.hover_enter.connect(on_dropdown_enter)
    dropdown.hover_leave.connect(on_dropdown_leave)
    group_panel.hover_enter.connect(on_group_enter)
    group_panel.hover_leave.connect(on_group_leave)
    group_panel.closed.connect(on_group_panel_closed)
    container_panel.hover_enter.connect(on_container_enter)
    container_panel.hover_leave.connect(on_container_leave)
    dropdown.submenu_hovered.connect(_show_container_menu)
    dropdown.submenu_left.connect(_on_submenu_left)

    trigger.request_reset.connect(reset_position_and_size)

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
            stay_on_top_warning(
                trigger,
                "Launch failed",
                f"Could not launch '{launcher.name}':\n{exc}",
            )
        finally:
            _hide_container_menu()
            if not cfg_mgr.config.settings.pinned_open:
                # short delay for click visual feedback, then hide (unless pinned)
                QTimer.singleShot(80, dropdown.start_hide_animation)
            else:
                # ensure it stays fully expanded/sized even after click (in case events caused partial state)
                QTimer.singleShot(50, dropdown.ensure_visible_and_sized)
                QTimer.singleShot(55, trigger.raise_)  # re-assert arrow on top after list re-ensure
                QTimer.singleShot(56, lambda: dropdown.stackUnder(trigger))

    dropdown.launch_requested.connect(on_launch)

    def on_reordered(ordered_ids: list[str]) -> None:
        cfg_mgr.reorder_launchers(ordered_ids)

    dropdown.reordered.connect(on_reordered)

    def _refresh_open_container() -> None:
        if open_container_id and container_panel.isVisible():
            _show_container_menu(open_container_id)

    def _refresh_open_list() -> None:
        _fill_main_dropdown(dropdown, cfg_mgr)
        _refresh_open_container()
        if cfg_mgr.config.settings.pinned_open:
            apply_pinned_state()

    def _group_by_id(group_id: str) -> Group | None:
        for group in cfg_mgr.config.groups:
            if group.id == group_id:
                return group
        return None

    def on_edit_requested(launcher: Launcher) -> None:
        show_add_dialog(launcher)
        if cfg_mgr.config.settings.pinned_open:
            apply_pinned_state()

    def on_delete_requested(launcher: Launcher) -> None:
        reply = stay_on_top_question(
            trigger,
            "Delete Launcher",
            f"Delete '{launcher.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        cfg_mgr.remove_launcher(launcher.id)
        _refresh_open_list()

    dropdown.edit_requested.connect(on_edit_requested)
    dropdown.delete_requested.connect(on_delete_requested)

    # Add dialog wiring
    def _on_greeting_toggled(checked: bool) -> None:
        cfg_mgr.update_settings(show_startup_greeting=checked)
        if checked:
            greeting.show_again(trigger)
        else:
            greeting.dismiss_for_session()
        _follow_trigger()

    def show_add_dialog(existing: Launcher | None = None):
        dlg = AddEditDialog(existing, trigger, cfg=cfg_mgr)
        if dlg.exec():
            new_or_updated = dlg.result_launcher
            if new_or_updated:
                if existing:
                    cfg_mgr.update_launcher(new_or_updated)
                else:
                    cfg_mgr.add_launcher(new_or_updated)
                _fill_main_dropdown(dropdown, cfg_mgr)
                _refresh_open_container()
                _sync_groups_after_change()

    def _follow_trigger() -> None:
        """Keep whichever list is open beside the arrow."""
        if showing_groups and group_panel.isVisible():
            group_panel.use_position_hook(None)
            group_panel.position_adjacent(trigger)
            group_panel.ensure_visible_and_sized()
            trigger.raise_()
            group_panel.stackUnder(trigger)
            return
        if not dropdown.isVisible() and not cfg_mgr.config.settings.pinned_open:
            return
        dropdown.position_adjacent(trigger)
        if cfg_mgr.config.settings.pinned_open:
            dropdown.ensure_visible_and_sized()
        trigger.raise_()
        dropdown.stackUnder(trigger)
        if _show_groups_enabled() and (group_panel.isVisible() or cfg_mgr.config.settings.pinned_open):
            _show_groups_beside()

    def apply_pinned_state():
        if showing_groups:
            return
        pinned = cfg_mgr.config.settings.pinned_open
        if pinned:
            dropdown.position_adjacent(trigger)
            dropdown.cancel_hide()
            dropdown.update_height_for_content()
            if not dropdown.isVisible():
                dropdown.start_show_animation()
            else:
                dropdown.update_height_for_content()
            trigger.raise_()
            dropdown.stackUnder(trigger)
            if _show_groups_enabled():
                _show_groups_beside()
        else:
            dropdown.force_hide()
            _hide_container_menu()
            _hide_groups_beside()

    def show_manager_dialog():
        dlg = ManagerDialog(cfg_mgr, trigger)
        dlg.exec()
        # always rebuild after manager (launchers may have changed) and apply pin state
        _fill_main_dropdown(dropdown, cfg_mgr)
        _refresh_open_container()
        _sync_groups_after_change()
        apply_pinned_state()

    def show_group_dialog(existing: Group | None = None) -> None:
        dialog = GroupDialog(cfg_mgr, existing, trigger)
        dialog.launchers_changed.connect(_refresh_open_list)
        accepted = bool(dialog.exec())
        result = dialog.result_group
        if accepted and result is not None:
            if existing is None:
                cfg_mgr.add_group(result)
            else:
                cfg_mgr.update_group(result)
        _refresh_open_list()
        _sync_groups_after_change()

    def show_group_manager() -> None:
        dialog = GroupManagerDialog(cfg_mgr, trigger)
        dialog.exec()
        _refresh_open_list()
        _sync_groups_after_change()

    def on_group_launch(row: Launcher) -> None:
        group = _group_by_id(row.id)
        if group is None:
            return
        steps = execution_steps(group, cfg_mgr.config.launchers)
        group_panel.force_hide()
        _hide_container_menu()
        if not cfg_mgr.config.settings.pinned_open:
            dropdown.start_hide_animation()
        if not steps:
            stay_on_top_warning(
                trigger,
                "Nothing to launch",
                f"'{group.name}' has no enabled launchers.",
            )
            return
        errors: list[str] = []

        def launch_one(item: Launcher) -> None:
            launch(item)

        def on_error(item: Launcher, exc: Exception) -> None:
            errors.append(f"{item.name}: {exc}")

        def on_finished() -> None:
            if errors:
                stay_on_top_warning(trigger, "Launch failed", "\n".join(errors))

        if tray.isVisible():
            tray.showMessage(
                "Started",
                group.name,
                QSystemTrayIcon.MessageIcon.Information,
                1200,
            )
        run_group_steps(
            steps,
            launch_one,
            lambda delay, callback: QTimer.singleShot(delay, trigger, callback),
            gap_ms=GROUP_STEP_GAP_MS,
            on_error=on_error,
            on_finished=on_finished,
        )

    def on_group_edit(row: Launcher) -> None:
        group = _group_by_id(row.id)
        if group is not None:
            show_group_dialog(group)

    def on_group_delete(row: Launcher) -> None:
        group = _group_by_id(row.id)
        if group is None:
            return
        reply = stay_on_top_question(
            trigger,
            "Delete Execute Group",
            f"Delete '{group.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        cfg_mgr.remove_group(group.id)
        _sync_groups_after_change()

    def on_group_reordered(ordered_ids: list[str]) -> None:
        cfg_mgr.reorder_groups(ordered_ids)

    group_panel.launch_requested.connect(on_group_launch)
    group_panel.edit_requested.connect(on_group_edit)
    group_panel.delete_requested.connect(on_group_delete)
    group_panel.reordered.connect(on_group_reordered)

    trigger.request_add.connect(lambda: show_add_dialog())
    trigger.request_manage.connect(lambda: show_manager_dialog())
    def show_container_dialog(existing: ContainerGroup | None = None) -> None:
        dialog = ContainerDialog(cfg_mgr, existing, trigger)
        dialog.launchers_changed.connect(_refresh_open_list)
        accepted = bool(dialog.exec())
        result = dialog.result_group
        if accepted and result is not None:
            if existing is None:
                cfg_mgr.add_container_group(result)
            else:
                cfg_mgr.update_container_group(result)
        _refresh_open_list()

    def show_container_manager() -> None:
        dialog = ContainerManagerDialog(cfg_mgr, trigger)
        dialog.exec()
        _refresh_open_list()

    def on_container_edit(group_id: str) -> None:
        group = _container_by_id(group_id)
        if group is not None:
            show_container_dialog(group)

    def on_container_delete(group_id: str) -> None:
        group = _container_by_id(group_id)
        if group is None:
            return
        reply = stay_on_top_question(
            trigger,
            "Delete Container Group",
            f"Delete '{group.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        cfg_mgr.remove_container_group(group.id)
        _hide_container_menu()
        _refresh_open_list()

    container_panel.launch_requested.connect(on_launch)
    container_panel.edit_requested.connect(on_edit_requested)
    container_panel.delete_requested.connect(on_delete_requested)
    dropdown.submenu_edit_requested.connect(on_container_edit)
    dropdown.submenu_delete_requested.connect(on_container_delete)

    trigger.request_add_group.connect(lambda: show_group_dialog())
    trigger.request_manage_groups.connect(show_group_manager)
    trigger.request_groups.connect(_show_group_panel)
    trigger.request_add_container.connect(lambda: show_container_dialog())
    trigger.request_manage_containers.connect(show_container_manager)

    # Connect the quick toggles from the arrow's right-click menu
    def on_pin_toggled(checked):
        cfg_mgr.update_settings(pinned_open=checked)
        apply_pinned_state()

    trigger.pin_toggled.connect(on_pin_toggled)

    def on_filter_toggled(checked):
        cfg_mgr.update_settings(show_filter_box=checked)
        dropdown.refresh_filter_visibility()
        group_panel.refresh_filter_visibility()
        container_panel.refresh_filter_visibility()
        if showing_groups and group_panel.isVisible():
            group_panel.update_height_for_content()
            group_panel.position_adjacent(trigger)
        elif _show_groups_enabled() and group_panel.isVisible():
            group_panel.update_height_for_content()
            _place_groups_beside()
            if dropdown.isVisible():
                dropdown.update_height_for_content()
        elif dropdown.isVisible():
            dropdown.update_height_for_content()
            if cfg_mgr.config.settings.pinned_open:
                dropdown.position_adjacent(trigger)

    trigger.filter_toggled.connect(on_filter_toggled)
    trigger.greeting_toggled.connect(_on_greeting_toggled)

    def on_show_groups_toggled(checked: bool) -> None:
        cfg_mgr.update_settings(show_groups=checked)
        if showing_groups:
            return
        if checked and (dropdown.isVisible() or cfg_mgr.config.settings.pinned_open):
            _show_groups_beside()
        elif not checked:
            _hide_groups_beside()

    trigger.groups_toggled.connect(on_show_groups_toggled)

    # Windows startup integration
    if sys.platform == "win32" and win_utils is not None:
        # On launch, if the user wants startup, (re)create the Run entry.
        # This makes it resilient if the user moved Runner.exe.
        if cfg_mgr.config.settings.launch_at_startup:
            win_utils.ensure_startup_entry(True)

        def on_startup_toggled(checked):
            cfg_mgr.update_settings(launch_at_startup=checked)
            win_utils.ensure_startup_entry(checked)

        trigger.startup_toggled.connect(on_startup_toggled)

    # Persist position when user drags the trigger
    def save_position(x: int, y: int):
        cfg_mgr.update_settings(position_x=x, position_y=y)
        _follow_trigger()

    trigger.position_changed.connect(save_position)

    def save_size(w: int, h: int):
        cfg_mgr.update_settings(
            trigger_width=w,
            trigger_height=h,
            position_x=trigger.x(),
            position_y=trigger.y(),
        )
        # The hint asked them to resize. Hide it for this launch; the switch brings it back next start.
        greeting.dismiss_for_session()
        _follow_trigger()

    trigger.size_changed.connect(save_size)

    # Exit request from trigger context menu
    trigger.request_exit.connect(app.quit)

    def _save_trigger_geometry() -> None:
        """Keep the arrow's size and position across a restart, without the greeting rim."""
        width, height = trigger.width(), trigger.height()
        if width < 20 or height < 20:
            return
        cfg_mgr.update_settings(
            trigger_width=width,
            trigger_height=height,
            position_x=trigger.x(),
            position_y=trigger.y(),
        )

    app.aboutToQuit.connect(_save_trigger_geometry)

    # System tray
    def _sync_groups_after_change() -> None:
        """Keep an open groups list in step with add, edit, and delete.

        Hover builds the list from current groups. Saving a group while that
        list is already open, or while the launcher list is pinned open, updates
        it immediately. With no groups left, the list hides.
        """
        if showing_groups:
            if not cfg_mgr.config.groups:
                group_panel.force_hide()
                return
            _refresh_group_list()
            if group_panel.isVisible():
                group_panel.position_adjacent(trigger)
                group_panel.ensure_visible_and_sized()
            return
        if _show_groups_enabled() and (
            group_panel.isVisible()
            or dropdown.isVisible()
            or cfg_mgr.config.settings.pinned_open
        ):
            _show_groups_beside()

    def _before_tray_show() -> None:
        _hide_container_menu()
        if showing_groups:
            group_panel.force_hide()

    def _after_reload() -> None:
        if showing_groups:
            _sync_groups_after_change()
            return
        if cfg_mgr.config.settings.pinned_open:
            dropdown.position_adjacent(trigger)
            dropdown.ensure_visible_and_sized()
            if _show_groups_enabled():
                _show_groups_beside()

    tray = create_tray(
        app,
        trigger,
        dropdown,
        cfg_mgr,
        before_show=_before_tray_show,
        on_reloaded=_after_reload,
    )

    # Show the trigger (it starts at saved or default position)
    trigger.show()
    trigger.raise_()

    # Defer initial positioning until after the event loop processes show().
    # Ensures trigger geometry (from persisted size) is realized before dropdown
    # calculates its position relative to it (important for custom sizes + pinned mode).
    def _after_show() -> None:
        if cfg_mgr.config.settings.show_startup_greeting:
            greeting.present(trigger)
        apply_pinned_state()

    QTimer.singleShot(0, _after_show)

    # On Windows we may want to hide from taskbar / Alt+Tab more aggressively.
    # Qt.Tool + frameless already helps a lot.

    # Run
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
