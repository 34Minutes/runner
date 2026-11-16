"""A single clickable launcher button inside the dropdown."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

from ..config import Launcher
from .theme import launch_button_qss


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
        self.setToolTip(
            f"Launch: {launcher.command} {launcher.args}".strip()
            + "\nDrag to reorder, or onto another menu to move it"
            + "\nRight-click to edit or delete"
        )

    def _apply_style(self) -> None:
        # Base + hover + pressed + keyboard-selected (for arrow nav highlight).
        # kbSelected is an attribute selector toggled via setProperty + polish.
        self.setStyleSheet(launch_button_qss())

    def apply_theme(self) -> None:
        self._apply_style()

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
