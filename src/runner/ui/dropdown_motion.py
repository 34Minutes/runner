"""Show, hide, and fade for DropdownPanel, alone or on a LockedPairMotion clock.

A mixin. It has no state of its own; DropdownPanel.__init__ sets every
attribute these methods use."""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Qt,
)
from PySide6.QtWidgets import (
    QMenu,
    QApplication,
)

from .locked_pair import LockedPairMotion


class PanelMotionMixin:

    def ensure_visible_and_sized(self) -> None:
        """Ensure the dropdown is visible at the correct full content height.
        Safe to call when pinned_open: prevents unwanted collapses after moves,
        resizes of trigger, or click interactions.
        """
        self._cancel_hide()
        self._update_height_for_content()
        if not self.isVisible():
            self.show()
            self.raise_()  # bring list forward (caller will raise trigger after to keep arrow on top)
            self._place()
            self.raise_()
            self.setWindowOpacity(self._rest_opacity())
        else:
            self._place()
            # Clear anim constraints so our fixed target from _update rules
            self._frame.setMinimumHeight(0)
            self._frame.setMaximumHeight(16777215)
            self._frame.updateGeometry()
            self.updateGeometry()
        if self._current_button is not None and not self._current_button.isVisible():
            self._clear_keyboard_selection()

    def _do_hide(self) -> None:
        self.start_hide_animation()

    def is_closing(self) -> bool:
        """True while a hide animation is committed to emitting closed."""
        if self._linked_closing:
            return True
        return self._close_motion != 0 and self._close_motion == self._motion

    def set_locked_pair(self, pair: LockedPairMotion | None) -> None:
        """Share open/close progress with the other hover list. None detaches it."""
        self._locked_pair = pair

    def capture_open_pose(self, *, focus: bool = True) -> None:
        """Show this list at its full size and remember that pose.

        The locked pair then drives both lists from one fraction. Solo
        animations are stopped here so they cannot fight that clock.
        """
        self._cancel_hide()
        self._invalidate_motion()
        self._close_motion = 0
        self._linked_closing = False
        self._button_container.setMinimumHeight(0)
        self._scroll.setMinimumHeight(0)
        self._frame.setMinimumHeight(0)
        self._frame.setMaximumHeight(16777215)

        menu_open = isinstance(QApplication.activePopupWidget(), QMenu)
        take_focus = focus and not menu_open
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, not take_focus)
        self.show()
        self.raise_()
        self._update_height_for_content()
        self._place()
        self.raise_()
        if take_focus:
            self.setFocus(Qt.FocusReason.OtherFocusReason)

        self._linked_full_h = max(1, self._frame.height())
        self._linked_x = self.x()
        self._linked_edge = int(self._fixed_edge_y)
        self._linked_grow_top = bool(self._grow_from_top)

    def apply_open_fraction(self, fraction: float) -> None:
        """fraction 0 is invisible, 1 is fully solid. The list stays at its full
        size and place throughout: it only fades, so its rows never move under
        the pointer. Two lists driven together share the fraction."""
        full_h = self._linked_full_h
        if full_h <= 0:
            return
        fraction = max(0.0, min(1.0, float(fraction)))
        self._button_container.setMinimumHeight(0)
        self._scroll.setMinimumHeight(0)
        self._frame.setMinimumHeight(0)
        self._frame.setMaximumHeight(full_h)
        self._frame.setFixedHeight(full_h)
        self.setFixedHeight(full_h)
        y = self._linked_edge if self._linked_grow_top else self._linked_edge - full_h
        self.move(self._linked_x, y)
        self._linked_fraction = fraction
        self.setWindowOpacity(fraction * self._rest_opacity())

    def release_open_pose(self) -> None:
        """The locked open finished. Restore normal resizing."""
        self._linked_closing = False
        self._linked_fraction = 1.0
        self.setWindowOpacity(self._rest_opacity())
        self._frame.setMinimumHeight(0)
        self._frame.setMaximumHeight(16777215)
        self._update_height_for_content()
        if self.isVisible():
            self._place()

    def release_closed_pose(self) -> None:
        """The locked close finished. Hide and tell listeners."""
        self._linked_closing = False
        self._linked_full_h = 0
        self._search_edit.clear()
        self._clear_keyboard_selection()
        self._visible_buttons.clear()
        self.hide()
        self.setWindowOpacity(self._rest_opacity())
        self._frame.setMinimumHeight(0)
        self._frame.setMaximumHeight(16777215)
        self._frame.setFixedHeight(self._frame.sizeHint().height() or 120)
        self.closed.emit()

    def mark_linked_closing(self) -> None:
        self._linked_closing = True

    def clear_linked_closing(self) -> None:
        self._linked_closing = False

    def cancel_close(self) -> None:
        """Stop a close already in progress and leave this list fully open.

        Replaying the open animation would collapse the list under the pointer.
        A locked pair snaps both lists, so one cannot finish closing alone.
        """
        self._cancel_hide()
        if self._locked_pair is not None and self._locked_pair.is_closing():
            self._locked_pair.snap_open()
            return
        if not self.is_closing():
            return
        self._invalidate_motion()
        self._close_motion = 0
        self.setWindowOpacity(self._rest_opacity())
        self._frame.setMinimumHeight(0)
        self._frame.setMaximumHeight(16777215)
        self._update_height_for_content()
        if self.isVisible():
            self._place()

    def _invalidate_motion(self) -> int:
        """Stop show/hide animations. Their finish handlers then do nothing."""
        self._motion += 1
        running = self._anims
        self._anims = []
        for anim in running:
            anim.stop()
        return self._motion

    def _track_anim(self, anim: QPropertyAnimation) -> None:
        self._anims.append(anim)

    # --- Animations ---
    def start_show_animation(self, *, focus: bool = True) -> None:
        if self._locked_pair is not None:
            self._locked_pair.abandon(self)
        self._linked_closing = False
        self._cancel_hide()
        motion = self._invalidate_motion()
        self._close_motion = 0
        # Pin and Show groups open this panel from a toggle on the arrow menu.
        # Taking focus would dismiss that popup while the pointer is still on it.
        # A drag also skips focus so the new list does not steal the mouse grab.
        menu_open = isinstance(QApplication.activePopupWidget(), QMenu)
        take_focus = focus and not menu_open
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, not take_focus)
        self.show()
        self.raise_()
        self._place()
        self.raise_()
        if take_focus:
            self.setFocus(Qt.FocusReason.OtherFocusReason)

        # Fade in at full size and in place. Growing toward or away from the
        # arrow moved rows under the pointer, which could reopen a closing list.
        self._update_height_for_content()
        self._place()
        self.setWindowOpacity(0.0)

        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(self._config.settings.animation_duration_ms)
        anim.setStartValue(0.0)
        anim.setEndValue(self._rest_opacity())
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def on_finished(motion: int = motion) -> None:
            if motion != self._motion:
                return
            self.setWindowOpacity(self._rest_opacity())

        anim.finished.connect(on_finished)

        self._animation = anim  # keep ref
        self._track_anim(anim)
        anim.start()

    def start_hide_animation(self) -> None:
        """Fade this list out where it is, then close it.

        The opacity still eases to nothing. The list does not slide or shrink.
        """
        if self._pinned():
            return
        if self._locked_pair is not None:
            self._locked_pair.abandon(self)
        self._linked_closing = False
        if self._drag_active:
            self._abort_drag_without_commit()
        if not self.isVisible():
            return

        decay_ms = self._decay_ms()
        if decay_ms <= 0:
            self.force_hide()
            return

        motion = self._invalidate_motion()
        self._close_motion = motion

        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(decay_ms)
        anim.setStartValue(self.windowOpacity())
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.InCubic)

        def on_finished(motion: int = motion) -> None:
            if motion != self._motion:
                return
            self._close_motion = 0
            self._search_edit.clear()
            self._clear_keyboard_selection()
            self._visible_buttons.clear()
            self.hide()
            self.setWindowOpacity(self._rest_opacity())
            self._frame.setMinimumHeight(0)
            self._frame.setMaximumHeight(16777215)
            self.closed.emit()

        anim.finished.connect(on_finished)
        self._animation = anim
        self._track_anim(anim)
        anim.start()

    def force_hide(self) -> None:
        """Immediate hide (used on launch or escape)."""
        was_visible = self.isVisible()
        if self._locked_pair is not None:
            self._locked_pair.abandon(self)
        self._linked_closing = False
        if self._drag_active:
            self._abort_drag_without_commit()
        else:
            self._hide_ghost()
        self._cancel_hide()
        self._invalidate_motion()
        self._close_motion = 0
        self._search_edit.clear()
        self._clear_keyboard_selection()
        self._visible_buttons.clear()
        self.hide()
        self.setWindowOpacity(self._rest_opacity())
        self._grow_from_top = True
        self._fixed_edge_y = 0
        if was_visible:
            self.closed.emit()
