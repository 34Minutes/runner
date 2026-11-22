"""Nested date-time dial in brushed metal, coloured from Runner's schemes.

Outside to inside: year, month, day, hour (24 h), and minute (optional).
A fixed window at the top reads the selected value on every ring. Drag a ring
to spin it: it rises out of the dial while held and settles back on release.
Scroll over a ring to step it; Up/Down picks a ring, Left/Right steps it.
Click the silver centre, or press Enter or Space, to select the date.

Run from the Runner repo (it reads src/runner/ui/theme.py):
    .venv/bin/python prototypes/metal_dial.py             demo window
    .venv/bin/python prototypes/metal_dial.py --shot DIR  screenshots of each look
"""

from __future__ import annotations

import datetime as dt
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from runner.ui import theme
from runner.ui.date_dial import MetalDial, _rgb

# ---------- demo window ----------
class Demo(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Metal Date Dial")
        self.resize(560, 720)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)

        self.dial = MetalDial()
        self.dial.changed.connect(self._show)
        layout.addWidget(self.dial, 1)

        self.readout = QLabel()
        self.readout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.readout)

        self.picked = QLabel("Click the centre to select")
        self.picked.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dial.selected.connect(self._picked)
        layout.addWidget(self.picked)

        self.hint = QLabel("Drag a ring to spin it  ·  scroll over a ring to step  ·  ↑↓ pick a ring, ←→ step"
                           "  ·  click the centre or press Enter to select")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.hint)

        row = QHBoxLayout()
        row.addStretch(1)
        self.scheme = QComboBox()
        for s in theme.SCHEMES:
            self.scheme.addItem(s.label, s.id)
        self.scheme.currentIndexChanged.connect(self._apply_scheme)
        row.addWidget(self.scheme)
        self.minutes = QCheckBox("Show minutes")
        self.minutes.setChecked(True)
        self.minutes.toggled.connect(self.dial.set_show_minutes)
        row.addWidget(self.minutes)
        self.now = QPushButton("Now")
        self.now.clicked.connect(lambda: self.dial.spin_to(dt.datetime.now()))
        row.addWidget(self.now)
        row.addStretch(1)
        layout.addLayout(row)

        self._apply_scheme()
        self.dial.setFocus()

    def _apply_scheme(self):
        scheme = theme.resolve(self.scheme.currentData())
        self.dial.set_scheme(scheme)
        pal = self.dial.palette_
        self.setStyleSheet(
            f"QWidget {{ background: {pal.background.name()}; color: {_rgb(scheme.row_fg).name()}; }}"
            f"QComboBox, QPushButton {{ background: {_rgb(scheme.row_bg).name()};"
            f" border: 1px solid {_rgb(scheme.row_border).name()}; border-radius: 4px; padding: 4px 12px; }}"
        )
        self.readout.setStyleSheet(f"font-size: 24px; font-weight: 600; color: {pal.accent.name()};")
        self.hint.setStyleSheet(f"color: {pal.hint.name()}; font-size: 12px;")
        self.picked.setStyleSheet(f"color: {pal.hint.name()}; font-size: 13px;")

    def _picked(self, when: dt.datetime):
        minutes = when.strftime("%H:%M") if self.dial.show_minutes() else when.strftime("%H:00")
        self.picked.setText(f"Selected  {when.strftime('%A %-d %B %Y')}  ·  {minutes}")
        self.picked.setStyleSheet(f"color: {self.dial.palette_.accent.name()}; font-size: 13px; font-weight: 600;")

    def _show(self, when: dt.datetime):
        if self.dial.show_minutes():
            self.readout.setText(when.strftime("%A %-d %B %Y  ·  %H:%M"))
        else:
            self.readout.setText(when.strftime("%A %-d %B %Y  ·  %H:00"))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Demo()
    w._show(w.dial.value())
    if len(sys.argv) > 2 and sys.argv[1] == "--shot":
        import os

        w.show()
        for i, s in enumerate(theme.SCHEMES):
            w.scheme.setCurrentIndex(i)
            for minutes in (True, False):
                w.minutes.setChecked(minutes)
                w.dial.month.lift = 1.0 if (s.id == "dark" and minutes) else 0.0
                app.processEvents()
                w.grab().save(os.path.join(sys.argv[2], f"metal_{s.id}_{'min' if minutes else 'hr'}.png"))
        sys.exit(0)
    w.show()
    w.raise_()
    w.activateWindow()
    sys.exit(app.exec())
