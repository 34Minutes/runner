"""Help, from the arrow's right-click menu: runner/help.md, shown in a window.

It isn't modal, so it can stay open beside Runner while you try things, and
it doesn't hold off `runner ctl` changes the way an editing window does.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QTextCursor
from PySide6.QtWidgets import QDialogButtonBox, QTextBrowser, QVBoxLayout, QWidget

from . import theme
from .stay_on_top import StayOnTopDialog

HELP_FILE = Path(__file__).resolve().parent.parent / "help.md"


def help_text() -> str:
    try:
        return HELP_FILE.read_text(encoding="utf-8")
    except OSError:
        return "# Runner Help\n\nThe help file is missing from this copy of Runner."


def _shade_code_blocks(browser: QTextBrowser, shade: str) -> None:
    """Give the commands to copy a background. Qt's Markdown leaves code blocks plain."""
    document = browser.document()
    block = document.begin()
    while block.isValid():
        fmt = block.blockFormat()
        if fmt.nonBreakableLines():  # what Qt marks a fenced code block with
            fmt.setBackground(QColor(shade))
            fmt.setLeftMargin(8)
            fmt.setRightMargin(8)
            cursor = QTextCursor(block)
            cursor.setBlockFormat(fmt)
        block = block.next()


class HelpWindow(StayOnTopDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Runner Help")
        self.setModal(False)
        self.resize(820, 760)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setMarkdown(help_text())
        self.browser.document().setDocumentMargin(4)
        self.apply_theme()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        layout = QVBoxLayout(self)
        layout.addWidget(self.browser, 1)
        layout.addWidget(buttons)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

    def apply_theme(self) -> None:
        theme.style_dialog(self)
        colors = theme.dialog_colors()
        self.browser.setStyleSheet(
            f"QTextBrowser {{ background: {colors.field}; color: {colors.text};"
            f" border: 1px solid {colors.field_border}; border-radius: 6px; padding: 10px 14px;"
            f" font-size: 14px; }}"
        )
        _shade_code_blocks(self.browser, colors.field_alt)
