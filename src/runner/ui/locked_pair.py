"""One open/close clock shared by the main popup and the execute-groups list."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QObject,
    QVariantAnimation,
)

# Close fades in place for about a quarter second so the pointer can reach a
# neighbouring list. The list does not slide or shrink. Opening still uses
# Settings.animation_duration_ms.
_HIDE_DECAY_MS = 250

if TYPE_CHECKING:
    from .dropdown import DropdownPanel


class LockedPairMotion(QObject):
    """One open/close clock for the main popup and the execute-groups list.

    Arrow hover starts both. They keep the same opacity and the same fraction
    of their full height for the whole animation, including a reverse.
    """

    def __init__(
        self,
        parent: QObject,
        open_duration_ms: Callable[[], int],
        hide_duration_ms: int | Callable[[], int] = _HIDE_DECAY_MS,
    ) -> None:
        super().__init__(parent)
        self._open_duration_ms = open_duration_ms
        self._hide_duration_ms = hide_duration_ms
        self._panels: list[DropdownPanel] = []
        self._progress = 0.0
        self._target = 0.0
        self._presented = False
        self._closing = False
        self._generation = 0
        self._finish_generation = -1
        self._anim = QVariantAnimation(self)
        self._anim.valueChanged.connect(self._on_value)
        self._anim.finished.connect(self._on_finished)

    def progress(self) -> float:
        return self._progress

    def is_running(self) -> bool:
        return self._anim.state() == QAbstractAnimation.State.Running

    def is_presented(self) -> bool:
        return self._presented

    def is_closing(self) -> bool:
        return self._closing

    def open(self, panels: list[DropdownPanel], *, focus_first: bool = True) -> None:
        """Animate every panel from the shared progress up to fully open."""
        if not self._presented:
            self._progress = 0.0
        self._closing = False
        already_open = (
            self._presented
            and self._progress >= 0.999
            and not self.is_running()
        )
        self._halt_clock()
        for panel in panels:
            panel.clear_linked_closing()
        self._prepare(panels, focus_first=focus_first)
        self._presented = True
        if already_open:
            self._progress = 1.0
            self._target = 1.0
            self._apply(1.0)
            self._arrive(1.0)
            return
        self._retarget(1.0, QEasingCurve.Type.OutCubic, self._open_duration_ms())

    def close_visible(self, panels: list[DropdownPanel]) -> bool:
        """Close both lists on this clock, adopting them if they opened apart.

        Returns false when fewer than two lists are on screen.
        """
        visible = [panel for panel in panels if panel.isVisible()]
        if len(visible) < 2:
            return False
        if not self._presented:
            rest = visible[0]._rest_opacity() or 1.0
            fraction = min(float(panel.windowOpacity()) / rest for panel in visible)
            self._progress = max(0.0, min(1.0, fraction))
            self._presented = True
        self.close(visible)
        return True

    def close(self, panels: list[DropdownPanel]) -> None:
        """Animate the panels that are still showing down together."""
        if not self._presented:
            return
        visible = [panel for panel in panels if panel.isVisible()]
        if len(visible) < 2:
            return
        for panel in visible:
            if panel._drag_active:
                panel._abort_drag_without_commit()
        self._prepare(visible, focus_first=False)
        self._presented = True
        self._closing = True
        for panel in self._panels:
            panel.mark_linked_closing()
        self._retarget(0.0, QEasingCurve.Type.InCubic, self._hide_ms())

    def snap_open(self) -> None:
        """Stop a close and leave both lists fully open together."""
        if not self._panels:
            return
        self._halt_clock()
        self._closing = False
        self._presented = True
        self._progress = 1.0
        self._target = 1.0
        for panel in list(self._panels):
            panel.clear_linked_closing()
            panel.apply_open_fraction(1.0)
            panel.release_open_pose()

    def reposition(self, panels: list[DropdownPanel]) -> None:
        """Move both lists with the arrow without letting one jump ahead."""
        if not self._presented:
            return
        running = self.is_running()
        fraction = self._progress
        target = self._target if running else fraction
        closing = self._closing
        self._halt_clock()
        self._prepare(panels, focus_first=False)
        self._progress = fraction
        self._presented = True
        self._closing = closing
        self._apply(fraction)
        if closing:
            for panel in self._panels:
                panel.mark_linked_closing()
        if running and abs(target - fraction) >= 0.001:
            easing = (
                QEasingCurve.Type.InCubic
                if target < fraction
                else QEasingCurve.Type.OutCubic
            )
            duration_ms = self._hide_ms() if target < fraction else self._open_duration_ms()
            self._retarget(target, easing, duration_ms)
            return
        if fraction >= 0.999:
            self._progress = 1.0
            self._target = 1.0
            self._arrive(1.0)

    def abandon(self, panel: DropdownPanel) -> None:
        """One list is animating on its own. Stop the shared clock.

        Any other list that is still visible snaps fully open, so it is not
        left mid-fade with nobody driving it.
        """
        if not self._presented and not self.is_running():
            return
        self._halt_clock()
        others = [other for other in self._panels if other is not panel and other.isVisible()]
        self._panels = []
        self._closing = False
        self._presented = False
        self._progress = 0.0
        self._target = 0.0
        for other in others:
            other.clear_linked_closing()
            other.apply_open_fraction(1.0)
            other.release_open_pose()

    def _prepare(self, panels: list[DropdownPanel], *, focus_first: bool) -> None:
        self._panels = list(panels)
        for index, panel in enumerate(self._panels):
            panel.capture_open_pose(focus=focus_first and index == 0)

    def _hide_ms(self) -> int:
        raw = self._hide_duration_ms() if callable(self._hide_duration_ms) else self._hide_duration_ms
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = _HIDE_DECAY_MS
        return max(0, min(1000, value))

    def _halt_clock(self) -> None:
        self._generation += 1
        self._finish_generation = -1
        self._anim.stop()

    def _retarget(self, target: float, easing: QEasingCurve.Type, duration_ms: int) -> None:
        self._generation += 1
        self._finish_generation = -1
        self._target = target
        self._anim.stop()
        span = abs(target - self._progress)
        if span < 0.001:
            self._progress = target
            self._apply(target)
            self._arrive(target)
            return
        self._anim.setEasingCurve(easing)
        self._anim.setDuration(max(1, int(round(duration_ms * span))))
        self._anim.setStartValue(self._progress)
        self._anim.setEndValue(target)
        self._apply(self._progress)
        self._finish_generation = self._generation
        self._anim.start()

    def _apply(self, fraction: float) -> None:
        for panel in self._panels:
            panel.apply_open_fraction(fraction)

    def _on_value(self, value: object) -> None:
        if self._finish_generation != self._generation:
            return
        self._progress = float(value)
        self._apply(self._progress)

    def _on_finished(self) -> None:
        if self._finish_generation != self._generation:
            return
        self._finish_generation = -1
        self._progress = self._target
        self._arrive(self._target)

    def _arrive(self, target: float) -> None:
        if target >= 1.0:
            self._closing = False
            self._presented = True
            self._progress = 1.0
            self._target = 1.0
            for panel in list(self._panels):
                panel.clear_linked_closing()
                panel.release_open_pose()
            return
        self._closing = False
        self._presented = False
        self._progress = 0.0
        self._target = 0.0
        for panel in list(self._panels):
            panel.clear_linked_closing()
            panel.release_closed_pose()
