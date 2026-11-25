"""Launching, execute-group stepping, and scheduled-run handling for RunnerController."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QSystemTrayIcon

from .config import Group, Launcher
from .groups import GROUP_STEP_GAP_MS, execution_steps, run_group_steps
from .launcher import launch
from .ui.stay_on_top import warning as stay_on_top_warning

if TYPE_CHECKING:
    from .controller import RunnerController


class LaunchCoordinator:
    """Starts single launchers, execute groups, and scheduled runs."""

    def __init__(self, controller: RunnerController) -> None:
        self._ctl = controller

    def notify(self, title: str, text: str) -> None:
        if self._ctl.tray.isVisible():
            self._ctl.tray.showMessage(title, text, QSystemTrayIcon.MessageIcon.Information, 1200)

    def on_launch(self, launcher: Launcher) -> None:
        ctl = self._ctl
        try:
            launch(launcher)
            self.notify("Launched", launcher.name)
        except Exception as exc:  # any failure is shown to the user
            stay_on_top_warning(
                ctl.trigger,
                "Launch failed",
                f"Could not launch '{launcher.name}':\n{exc}",
            )
        finally:
            if not ctl.settings.pinned_open:
                ctl._collapse_open_lists()
            else:
                ctl.container_menu.hide()
                ctl.execute_menu.hide()
                if ctl._standalone_panel() is not None:
                    ctl._hide_standalone()
                # Keep the pinned list fully open after the click.
                QTimer.singleShot(50, ctl.dropdown.ensure_visible_and_sized)
                QTimer.singleShot(55, lambda: ctl._keep_arrow_on_top(ctl.dropdown))

    def on_group_launch(self, row: Launcher) -> None:
        ctl = self._ctl
        group = ctl._group_by_id(row.id)
        if group is None:
            return
        if ctl.settings.pinned_open:
            ctl.group_panel.force_hide()
            ctl.container_menu.hide()
            ctl.execute_menu.hide()
        else:
            ctl._collapse_open_lists()
        ctl._start_group(group, "Started")

    def on_schedule_click(self, row: Launcher) -> None:
        """A click in the Schedules list: open the schedule, or run it if it is set to."""
        ctl = self._ctl
        group = ctl._group_by_id(row.id)
        if group is None:
            return
        if not group.click_runs:
            ctl.show_group_dialog(group)
            return
        ctl._collapse_open_lists()
        if ctl.schedule_list.isVisible() and not ctl.settings.pinned_open:
            ctl.schedule_list.force_hide()
        ctl._start_group(group, "Started")

    def run_scheduled(self, group: Group) -> None:
        """The scheduler's turn: run it without touching the lists the user has open."""
        from .controller import PopupMode

        self._ctl._start_group(group, "Scheduled run")
        if self._ctl._schedules_only():
            self._ctl._refresh_standalone(PopupMode.SCHEDULES_ONLY)

    def start_group(self, group: Group, notice: str) -> None:
        ctl = self._ctl
        steps = execution_steps(group, ctl.cfg.config.launchers)
        if not steps:
            stay_on_top_warning(
                ctl.trigger,
                "Nothing to launch",
                f"'{group.name}' has no launchers.",
            )
            return
        errors: list[str] = []

        def on_error(item: Launcher, exc: Exception) -> None:
            errors.append(f"{item.name}: {exc}")

        def on_finished() -> None:
            if errors:
                stay_on_top_warning(ctl.trigger, "Launch failed", "\n".join(errors))

        self.notify(notice, group.name)
        run_group_steps(
            steps,
            launch,
            lambda delay, callback: QTimer.singleShot(delay, ctl.trigger, callback),
            gap_ms=GROUP_STEP_GAP_MS,
            on_error=on_error,
            on_finished=on_finished,
        )
