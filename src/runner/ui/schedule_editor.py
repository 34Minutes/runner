"""The schedule area of the execute-group dialog: the dates a group runs on.

Each row is one date: the date itself (click to change it on the dial), how
often it repeats (click to change it on the rollers), and × to remove it.
The + button adds a date on the dial.

Rows are sorted by when each one next runs. A date added since the dialog
opened stays at the top instead, so it is in plain view; it takes its place
in the order the next time the dialog is opened. A date that ran once and is
over reads "done" and sorts last.

Turned off, the rows stay but are greyed out and + is hidden, so turning the
schedule back on brings the same dates back.
"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..config import ScheduleEntry
from ..schedule import describe_repeat, format_when, next_run
from . import theme
from .schedule_pickers import DatePickerDialog, IntervalPickerDialog, apply_total, entry_total, next_quarter_hour

ROW_HEIGHT = 34
VISIBLE_ROWS = 4

# One rounded look for every button in the area, greyed out with the schedule off.
_QSS = """
QPushButton { background: palette(button); border: 1px solid palette(mid);
              border-radius: 6px; padding: 4px 10px; }
QPushButton:hover { border-color: palette(highlight); }
QPushButton:disabled { color: palette(mid); border-color: palette(midlight); }
QPushButton#scheduleDate { text-align: left; }
QPushButton#scheduleDate[done="true"] { color: palette(mid); }
QPushButton#scheduleAdd { font-size: 16px; font-weight: 600; padding: 0; }
QLabel#scheduleNext { color: palette(highlight); font-weight: 600; }
QLabel#scheduleNext:disabled { color: palette(mid); }
"""


class ScheduleEditor(QWidget):
    changed = Signal()

    def __init__(
        self,
        entries: list[ScheduleEntry] | None = None,
        parent: QWidget | None = None,
        *,
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        super().__init__(parent)
        self._now = now
        self._entries: list[ScheduleEntry] = [deepcopy(entry) for entry in entries or []]
        self._new_ids: list[str] = []  # added since the dialog opened, newest first
        self._active = True
        # Tests swap these for fakes that answer without a window.
        self.pick_date: Callable[[datetime | None], datetime | None] = self._pick_date
        self.pick_interval: Callable[[int], int | None] = self._pick_interval

        title = QLabel("Schedule")
        title.setStyleSheet("font-weight: 600;")
        self.add_button = QPushButton("+")
        self.add_button.setObjectName("scheduleAdd")
        self.add_button.setToolTip("Add a date")
        self.add_button.setFixedSize(30, 26)
        self.add_button.clicked.connect(self.add_date)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.add_button)

        self._rows_host = QWidget()
        self._rows = QVBoxLayout(self._rows_host)
        self._rows.setContentsMargins(0, 0, 0, 0)
        self._rows.setSpacing(4)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.StyledPanel)
        scroll.setWidget(self._rows_host)
        scroll.setFixedHeight(VISIBLE_ROWS * (ROW_HEIGHT + 4) + 8)

        self.setStyleSheet(_QSS)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(header)
        layout.addWidget(scroll)
        self._rebuild()

    # ------------------------------------------------------------ public

    def entries(self) -> list[ScheduleEntry]:
        return [deepcopy(entry) for entry in self._entries]

    def set_active(self, active: bool) -> None:
        """Off: the dates are greyed out and + is hidden. They are kept."""
        self._active = active
        self.add_button.setVisible(active)
        self._rows_host.setEnabled(active)

    def is_active(self) -> bool:
        return self._active

    def ordered_ids(self) -> list[str]:
        return [entry.id for entry in self._ordered()]

    def row_texts(self) -> list[tuple[str, str]]:
        """(date, repeat) as each row shows them, top to bottom."""
        out = []
        for index in range(self._rows.count()):
            row = self._rows.itemAt(index).widget()
            if row is not None and row.property("entry_id"):
                out.append((row.property("date_text"), row.property("repeat_text")))
        return out

    def add_date(self) -> None:
        when = self.pick_date(None)
        if when is None:
            return
        entry = ScheduleEntry.new(when)
        self._entries.append(entry)
        self._new_ids.insert(0, entry.id)
        self._rebuild()
        self.changed.emit()

    def change_date(self, entry_id: str) -> None:
        entry = self._entry(entry_id)
        if entry is None:
            return
        when = self.pick_date(self._shown_date(entry))
        if when is None:
            return
        entry.start = ScheduleEntry.new(when).start
        self._rebuild()
        self.changed.emit()

    def change_repeat(self, entry_id: str) -> None:
        entry = self._entry(entry_id)
        if entry is None:
            return
        total = self.pick_interval(entry_total(entry))
        if total is None:
            return
        apply_total(entry, total)
        self._rebuild()
        self.changed.emit()

    def remove(self, entry_id: str) -> None:
        self._entries = [entry for entry in self._entries if entry.id != entry_id]
        if entry_id in self._new_ids:
            self._new_ids.remove(entry_id)
        self._rebuild()
        self.changed.emit()

    # ----------------------------------------------------------- pickers

    def _pick_date(self, when: datetime | None) -> datetime | None:
        dialog = DatePickerDialog(when or next_quarter_hour(self._now()), self.window())
        return dialog.chosen if dialog.exec() else None

    def _pick_interval(self, total: int) -> int | None:
        dialog = IntervalPickerDialog(total, self.window())
        return dialog.chosen if dialog.exec() else None

    # -------------------------------------------------------------- rows

    def _entry(self, entry_id: str) -> ScheduleEntry | None:
        return next((entry for entry in self._entries if entry.id == entry_id), None)

    def _next(self, entry: ScheduleEntry) -> datetime | None:
        return next_run(entry, self._now())

    def _shown_date(self, entry: ScheduleEntry) -> datetime:
        """The next run, or the date picked once it is over."""
        return self._next(entry) or entry.when

    def _ordered(self) -> list[ScheduleEntry]:
        fresh = [self._entry(entry_id) for entry_id in self._new_ids]
        fresh = [entry for entry in fresh if entry is not None]
        rest = [entry for entry in self._entries if entry.id not in self._new_ids]
        upcoming = sorted((e for e in rest if self._next(e) is not None), key=lambda e: self._next(e))
        done = sorted((e for e in rest if self._next(e) is None), key=lambda e: e.when)
        return fresh + upcoming + done

    def _soonest_id(self) -> str | None:
        upcoming = [(self._next(entry), entry.id) for entry in self._entries if self._next(entry)]
        return min(upcoming)[1] if upcoming else None

    def _rebuild(self) -> None:
        while self._rows.count():
            item = self._rows.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        soonest = self._soonest_id()
        for entry in self._ordered():
            self._rows.addWidget(self._row(entry, soonest == entry.id))
        if not self._entries:
            empty = QLabel("No dates yet. Press + to add one.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(f"color: {theme.current().hint_fg};")
            self._rows.addWidget(empty)
        self._rows.addStretch(1)

    def _row(self, entry: ScheduleEntry, soonest: bool) -> QWidget:
        row = QWidget()
        row.setProperty("entry_id", entry.id)
        upcoming = self._next(entry)
        date_text = format_when(self._shown_date(entry)) + ("" if upcoming else "  (done)")
        repeat_text = describe_repeat(entry)
        row.setProperty("date_text", date_text)
        row.setProperty("repeat_text", repeat_text)

        date_button = QPushButton(date_text)
        date_button.setObjectName("scheduleDate")
        date_button.setToolTip(
            f"Picked: {format_when(entry.when)}. Click to change the date." if entry.repeats
            else "Click to change the date."
        )
        date_button.setProperty("done", upcoming is None)
        date_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        date_button.clicked.connect(lambda _=False, eid=entry.id: self.change_date(eid))

        repeat_button = QPushButton(repeat_text)
        repeat_button.setObjectName("scheduleRepeat")
        repeat_button.setToolTip("Click to choose how often it repeats.")
        repeat_button.setMinimumWidth(190)
        repeat_button.clicked.connect(lambda _=False, eid=entry.id: self.change_repeat(eid))

        remove_button = QPushButton("×")
        remove_button.setObjectName("scheduleRemove")
        remove_button.setToolTip("Remove this date")
        remove_button.setFixedSize(28, 26)
        remove_button.clicked.connect(lambda _=False, eid=entry.id: self.remove(eid))

        layout = QHBoxLayout(row)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.addWidget(date_button, 1)
        if soonest:
            tag = QLabel("next")
            tag.setObjectName("scheduleNext")
            tag.setToolTip("This is the next time the group runs.")
            layout.addWidget(tag)
        layout.addWidget(repeat_button)
        layout.addWidget(remove_button)
        row.setFixedHeight(ROW_HEIGHT)
        return row
