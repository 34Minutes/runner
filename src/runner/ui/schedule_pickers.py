"""The two pickers a schedule uses, each in its own small window.

DatePickerDialog holds the metal dial: pressing its silver centre, or Enter,
chooses the date. IntervalPickerDialog holds the interval rollers: the Select
key chooses how often it repeats, and Don't repeat clears it. Both follow the
active colour scheme. Esc closes either one without changing anything.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..config import ScheduleEntry
from . import theme
from .date_dial import MetalDial
from .interval_roller import PLACES, IntervalRoller, digits
from .stay_on_top import StayOnTopDialog


def next_quarter_hour(now: datetime | None = None) -> datetime:
    """A sensible first date for a new schedule: the next quarter hour from now."""
    now = (now or datetime.now()).replace(second=0, microsecond=0)
    return now + timedelta(minutes=15 - now.minute % 15)


def _style(dialog: QWidget, hint: QLabel, background: str) -> None:
    scheme = theme.current()
    dialog.setStyleSheet(
        f"QDialog {{ background: {background}; }}"
        f"QPushButton {{ background: {scheme.row_bg}; color: {scheme.row_fg};"
        f" border: 1px solid {scheme.row_border}; border-radius: 4px; padding: 4px 12px; }}"
        f"QPushButton:hover {{ background: {scheme.hover_bg}; color: {scheme.hover_fg}; }}"
    )
    hint.setStyleSheet(f"color: {scheme.hint_fg}; font-size: 12px;")
    hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
    hint.setWordWrap(True)


class DatePickerDialog(StayOnTopDialog):
    """Pick a date and time on the dial. Press the centre to choose it."""

    def __init__(self, when: datetime | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Choose date and time")
        self.setModal(True)
        self.resize(480, 540)
        self._chosen: datetime | None = None
        self.dial = MetalDial(when or next_quarter_hour(), scheme=theme.current())
        self.dial.selected.connect(self._choose)
        hint = QLabel("Turn the rings to the date and time, then press the centre to choose it.")
        layout = QVBoxLayout(self)
        layout.addWidget(self.dial, 1)
        layout.addWidget(hint)
        _style(self, hint, self.dial.palette_.background.name())
        self.dial.setFocus()

    @property
    def chosen(self) -> datetime | None:
        return self._chosen

    def _choose(self, when: datetime) -> None:
        self._chosen = when
        self.accept()


def entry_total(entry: ScheduleEntry) -> int:
    """The roller's single number for an entry's repeat."""
    parts = (entry.months, entry.weeks, entry.days, entry.hours, entry.minutes)
    return sum(value * place for value, place in zip(parts, PLACES))


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

