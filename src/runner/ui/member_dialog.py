"""The shared screen behind Add/Edit Execute Group and Add/Edit Container Group.

Every launcher is a row. Click a launcher anywhere on its name to include
it. Each click moves that launcher to the top, in the order it was clicked.
Click it again to put it back in the main-view order. Checked rows can be
dragged to change their order. A drag lifts that row off the list and keeps
it under the pointer until release.

Subclasses add their own columns, the extra switches above the table, and
how a saved group is built from the selection.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QMouseEvent, QPainter, QPaintEvent, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..config import ConfigManager, Launcher
from ..groups import display_order, select_member, selected_order_after_drag, unselect_member
from .add_dialog import AddEditDialog
from .stay_on_top import StayOnTopDialog
from .theme import current

DRAG_THRESHOLD_PX = 10
DRAG_ROW_OPACITY = 0.28


class _DragGhost(QWidget):
    """The lifted row, drawn on the dialog so the yellow border cannot hide behind it."""

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("dragGhost")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.label = QLabel(name)
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.addWidget(self.label)
        self._apply_label()

    def _apply_label(self) -> None:
        self.label.setStyleSheet(
            "QLabel {"
            f" color: {current().dialog_selected_fg};"
            " background: transparent;"
            " border: none;"
            " font-weight: 600;"
            "}"
        )

    def paintEvent(self, event: QPaintEvent) -> None:  # type: ignore[override]
        scheme = current()
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(scheme.dialog_drag_border))
        painter.fillRect(self.rect().adjusted(4, 4, -4, -4), QColor(scheme.dialog_selected_bg))
        painter.end()
        event.accept()


class _ClickCell(QWidget):
    """A row cell whose whole area toggles one checkbox or switch."""

    def __init__(self, box: QWidget, on_click) -> None:
        super().__init__()
        self.box = box
        self._on_click = on_click
        self.box.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.addWidget(self.box)
        layout.addStretch(1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_click()
        event.accept()


class _NameCell(_ClickCell):
    """Launcher name. A short press toggles membership. A drag reorders it."""

    def __init__(self, checkbox: QCheckBox, on_click, on_drag_start, on_drag_move, on_drag_finish) -> None:
        super().__init__(checkbox, on_click)
        self._on_drag_start = on_drag_start
        self._on_drag_move = on_drag_move
        self._on_drag_finish = on_drag_finish
        self._press_global: QPoint | None = None
        self._dragging = False

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_global = event.globalPosition().toPoint()
            self._dragging = False
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if self._press_global is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            event.accept()
            return
        global_pos = event.globalPosition().toPoint()
        if not self._dragging:
            moved = abs(global_pos.y() - self._press_global.y())
            if moved >= DRAG_THRESHOLD_PX and self.box.isChecked():
                self._dragging = True
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                self._on_drag_start(self._press_global, global_pos)
        if self._dragging:
            self._on_drag_move(global_pos)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        dragging = self._dragging
        self._press_global = None
        self._dragging = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if event.button() == Qt.MouseButton.LeftButton:
            if dragging:
                self._on_drag_finish()
            else:
                self._on_click()
        event.accept()


class MemberPickerDialog(StayOnTopDialog):
    """Name a group and choose its launchers, in order."""

    launchers_changed = Signal()

    # Set by each subclass.
    NOUN = "Group"
    NOTE = ""
    COLUMNS: tuple[str, ...] = ("Launcher",)
    SIZE = (680, 480)
    ROW_HEIGHT = 34
    # Cells in a row that fade while that row is lifted.
    DRAG_ROLES: tuple[str, ...] = ("member",)

    def __init__(self, cfg: ConfigManager, group=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Add {self.NOUN}" if group is None else f"Edit {self.NOUN}")
        self.setModal(True)
        self.resize(*self.SIZE)
        self._cfg = cfg
        self._original = group
        self._result = None
        self._selected: list[str] = []
        self._drag_id: str | None = None
        self._drag_visual: list[str] | None = None
        self._drag_hotspot: QPoint | None = None
        self._drag_updating = False
        self._ghost: _DragGhost | None = None
        self._visual_override: list[str] | None = None
        self._init_state()

        if group is not None:
            known = {launcher.id for launcher in cfg.config.launchers}
            members = [member for member in group.members if member.launcher_id in known]
            self._selected = [member.launcher_id for member in members]
            self._load_members(members)

        self._name_edit = QLineEdit()
        if group is not None:
            self._name_edit.setText(group.name)

        note = QLabel(self.NOTE)
        note.setWordWrap(True)

        self._table = QTableWidget(0, len(self.COLUMNS), self)
        self._table.setHorizontalHeaderLabels(list(self.COLUMNS))
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, len(self.COLUMNS)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)

        add_button = QPushButton("Add new Launcher")
        add_button.clicked.connect(self._on_add_launcher)
        save_button = QPushButton("Save")
        save_button.setDefault(True)
        save_button.clicked.connect(self.accept)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addWidget(add_button)
        buttons.addStretch(1)
        buttons.addWidget(save_button)
        buttons.addWidget(cancel_button)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Name:"))
        layout.addWidget(self._name_edit)
        for widget in self._extra_widgets(group):
            layout.addWidget(widget)
        layout.addWidget(note)
        layout.addWidget(self._table, 1)
        for widget in self._bottom_widgets(group):
            layout.addWidget(widget)
        layout.addLayout(buttons)

        self._rebuild()
        self._name_edit.setFocus()

    # ---------------------------------------------------- subclass hooks

    def _init_state(self) -> None:
        """Set up subclass state. Runs before the group is read or the table is built."""

    def _load_members(self, members: list) -> None:
        """Read per-member flags from the group being edited."""

    def _extra_widgets(self, group) -> list[QWidget]:
        """Widgets between the name and the note."""
        return []

    def _bottom_widgets(self, group) -> list[QWidget]:
        """Widgets between the table and the buttons."""
        return []

    def _fill_row(self, row: int, launcher: Launcher, member: bool) -> None:
        """Put this subclass's cells in columns 1 and up."""

    def _on_unselected(self, launcher_id: str) -> None:
        """A launcher was taken out of the group."""

    def _absorb_member(self, member) -> None:
        """A launcher the add screen put in this group was taken in."""

    def _saved_groups(self) -> list:
        """The config list this kind of group is saved in."""
        return []

    # ------------------------------------------------------------ public

    @property
    def result_group(self):
        return self._result

    def display_ids(self) -> list[str]:
        ids: list[str] = []
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item is not None:
                ids.append(item.data(Qt.ItemDataRole.UserRole))
        return ids

    def name_cell(self, launcher_id: str) -> _NameCell:
        return self._cell(launcher_id, "member")  # type: ignore[return-value]

    # ----------------------------------------------------------- the table

    def _cell(self, launcher_id: str, role: str) -> _ClickCell:
        for row in range(self._table.rowCount()):
            for column in range(self._table.columnCount()):
                widget = self._table.cellWidget(row, column)
                if not isinstance(widget, _ClickCell):
                    continue
                if widget.box.property("launcher_id") == launcher_id and widget.box.property("role") == role:
                    return widget
        raise KeyError(launcher_id)

    def _launcher(self, launcher_id: str) -> Launcher | None:
        return next((item for item in self._cfg.config.launchers if item.id == launcher_id), None)

    def _base_ids(self) -> list[str]:
        return [launcher.id for launcher in self._cfg.config.launchers]

    def _rebuild(self) -> None:
        order = self._visual_override
        if order is None:
            order = display_order(self._base_ids(), self._selected)
        by_id = {launcher.id: launcher for launcher in self._cfg.config.launchers}
        selected = set(self._selected)
        self._table.setRowCount(len(order))
        for row, launcher_id in enumerate(order):
            launcher = by_id[launcher_id]
            member = launcher_id in selected
            for column in range(len(self.COLUMNS)):
                self._table.setItem(row, column, self._id_item(launcher_id, member))
            self._table.setCellWidget(row, 0, self._name_widget(launcher, member))
            self._fill_row(row, launcher, member)
            self._table.setRowHeight(row, self.ROW_HEIGHT)
        self._table.resizeColumnsToContents()
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

    def _id_item(self, launcher_id: str, member: bool) -> QTableWidgetItem:
        item = QTableWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, launcher_id)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        if member:
            item.setBackground(QBrush(QColor(current().dialog_selected_bg)))
        return item

    def _name_widget(self, launcher: Launcher, member: bool) -> _NameCell:
        box = QCheckBox(launcher.name)
        box.setProperty("launcher_id", launcher.id)
        box.setProperty("role", "member")
        box.setChecked(member)
        box.toggled.connect(lambda checked, lid=launcher.id: self._on_member_toggled(lid, checked))
        cell = _NameCell(
            box,
            on_click=box.toggle,
            on_drag_start=lambda press, pos, lid=launcher.id: self._begin_drag(lid, press, pos),
            on_drag_move=self._move_drag,
            on_drag_finish=self._finish_drag,
        )
        self._paint(cell, member)
        return cell

    def _paint(self, cell: _ClickCell, member: bool) -> None:
        """Fill the whole cell. A stylesheet background does not paint on a plain QWidget."""
        cell.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        cell.setAutoFillBackground(True)
        box = cell.box
        if not member:
            cell.setPalette(self._table.palette())
            box.setPalette(self._table.palette())
            cell.setStyleSheet("background: transparent;")
            box.setStyleSheet("background: transparent;")
            return
        scheme = current()
        colour = QColor(scheme.dialog_selected_bg)
        text = QColor(scheme.dialog_selected_fg)
        palette = cell.palette()
        palette.setColor(QPalette.ColorRole.Window, colour)
        palette.setColor(QPalette.ColorRole.Base, colour)
        palette.setColor(QPalette.ColorRole.WindowText, text)
        palette.setColor(QPalette.ColorRole.Text, text)
        cell.setPalette(palette)
        box.setPalette(palette)
        cell.setStyleSheet(f"background-color: {scheme.dialog_selected_bg};")
        if isinstance(box, QCheckBox):
            box.setStyleSheet(
                "QCheckBox {"
                f" color: {scheme.dialog_selected_fg};"
                " background-color: transparent;"
                " font-weight: 600;"
                "}"
            )
        else:
            box.setStyleSheet("background: transparent;")

    # ----------------------------------------------------------- selection

    def _on_member_toggled(self, launcher_id: str, checked: bool) -> None:
        if self._drag_id:
            return
        if checked:
            self._selected = select_member(self._base_ids(), self._selected, launcher_id)
        else:
            self._selected = unselect_member(self._selected, launcher_id)
            self._on_unselected(launcher_id)
        # Rebuild after the click finishes. Replacing the cell inside the
        # click deletes the widget that is still handling the mouse release.
        QTimer.singleShot(0, self._rebuild)

    def _on_visual_order(self, visual_ids: list[str]) -> None:
        self._selected = selected_order_after_drag(visual_ids, self._selected)
        QTimer.singleShot(0, self._rebuild)

    # ------------------------------------------------------------ dragging

    def eventFilter(self, obj, event):  # type: ignore[override]
        # A new window under the pointer can steal the row's mouse grab on macOS.
        # Keep following the cursor, and drop, from application-wide mouse events.
        if self._drag_id is not None and isinstance(event, QMouseEvent):
            if event.type() == QEvent.Type.MouseMove and event.buttons() & Qt.MouseButton.LeftButton:
                self._move_drag(event.globalPosition().toPoint())
            elif (
                event.type() == QEvent.Type.MouseButtonRelease
                and event.button() == Qt.MouseButton.LeftButton
            ):
                self._finish_drag()
        return super().eventFilter(obj, event)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._drag_id = None
        self._drag_hotspot = None
        self._hide_drag_chrome()
        super().closeEvent(event)

    def _begin_drag(self, launcher_id: str, press_global: QPoint, global_pos: QPoint) -> None:
        if launcher_id not in self._selected or self._drag_id:
            return
        ids = self.display_ids()
        if launcher_id not in ids:
            return
        self._drag_id = launcher_id
        self._drag_visual = list(ids)
        row = ids.index(launcher_id)
        viewport = self._table.viewport()
        origin = viewport.mapToGlobal(QPoint(0, self._table.rowViewportPosition(row)))
        # The grabbed point on the row stays under the pointer.
        self._drag_hotspot = press_global - origin
        ghost = _DragGhost(self.name_cell(launcher_id).box.text(), self)
        ghost.resize(viewport.width(), self._table.rowHeight(row))
        ghost.move(self.mapFromGlobal(global_pos - self._drag_hotspot))
        ghost.show()
        ghost.raise_()
        self._ghost = ghost
        for role in self.DRAG_ROLES:
            cell = self._cell(launcher_id, role)
            effect = QGraphicsOpacityEffect(cell)
            effect.setOpacity(DRAG_ROW_OPACITY)
            cell.setGraphicsEffect(effect)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        self._move_drag(global_pos)

    def _move_drag(self, global_pos: QPoint) -> None:
        """Keep the lifted row under the pointer. The list updates on release."""
        if self._drag_updating or not self._drag_id or self._drag_visual is None:
            return
        self._drag_updating = True
        try:
            self._move_drag_body(global_pos)
        finally:
            self._drag_updating = False

    def _move_drag_body(self, global_pos: QPoint) -> None:
        if self._ghost is not None and self._drag_hotspot is not None:
            self._ghost.move(self.mapFromGlobal(global_pos - self._drag_hotspot))
            self._ghost.raise_()
        local = self._table.viewport().mapFromGlobal(global_pos)
        dest = self._table.indexAt(local).row()
        ids = list(self.display_ids())
        if self._drag_id not in ids:
            return
        if dest < 0:
            dest = len(ids) - 1
        source = ids.index(self._drag_id)
        new_ids = list(ids)
        if dest != source:
            moved = new_ids.pop(source)
            new_ids.insert(min(dest, len(new_ids)), moved)
        self._drag_visual = new_ids

    def _hide_drag_chrome(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        if self._ghost is not None:
            self._ghost.hide()
            self._ghost.deleteLater()
            self._ghost = None

    def _finish_drag(self) -> None:
        if not self._drag_id:
            return
        visual = list(self._drag_visual or self.display_ids())
        self._drag_id = None
        self._drag_visual = None
        self._drag_hotspot = None
        self._visual_override = None
        self._hide_drag_chrome()
        self._on_visual_order(visual)

    # ------------------------------------------------------- new launcher

    def _on_add_launcher(self) -> None:
        dialog = AddEditDialog(None, self, cfg=self._cfg)
        if not dialog.exec():
            return
        created = dialog.result_launcher
        if created is None:
            return
        self._cfg.add_launcher(created)
        self.launchers_changed.emit()
        self._absorb_new_member(created.id)
        self._rebuild()

    def _absorb_new_member(self, launcher_id: str) -> None:
        """Keep a launcher the add screen just put in this group."""
        if self._original is None:
            return
        saved = next(
            (group for group in self._saved_groups() if group.id == self._original.id),
            None,
        )
        if saved is None:
            return
        for member in saved.members:
            if member.launcher_id != launcher_id:
                continue
            self._selected = select_member(self._base_ids(), self._selected, launcher_id)
            self._absorb_member(member)
            return
