"""Add or edit a container group.

A container group is a submenu. Click a launcher name to include it. Each
click moves that launcher to the top, in the order it was clicked. Click it
again to put it back. Checked rows can be dragged to change the submenu order.
Only in Container Group is a switch on the row. It is saved with this container.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QPoint, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QMouseEvent, QPalette
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

from ..config import ConfigManager, ContainerGroup, ContainerMember
from ..groups import (
    display_order,
    select_member,
    selected_order_after_drag,
    unselect_member,
)
from .add_dialog import AddEditDialog
from .group_dialog import _DragGhost, _NameCell, _SELECTED_BG, _SELECTED_FG
from .stay_on_top import StayOnTopDialog, warning
from .toggle_switch import ToggleSwitch

_NOTE = (
    "These items open in a submenu when you hover this container group. "
    "They are not run together."
)
_DRAG_ROW_OPACITY = 0.28


class _SwitchCell(QWidget):
    """A row cell whose whole area toggles Only in Container Group."""

    def __init__(self, switch: ToggleSwitch, on_click) -> None:
        super().__init__()
        self.box = switch
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


class ContainerDialog(StayOnTopDialog):
    """Name a container group and choose which launchers appear in its submenu."""

    launchers_changed = Signal()

    def __init__(
        self,
        cfg: ConfigManager,
        group: ContainerGroup | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Container Group" if group is None else "Edit Container Group")
        self.setModal(True)
        self.resize(760, 480)
        self._cfg = cfg
        self._original = group
        self._result: ContainerGroup | None = None
        self._selected: list[str] = []
        self._only: dict[str, bool] = {}
        self._drag_id: str | None = None
        self._drag_visual: list[str] | None = None
        self._drag_hotspot: QPoint | None = None
        self._drag_updating = False
        self._ghost: _DragGhost | None = None
        self._visual_override: list[str] | None = None

        if group is not None:
            known = {launcher.id for launcher in cfg.config.launchers}
            self._selected = [
                member.launcher_id
                for member in group.members
                if member.launcher_id in known
            ]
            self._only = {
                member.launcher_id: member.only_in_container
                for member in group.members
                if member.launcher_id in known
            }

        self._name_edit = QLineEdit()
        if group is not None:
            self._name_edit.setText(group.name)

        note = QLabel(_NOTE)
        note.setWordWrap(True)

        self._table = QTableWidget(0, 2, self)
        self._table.setHorizontalHeaderLabels(["Launcher", "Only in Container Group"])
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)

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
        layout.addWidget(note)
        layout.addWidget(self._table, 1)
        layout.addLayout(buttons)

        self._rebuild()
        self._name_edit.setFocus()

    @property
    def result_group(self) -> ContainerGroup | None:
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

    def only_switch(self, launcher_id: str) -> _SwitchCell:
        return self._cell(launcher_id, "only")  # type: ignore[return-value]

    def _cell(self, launcher_id: str, role: str) -> QWidget:
        for row in range(self._table.rowCount()):
            for column in range(self._table.columnCount()):
                widget = self._table.cellWidget(row, column)
                if not isinstance(widget, (_NameCell, _SwitchCell)):
                    continue
                if widget.box.property("launcher_id") == launcher_id and widget.box.property("role") == role:
                    return widget
        raise KeyError(launcher_id)

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
            self._table.setItem(row, 0, self._id_item(launcher_id, member))
            self._table.setItem(row, 1, self._id_item(launcher_id, member))
            self._table.setCellWidget(row, 0, self._name_widget(launcher, member))
            self._table.setCellWidget(row, 1, self._switch_widget(launcher_id, member))
            self._table.setRowHeight(row, 36)
        self._table.resizeColumnsToContents()
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

    def _id_item(self, launcher_id: str, member: bool) -> QTableWidgetItem:
        item = QTableWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, launcher_id)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        if member:
            item.setBackground(QBrush(QColor(_SELECTED_BG)))
        return item

    def _name_widget(self, launcher, member: bool) -> _NameCell:
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

    def _switch_widget(self, launcher_id: str, member: bool) -> _SwitchCell:
        switch = ToggleSwitch("Only in Container Group")
        switch.setProperty("launcher_id", launcher_id)
        switch.setProperty("role", "only")
        switch.setChecked(member and self._only.get(launcher_id, False))
        switch.setEnabled(member)
        cell = _SwitchCell(switch, on_click=lambda lid=launcher_id: self._on_only_clicked(lid))
        self._paint(cell, member)
        return cell

    def _paint(self, cell: QWidget, member: bool) -> None:
        """Fill the whole cell. A stylesheet background does not paint on a plain QWidget."""
        cell.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        cell.setAutoFillBackground(True)
        box = cell.box  # type: ignore[attr-defined]
        if not member:
            cell.setPalette(self._table.palette())
            box.setPalette(self._table.palette())
            cell.setStyleSheet("background: transparent;")
            box.setStyleSheet("background: transparent;")
            return
        colour = QColor(_SELECTED_BG)
        text = QColor(_SELECTED_FG)
        palette = cell.palette()
        palette.setColor(QPalette.ColorRole.Window, colour)
        palette.setColor(QPalette.ColorRole.Base, colour)
        palette.setColor(QPalette.ColorRole.WindowText, text)
        palette.setColor(QPalette.ColorRole.Text, text)
        cell.setPalette(palette)
        box.setPalette(palette)
        cell.setStyleSheet(f"background-color: {_SELECTED_BG};")
        if isinstance(box, QCheckBox):
            box.setStyleSheet(
                "QCheckBox {"
                f" color: {_SELECTED_FG};"
                " background-color: transparent;"
                " font-weight: 600;"
                "}"
            )
        else:
            box.setStyleSheet("background: transparent;")

    def _on_only_clicked(self, launcher_id: str) -> None:
        if launcher_id not in self._selected:
            return
        self._only[launcher_id] = not self._only.get(launcher_id, False)
        QTimer.singleShot(0, self._rebuild)

    def _on_member_toggled(self, launcher_id: str, checked: bool) -> None:
        if self._drag_id:
            return
        if checked:
            self._selected = select_member(self._base_ids(), self._selected, launcher_id)
        else:
            self._selected = unselect_member(self._selected, launcher_id)
            self._only[launcher_id] = False
        QTimer.singleShot(0, self._rebuild)

    def _on_visual_order(self, visual_ids: list[str]) -> None:
        self._selected = selected_order_after_drag(visual_ids, self._selected)
        QTimer.singleShot(0, self._rebuild)

    def eventFilter(self, obj, event):  # type: ignore[override]
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
        self._drag_hotspot = press_global - origin
        ghost = _DragGhost(self.name_cell(launcher_id).box.text(), self)
        ghost.resize(viewport.width(), self._table.rowHeight(row))
        ghost.move(self.mapFromGlobal(global_pos - self._drag_hotspot))
        ghost.show()
        ghost.raise_()
        self._ghost = ghost
        for role in ("member", "only"):
            cell = self._cell(launcher_id, role)
            effect = QGraphicsOpacityEffect(cell)
            effect.setOpacity(_DRAG_ROW_OPACITY)
            cell.setGraphicsEffect(effect)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        self._move_drag(global_pos)

    def _move_drag(self, global_pos: QPoint) -> None:
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

    def _absorb_new_launcher(self, launcher_id: str) -> None:
        """Keep a launcher the add screen just put in this container."""
        if self._original is None:
            return
        saved = next(
            (group for group in self._cfg.config.container_groups if group.id == self._original.id),
            None,
        )
        if saved is None:
            return
        for member in saved.members:
            if member.launcher_id != launcher_id:
                continue
            self._selected = select_member(self._base_ids(), self._selected, launcher_id)
            self._only[launcher_id] = member.only_in_container
            return

    def _on_add_launcher(self) -> None:
        dialog = AddEditDialog(None, self, cfg=self._cfg)
        if not dialog.exec():
            return
        created = dialog.result_launcher
        if created is None:
            return
        self._cfg.add_launcher(created)
        self.launchers_changed.emit()
        self._absorb_new_launcher(created.id)
        self._rebuild()

    def accept(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            warning(self, "Missing info", "Name is required.")
            return
        members = [
            ContainerMember(launcher_id, only_in_container=self._only.get(launcher_id, False))
            for launcher_id in self._selected
        ]
        if self._original is not None:
            self._original.name = name
            self._original.members = members
            self._result = self._original
        else:
            self._result = ContainerGroup.new(name, members)
        super().accept()
