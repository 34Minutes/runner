"""Row widgets of a DropdownPanel other than LaunchButton."""

from __future__ import annotations

from PySide6.QtCore import (
    QEvent,
    Qt,
    Signal,
)
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
)

from .theme import ghost_qss, submenu_qss


class SubmenuButton(QPushButton):
    """A main-list row that opens another list on hover. It does not launch."""

    hovered = Signal(str)
    left = Signal(str)

    def __init__(self, item_id: str, name: str, parent=None) -> None:
        super().__init__(f"{name}    ›", parent)
        self.item_id = item_id
        self.item_name = name
        self.setObjectName("submenuRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(28)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(f"{name} container group")
        self.setAccessibleDescription(
            "Press Enter or Right arrow, or hover, to open its launchers"
        )
        self._kb_selected = False
        self.apply_theme()
        self.setToolTip("Hover to open\nDrag up or down to reorder\nRight-click to edit or delete")

    def apply_theme(self) -> None:
        self.setStyleSheet(submenu_qss())

    def set_keyboard_selected(self, selected: bool) -> None:
        self._kb_selected = selected
        self.setProperty("kbSelected", "true" if selected else "false")
        self.style().polish(self)
        self.update()

    def is_keyboard_selected(self) -> bool:
        return self._kb_selected

    def enterEvent(self, event: QEvent) -> None:  # type: ignore[override]
        self.hovered.emit(self.item_id)
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # type: ignore[override]
        self.left.emit(self.item_id)
        super().leaveEvent(event)


class _RowGhost(QWidget):
    """Yellow-bordered stand-in that follows the pointer outside the list.

    The real row lives in a scroll area, which clips it. This window is
    mouse-transparent so the drag's mouse grab stays on the source row.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._label = QLabel(self)
        self.apply_theme()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)
        self.hide()

    def set_text(self, text: str) -> None:
        self._label.setText(text)

    def apply_theme(self) -> None:
        self._label.setStyleSheet(ghost_qss())
