"""Drag-and-drop for DropdownPanel: reorder rows and drop them onto another list.

A mixin. It has no state of its own; DropdownPanel.__init__ sets every
attribute these methods use."""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPropertyAnimation,
    Qt,
)
from PySide6.QtWidgets import (
    QApplication,
    QPushButton,
)

from ..moves import merge_visible_order
from .launch_button import LaunchButton
from .rows import SubmenuButton, _RowGhost

# Pixels of movement before a press becomes a drag, so a click still launches.
# Any direction counts, so a row can be dragged sideways onto another menu.
_DRAG_THRESHOLD_PX = 10
# A small step out of the column. Large enough to read as lifted, small enough
# that the row still feels under the pointer.
_DRAG_LIFT_X = 8
_DRAG_SLIDE_MS = 150


class DragReorderMixin:

    def _cancel_drag(self) -> None:
        button = self._drag_button
        self._remove_drag_filter()
        self._drag_scroll_timer.stop()
        self._drag_active = False
        self._drag_button = None
        self._external_target = None
        self._hide_ghost()
        self._stop_row_anims()
        if self._drag_detached:
            self._commit_drag_order()
        self._pre_drag_buttons = None
        if button is None:
            return
        if self.mouseGrabber() is button:
            button.releaseMouse()
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._set_drag_style(button, False)

    def _set_drag_style(self, button: QPushButton, dragging: bool) -> None:
        button.setProperty("dragging", "true" if dragging else "false")
        button.style().polish(button)
        button.update()

    def _begin_drag(self, button: QPushButton) -> None:
        self._drag_active = True
        self._cancel_hide()
        self._pre_drag_buttons = list(self._buttons)
        self._pre_drag_tokens = self.row_tokens()
        self._external_target = None
        button.setDown(False)
        self._set_drag_style(button, True)
        button.setCursor(Qt.CursorShape.ClosedHandCursor)
        button.grabMouse()
        self._install_drag_filter()
        self._detach_for_drag(button)
        self._drag_scroll_timer.start()

    def _install_drag_filter(self) -> None:
        # A new window under the pointer can steal the row's mouse grab on macOS.
        if self._app_filter:
            return
        app = QApplication.instance()
        if app is None:
            return
        app.installEventFilter(self)
        self._app_filter = True

    def _remove_drag_filter(self) -> None:
        if not self._app_filter:
            return
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self._app_filter = False

    def _stop_row_anims(self) -> None:
        running = list(self._row_anims.values())
        self._row_anims.clear()
        for anim in running:
            anim.stop()

    def _rows_for_drag(self) -> list[QPushButton]:
        kinds = (LaunchButton, SubmenuButton) if self._mix_rows else (LaunchButton,)
        return [item for item in self._buttons if isinstance(item, kinds) and item.isVisible()]

    def _detach_for_drag(self, button: QPushButton) -> None:
        """Lift this row out of the column and leave a gap the others can slide around."""
        visible = self._rows_for_drag()
        if button not in visible:
            return
        self._drag_order = list(visible)
        self._drag_home_x = button.x()
        self._drag_row_h = max(button.height(), 1)
        self._drag_row_step = self._drag_row_h + self._button_layout.spacing()
        self._drag_base_y = min(item.y() for item in visible)
        content_h = self._drag_base_y + len(visible) * self._drag_row_step
        self._button_container.setMinimumHeight(max(self._button_container.minimumHeight(), content_h))
        for item in visible:
            self._button_layout.removeWidget(item)
        self._drag_detached = True
        self._slide_rest(animate=False)
        self._place_lifted(button)

    def _slide_rest(self, animate: bool) -> None:
        dragged = self._drag_button
        if dragged is None:
            return
        slot = 0
        for button in self._drag_order:
            if button is dragged:
                slot += 1
                continue
            target = QPoint(self._drag_home_x, self._drag_base_y + slot * self._drag_row_step)
            slot += 1
            self._move_row(button, target, animate)

    def _move_row(self, button: QPushButton, target: QPoint, animate: bool) -> None:
        running = self._row_anims.pop(button, None)
        if running is not None:
            running.stop()
        if not animate or button.pos() == target:
            button.move(target)
            return
        anim = QPropertyAnimation(button, b"pos", button)
        anim.setDuration(_DRAG_SLIDE_MS)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(button.pos())
        anim.setEndValue(target)
        anim.start()
        self._row_anims[button] = anim

    def _place_lifted(self, button: QPushButton) -> None:
        local_y = self._button_container.mapFromGlobal(self._drag_last_global).y()
        y = local_y - button.height() // 2
        limit = self._drag_base_y + max(0, len(self._drag_order) - 1) * self._drag_row_step
        y = max(self._drag_base_y, min(y, limit))
        button.move(self._drag_home_x + _DRAG_LIFT_X, y)
        button.raise_()

    def _commit_drag_order(self) -> None:
        if not self._drag_detached:
            return
        self._drag_detached = False
        visible_order = list(self._drag_order)
        self._drag_order = []
        if not visible_order:
            return
        if self._mix_rows:
            self._commit_mixed_order(visible_order)
            return
        in_play = {button.launcher.id for button in visible_order}
        entries = [(button.launcher.id, button.launcher.id in in_play) for button in self._launch_buttons()]
        new_ids = merge_visible_order(entries, [button.launcher.id for button in visible_order])
        by_id = {button.launcher.id: button for button in self._launch_buttons()}
        ordered = [by_id[item_id] for item_id in new_ids if item_id in by_id]
        self._place_launcher_rows(ordered)

    def _commit_mixed_order(self, visible_order: list) -> None:
        visible_tokens = []
        for button in visible_order:
            token = self._token_for(button)
            if token is not None:
                visible_tokens.append(token)
        in_play = set(visible_tokens)
        rows = [button for button in self._buttons if isinstance(button, (LaunchButton, SubmenuButton))]
        entries = []
        for button in rows:
            token = self._token_for(button)
            if token is None:
                continue
            entries.append((token, token in in_play))
        new_tokens = merge_visible_order(entries, visible_tokens)
        by_token = {}
        for button in rows:
            token = self._token_for(button)
            if token is not None:
                by_token[token] = button
        ordered = [by_token[token] for token in new_tokens if token in by_token]
        labels = [
            button
            for button in self._buttons
            if not isinstance(button, (LaunchButton, SubmenuButton))
        ]
        self._relayout_buttons(ordered + labels)

    def _finish_drag(self, global_pos: QPoint) -> None:
        if not self._drag_active or self._drag_button is None:
            return
        button = self._drag_button
        external = self._external_target
        outside = isinstance(button, SubmenuButton) and not self.rect().contains(self.mapFromGlobal(global_pos))
        self._suppress_click = True
        if external is not None and isinstance(button, LaunchButton):
            launcher_id = button.launcher.id
            source_key = self._drag_source_key
            target_key, index = external
            self._cancel_drag()
            self.external_drop.emit(launcher_id, source_key, target_key, index)
            self.drag_finished.emit()
            return
        if outside:
            self._abort_drag_without_commit()
            if not self._pinned():
                self._schedule_hide()
                self.hover_leave.emit()
            self.drag_finished.emit()
            return
        self._cancel_drag()
        self._emit_reordered()
        if not self._pinned():
            local = self.mapFromGlobal(global_pos)
            if not self.rect().contains(local):
                self._schedule_hide()
                self.hover_leave.emit()
        self.drag_finished.emit()

    def _abort_drag_without_commit(self) -> None:
        """Put the rows back. A container row that left this list does not move."""
        self._stop_row_anims()
        if self._pre_drag_buttons is not None:
            self._drag_detached = False
            self._drag_order = []
            self._relayout_buttons(list(self._pre_drag_buttons))
            self._button_layout.activate()
        self._cancel_drag()

    def _emit_reordered(self) -> None:
        if self._mix_rows:
            tokens = self.row_tokens()
            if tokens != self._pre_drag_tokens:
                self.rows_reordered.emit(tokens)
            return
        visible_ids = [b.launcher.id for b in self._launch_buttons() if b.isVisible()]
        visible_set = set(visible_ids)
        if self._order_ids is not None:
            current_ids = list(self._order_ids())
            entries = [(item_id, item_id in visible_set) for item_id in current_ids]
        else:
            current_ids = [launcher.id for launcher in self._config.launchers]
            entries = [
                (launcher.id, launcher.show_in_main and launcher.id in visible_set)
                for launcher in self._config.launchers
            ]
        new_ids = merge_visible_order(entries, visible_ids)
        if new_ids != current_ids:
            self.reordered.emit(new_ids)

    def _target_visible_index(self, global_y: int) -> int:
        """Index to insert the dragged row at. len(visible) means after the last row."""
        if self._drag_detached and self._drag_order:
            origin = self._button_container.mapToGlobal(QPoint(0, self._drag_base_y)).y()
            count = len(self._drag_order)
            for index in range(count):
                center = origin + index * self._drag_row_step + self._drag_row_h / 2
                if global_y < center:
                    return index
            return count
        visible = [b for b in self._launch_buttons() if b.isVisible()]
        for index, button in enumerate(visible):
            center = button.mapToGlobal(QPoint(0, button.height() // 2)).y()
            if global_y < center:
                return index
        return len(visible)

    def _move_dragged_to(self, index: int) -> None:
        dragged = self._drag_button
        if dragged is None:
            return
        visible = list(self._drag_order) if self._drag_detached else self._rows_for_drag()
        if dragged not in visible:
            return
        old = visible.index(dragged)
        # index is an insertion point, so the slot just after the row is the same place.
        if index == old or index == old + 1:
            return
        visible.pop(old)
        if old < index:
            index -= 1
        index = max(0, min(index, len(visible)))
        visible.insert(index, dragged)
        if self._drag_detached:
            self._drag_order = visible
            self._slide_rest(animate=True)
            return
        if self._mix_rows:
            self._commit_mixed_order(visible)
            return

        entries = [(b.launcher.id, b.isVisible()) for b in self._launch_buttons()]
        new_ids = merge_visible_order(entries, [b.launcher.id for b in visible])
        by_id = {b.launcher.id: b for b in self._launch_buttons()}
        ordered = [by_id[item_id] for item_id in new_ids if item_id in by_id]
        self._place_launcher_rows(ordered)

    def _place_launcher_rows(self, launchers: list[LaunchButton]) -> None:
        """Keep container rows above the launchers when a drag reorders the list."""
        prefixes = [button for button in self._buttons if isinstance(button, SubmenuButton)]
        labels = [
            button
            for button in self._buttons
            if not isinstance(button, (LaunchButton, SubmenuButton))
        ]
        self._relayout_buttons(prefixes + launchers + labels)

    def _relayout_buttons(self, buttons: list) -> None:
        for button in buttons:
            self._button_layout.removeWidget(button)
        for button in buttons:
            self._button_layout.addWidget(button)
        self._buttons = list(buttons)
        self._visible_buttons = [b for b in self._buttons if isinstance(b, LaunchButton) and b.isVisible()]

    def _drag_step(self, global_pos: QPoint) -> None:
        if self._in_drag_step:
            return
        self._in_drag_step = True
        try:
            self._drag_last_global = global_pos
            self._autoscroll_once(global_pos)
            if self._container_row_left(global_pos):
                self._external_target = None
                self._hide_ghost()
                if self._drag_detached:
                    self._park_rows(ghost=False)
                return
            external = self._external_at(global_pos)
            if external is not None:
                self._external_target = external
                if self._drag_detached:
                    self._park_rows(ghost=True)
                self._show_ghost(global_pos)
                return
            self._external_target = None
            self._hide_ghost()
            if not self._drag_detached and self._drag_button is not None:
                self._set_drag_style(self._drag_button, True)
                self._detach_for_drag(self._drag_button)
            self._move_dragged_to(self._target_visible_index(global_pos.y()))
            if self._drag_button is not None and self._drag_detached:
                self._place_lifted(self._drag_button)
        finally:
            self._in_drag_step = False

    def _container_row_left(self, global_pos: QPoint) -> bool:
        return isinstance(self._drag_button, SubmenuButton) and not self.rect().contains(
            self.mapFromGlobal(global_pos)
        )

    def _external_at(self, global_pos: QPoint) -> tuple[str, int] | None:
        """A different menu under the pointer. None keeps the drag inside this list."""
        if not self._drag_source_key or self._drag_source_key == "groups":
            return None
        if not isinstance(self._drag_button, LaunchButton) or self._peer_at is None:
            return None
        peer = self._peer_at(global_pos)
        if peer is None or peer is self:
            return None
        found = peer.drop_target_at(global_pos)
        if found is None:
            return None
        key, index = found
        if key == self._drag_source_key:
            return None
        return key, index

    def _park_rows(self, *, ghost: bool) -> None:
        """Put every row back. The ghost, when shown, is what follows the pointer."""
        self._stop_row_anims()
        self._drag_order = []
        self._drag_detached = False
        if self._pre_drag_buttons is not None:
            self._relayout_buttons(list(self._pre_drag_buttons))
            self._button_layout.activate()
        if self._drag_button is not None:
            self._set_drag_style(self._drag_button, not ghost)

    def _ghost_widget(self) -> _RowGhost:
        if self._ghost is None:
            self._ghost = _RowGhost(self)
        return self._ghost

    def _show_ghost(self, global_pos: QPoint) -> None:
        button = self._drag_button
        if button is None:
            return
        ghost = self._ghost_widget()
        ghost.set_text(button.text())
        ghost.setFixedSize(button.size())
        ghost.move(global_pos.x() - button.width() // 2, global_pos.y() - button.height() // 2)
        ghost.show()
        ghost.raise_()

    def _hide_ghost(self) -> None:
        if self._ghost is not None:
            self._ghost.hide()

    def _autoscroll_once(self, global_pos: QPoint) -> None:
        viewport = self._scroll.viewport()
        local_y = viewport.mapFromGlobal(global_pos).y()
        bar = self._scroll.verticalScrollBar()
        if local_y < 16:
            bar.setValue(bar.value() - 14)
        elif local_y > viewport.height() - 16:
            bar.setValue(bar.value() + 14)

    def _drag_autoscroll(self) -> None:
        if not self._drag_active or self._drag_button is None:
            self._drag_scroll_timer.stop()
            return
        self._drag_step(self._drag_last_global)

    def _handle_reorder_event(self, button: QPushButton, event: QEvent) -> bool:
        if not self._allow_reorder:
            return False
        if isinstance(button, SubmenuButton) and not self._mix_rows:
            return False
        kind = event.type()
        if kind == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            if self._drag_active:
                return False
            self._suppress_click = False
            self._drag_button = button
            self._drag_press = event.globalPosition().toPoint()
            self._drag_last_global = self._drag_press
            return False
        if (
            kind == QEvent.Type.MouseMove
            and self._drag_button is button
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            global_pos = event.globalPosition().toPoint()
            if not self._drag_active:
                if (global_pos - self._drag_press).manhattanLength() < _DRAG_THRESHOLD_PX:
                    return False
                self._begin_drag(button)
            self._drag_step(global_pos)
            return True
        if (
            kind == QEvent.Type.MouseButtonRelease
            and event.button() == Qt.MouseButton.LeftButton
            and self._drag_button is button
        ):
            if self._drag_active:
                # Swallow the release so the row does not launch at the end of a drag.
                self._finish_drag(event.globalPosition().toPoint())
                return True
            self._drag_button = None
        return False
