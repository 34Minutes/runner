"""A single clickable launcher button inside the dropdown."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

from ..config import Launcher


class LaunchButton(QPushButton):
    """Styled button representing one launcher entry."""

    def __init__(self, launcher: Launcher, parent=None):
        super().__init__(launcher.name, parent)
        self.launcher = launcher
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(28)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._kb_selected = False
        self._apply_style()
        # Future: add icon on left
        self.setToolTip(f"Launch: {launcher.command} {launcher.args}".strip())

    def _apply_style(self) -> None:
        # Base + hover + pressed + keyboard-selected (for arrow nav highlight)
        # Use attribute selector for kbSelected so we can toggle via setProperty + polish
        self.setStyleSheet(
            """
            QPushButton {
                background-color: rgba(55, 55, 60, 200);
                color: #eee;
                border: 1px solid rgba(90, 90, 95, 180);
                border-radius: 5px;
                padding: 4px 10px;
                text-align: left;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: rgba(70, 110, 170, 210);
                border: 1px solid rgba(100, 140, 200, 220);
            }
            QPushButton:pressed {
                background-color: rgba(50, 85, 140, 230);
            }
            QPushButton[kbSelected="true"] {
                background-color: rgba(65, 95, 145, 225);
                border: 1px solid rgba(120, 160, 220, 240);
            }
            QPushButton[kbSelected="true"]:hover {
                background-color: rgba(75, 115, 175, 230);
                border: 1px solid rgba(130, 170, 230, 250);
            }
            """
        )

    def set_keyboard_selected(self, selected: bool) -> None:
        """Highlight this button as the current keyboard-navigated item."""
        self._kb_selected = selected
        self.setProperty("kbSelected", "true" if selected else "false")
        # Force style recompute
        self.style().polish(self)
        self.update()

    def is_keyboard_selected(self) -> bool:
        return self._kb_selected

    def sizeHint(self):
        sh = super().sizeHint()
        # Ensure sizeHint reflects our intended row height (minHeight) so that
        # container layouts and sizeHint/minimumSize queries in DropdownPanel
        # compute a tall enough natural height. Without this the VBox can
        # under-allocate and squash the 2px spacing.
        min_h = self.minimumHeight()
        if sh.height() < min_h:
            return sh.expandedTo(type(sh)(sh.width(), min_h))
        return sh
