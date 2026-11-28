"""The two pickers a schedule uses, each in its own small window.

DatePickerDialog holds the metal dial: pressing its silver centre, or Enter,
chooses the date. A three-line menu top left holds Show minutes and Now, and the
written-out date under the dial can be typed over to spin the dial there. IntervalPickerDialog holds the interval rollers: the Select
key chooses how often it repeats, and Don't repeat clears it. Both follow the
active colour scheme. Esc closes either one without changing anything.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from PySide6.QtCore import QPointF, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..config import ScheduleEntry
from ..schedule import format_full, parse_when
from . import theme
from .date_dial import MetalDial
from .interval_roller import PLACES, IntervalRoller, digits
from .stay_on_top import StayOnTopDialog


def next_quarter_hour(now: datetime | None = None) -> datetime:
    """A sensible first date for a new schedule: the next quarter hour from now."""
    now = (now or datetime.now()).replace(second=0, microsecond=0)
    return now + timedelta(minutes=15 - now.minute % 15)


def next_hour(when: datetime) -> datetime:
    """when, or the next whole hour after it: a first date when the minute ring is hidden."""
    if when.minute == 0:
        return when
    return when.replace(minute=0) + timedelta(hours=1)


def _style(dialog: QWidget, hint: QLabel, background: str) -> None:
    """The dialog look, on the background the dial or rollers are drawn for."""
    scheme = theme.current()
    dialog.setStyleSheet(theme.dialog_qss() + f"QDialog {{ background: {background}; }}")
    hint.setStyleSheet(f"color: {scheme.hint_fg}; font-size: 12px;")
    hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
    hint.setWordWrap(True)


MENU_ICON_PX = 18


def menu_icon(colour: str, size: int = MENU_ICON_PX) -> QIcon:
    """Three short rounded lines, drawn sharp on high-density screens."""
    scale = 3
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(colour), 2 * scale)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    left, right = 3 * scale, (size - 3) * scale
    for y in (5, 9, 13):
        painter.drawLine(QPointF(left, y * scale), QPointF(right, y * scale))
    painter.end()
    pixmap.setDevicePixelRatio(scale)
    return QIcon(pixmap)


def _menu_qss() -> str:
    """The three-line button and its menu, in the active scheme."""
    c = theme.dialog_colors()
    return (
        "QToolButton#dialMenu {"
        f" background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 3px; }}"
        "QToolButton#dialMenu:hover, QToolButton#dialMenu:pressed, QToolButton#dialMenu[open=\"true\"] {"
        f" background: {c.button_hover}; border-color: {c.button_border}; }}"
        "QToolButton#dialMenu:focus {"
        f" border: 1px solid {c.focus}; }}"
        "QToolButton#dialMenu::menu-indicator { image: none; width: 0; }"
        "QMenu {"
        f" background: {c.field}; color: {c.text}; border: 1px solid {c.field_border};"
        " border-radius: 6px; padding: 4px; }"
        "QMenu::item { padding: 5px 18px 5px 26px; border-radius: 4px; }"
        "QMenu::item:selected {"
        f" background: {c.button_hover}; color: {c.button_hover_text}; }}"
        "QMenu::indicator { width: 14px; height: 14px; left: 6px; }"
        "QMenu::separator {"
        f" height: 1px; background: {c.field_border}; margin: 4px 6px; }}"
    )


# A date that can't be read: the field's edge and the line under it. Reads on all three schemes.
PROBLEM_COLOR = "#e0584f"


class _DateField(QLineEdit):
    """The written-out date under the dial. Esc undoes typing before it closes the window."""

    reverted = Signal()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape and self.isModified():
            self.reverted.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class DatePickerDialog(StayOnTopDialog):
    """Pick a date and time on the dial. Press the centre to choose it.

    Top left, a three-line menu: Show minutes shows or hides the minute ring
    (off, times land on the hour), and Now spins every ring to the current
    time. The
    written-out date under the dial can be typed over; Enter spins the dial
    to it.
    """

    minutes_toggled = Signal(bool)

    def __init__(
        self,
        when: datetime | None = None,
        parent: QWidget | None = None,
        *,
        show_minutes: bool = True,
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Choose date and time")
        self.setModal(True)
        self.resize(480, 620)
        self._now = now
        self._chosen: datetime | None = None
        when = when or next_quarter_hour(now())
        # A date with minutes keeps them: hiding the ring would move it to the hour.
        show_minutes = show_minutes or when.minute != 0
        self.dial = MetalDial(when, show_minutes=show_minutes, scheme=theme.current(), first_year=now().year)
        self.dial.selected.connect(self._choose)

        # The dial's settings, in a three-line menu top left.
        self.menu = QMenu(self)
        self.menu.setToolTipsVisible(True)
        self.minutes_action = QAction("Show minutes", self)
        self.minutes_action.setCheckable(True)
        self.minutes_action.setChecked(show_minutes)
        self.minutes_action.setToolTip("Show the minute ring. Off, times land on the hour.")
        self.minutes_action.toggled.connect(self._toggle_minutes)
        self.now_action = QAction("Now", self)
        self.now_action.setToolTip("Spin the dial to the current date and time")
        self.now_action.triggered.connect(self.spin_to_now)
        self.menu.addAction(self.minutes_action)
        self.menu.addSeparator()
        self.menu.addAction(self.now_action)
        self.menu.aboutToShow.connect(lambda: self._mark_menu_open(True))
        self.menu.aboutToHide.connect(lambda: self._mark_menu_open(False))

        self.menu_button = QToolButton(self)
        self.menu_button.setObjectName("dialMenu")
        self.menu_button.setToolTip("Dial settings: Show minutes, Now")
        self.menu_button.setAccessibleName("Dial settings")
        self.menu_button.setIcon(menu_icon(theme.dialog_colors().text))
        self.menu_button.setIconSize(QSize(MENU_ICON_PX, MENU_ICON_PX))
        self.menu_button.setMenu(self.menu)
        self.menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.menu_button.setCursor(Qt.CursorShape.PointingHandCursor)
        corner = QHBoxLayout()
        corner.setContentsMargins(0, 0, 0, 0)
        corner.addWidget(self.menu_button)
        corner.addStretch(1)

        # The full date the dial shows, kept up to date as the rings turn.
        # Type over it and press Enter to spin the dial there.
        self.readout = _DateField(format_full(self.dial.value()))
        self.readout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.readout.setToolTip(
            "Type a date and time, then press Enter.\n"
            "For example: 5 March 2027 18:05, 24/11/2026 9:30, or 14:45."
        )
        self.readout.editingFinished.connect(self._apply_typed)
        self.readout.reverted.connect(self._show_dial_value)
        self.readout.textEdited.connect(lambda _text: self._set_problem(""))
        self.dial.changed.connect(self._dial_changed)
        self.problem = QLabel("")
        self.problem.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.problem.setVisible(False)
        hint = QLabel(
            "Turn the rings, or type the date above, then press the centre to choose it."
        )
        layout = QVBoxLayout(self)
        layout.addLayout(corner)
        layout.addWidget(self.dial, 1)
        layout.addWidget(self.readout)
        layout.addWidget(self.problem)
        layout.addWidget(hint)
        _style(self, hint, self.dial.palette_.background.name())
        self.setStyleSheet(self.styleSheet() + _menu_qss())
        self._style_readout(error=False)
        self.dial.setFocus()

    @property
    def chosen(self) -> datetime | None:
        return self._chosen

    def spin_to_now(self) -> None:
        self._set_problem("")
        self.dial.spin_to(self._now().replace(second=0, microsecond=0))
        self.dial.setFocus()

    def type_date(self, text: str) -> None:
        """As if the user typed text under the dial and pressed Enter."""
        self.readout.setText(text)
        self.readout.setModified(True)
        self._apply_typed()

    # ------------------------------------------------------------ inside

    def _choose(self, when: datetime) -> None:
        self._chosen = when
        self.accept()

    def _mark_menu_open(self, open_: bool) -> None:
        # Keeps the button lit while its menu is down.
        self.menu_button.setProperty("open", "true" if open_ else "false")
        self.menu_button.style().polish(self.menu_button)

    def _toggle_minutes(self, shown: bool) -> None:
        self.dial.set_show_minutes(shown)
        self.minutes_toggled.emit(shown)

    def _dial_changed(self, when: datetime) -> None:
        # Leave text the user is typing alone until they press Enter.
        if not (self.readout.hasFocus() and self.readout.isModified()):
            self.readout.setText(format_full(when))

    def _show_dial_value(self) -> None:
        self._set_problem("")
        self.readout.setText(format_full(self.dial.value()))
        self.readout.setModified(False)

    def _apply_typed(self) -> None:
        if not self.readout.isModified():
            return
        self.readout.setModified(False)
        try:
            when = parse_when(self.readout.text(), self.dial.value())
        except ValueError as problem:
            self._set_problem(str(problem))
            return
        if not self.dial.can_show(when):
            first, last = self.dial.years[0], self.dial.years[-1]
            self._set_problem(f"Choose a year from {first} to {last}.")
            return
        if when.minute and not self.dial.show_minutes():
            self.minutes_action.setChecked(True)  # so the minutes typed are kept
        self._set_problem("")
        self.readout.setText(format_full(when))
        self.dial.spin_to(when)
        self.dial.setFocus()

    def _set_problem(self, text: str) -> None:
        self.problem.setText(text)
        self.problem.setVisible(bool(text))
        self._style_readout(error=bool(text))

    def _style_readout(self, *, error: bool) -> None:
        pal = self.dial.palette_
        colors = theme.dialog_colors()
        warn = PROBLEM_COLOR
        edge = warn if error else "transparent"
        self.readout.setStyleSheet(
            f"QLineEdit {{ color: {pal.accent.name()}; font-size: 20px; font-weight: 600;"
            f" background: transparent; border: 1px solid {edge}; border-radius: 6px; padding: 2px 6px; }}"
            f"QLineEdit:hover {{ border-color: {warn if error else colors.field_border}; }}"
            f"QLineEdit:focus {{ border-color: {warn if error else colors.focus}; background: {colors.field}; }}"
        )
        self.problem.setStyleSheet(f"color: {warn}; font-size: 12px;")


def entry_total(entry: ScheduleEntry) -> int:
    """The roller's single number for an entry's repeat."""
    parts = (entry.months, entry.weeks, entry.days, entry.hours, entry.minutes)
    return sum(value * place for value, place in zip(parts, PLACES, strict=True))


def apply_total(entry: ScheduleEntry, total: int) -> None:
    entry.months, entry.weeks, entry.days, entry.hours, entry.minutes = digits(total)


class IntervalPickerDialog(StayOnTopDialog):
    """Pick how often a date repeats on the rollers. The Select key chooses it."""

    def __init__(self, total: int = 0, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("How often it repeats")
        self.setModal(True)
        self.resize(640, 330)
        self._chosen: int | None = None
        self.roller = IntervalRoller(total, scheme=theme.current())
        self.roller.selected.connect(self._choose)
        hint = QLabel("Roll to how often it should run again, then press Select.")
        self.no_repeat = QPushButton("Don't repeat")
        self.no_repeat.setAutoDefault(False)
        self.no_repeat.clicked.connect(lambda: self._choose(0))
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.no_repeat)
        row.addStretch(1)
        layout = QVBoxLayout(self)
        layout.addWidget(self.roller, 1)
        layout.addWidget(hint)
        layout.addLayout(row)
        _style(self, hint, self.roller.palette_.background.name())
        self.roller.setFocus()

    @property
    def chosen(self) -> int | None:
        """The roller total chosen, 0 for Don't repeat, None when closed without choosing."""
        return self._chosen

    def _choose(self, total: int) -> None:
        self._chosen = total
        self.accept()

