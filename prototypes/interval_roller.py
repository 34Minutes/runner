"""Interval picker: five number rollers, like an odometer, in Runner's schemes.

Left to right: months, weeks, days, hours, minutes. Each roller turns on its
own, and rolling past the end carries into the roller on its left, the way
time does: 60 minutes make an hour, 24 hours a day, 7 days a week, and
4 weeks roll into a month. Rolling below zero borrows from the left; the
interval never goes below zero or above 99 months.

Drag a roller (flick it to coast), scroll over it, or click above or below
the middle. Left/Right picks a roller, Up/Down steps it. The Select key on
the right, a drum-sized key in the same metal, presses in to select the
interval; Enter or Space does the same. It is off while the interval is zero.

Run from the Runner repo (it reads src/runner/ui/theme.py):
    .venv/bin/python prototypes/interval_roller.py             demo window
    .venv/bin/python prototypes/interval_roller.py --shot DIR  screenshots of each look
"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from runner.ui import theme
from runner.ui.date_dial import _rgb
from runner.ui.interval_roller import PLACES, IntervalRoller, describe

# ---------- demo window ----------
class Demo(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Interval Roller")
        self.resize(640, 460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        self.picker = IntervalRoller(60)
        self.picker.changed.connect(self._show)
        layout.addWidget(self.picker, 1)

        self.readout = QLabel()
        self.readout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.readout)

        self.picker.selected.connect(self._selected)

        self.hint = QLabel("Drag or flick a roller  ·  scroll over it  ·  ←→ pick a roller, ↑↓ step"
                           "  ·  press Select or Enter")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.hint)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.scheme = QComboBox()
        for s in theme.SCHEMES:
            self.scheme.addItem(s.label, s.id)
        self.scheme.currentIndexChanged.connect(self._apply_scheme)
        bottom.addWidget(self.scheme)
        bottom.addStretch(1)
        layout.addLayout(bottom)

        self._apply_scheme()
        self._show(self.picker.total())
        self.picker.setFocus()

    def _apply_scheme(self):
        scheme = theme.resolve(self.scheme.currentData())
        self.picker.set_scheme(scheme)
        pal = self.picker.palette_
        self.setStyleSheet(
            f"QWidget {{ background: {pal.background.name()}; color: {_rgb(scheme.row_fg).name()}; }}"
            f"QComboBox, QPushButton {{ background: {_rgb(scheme.row_bg).name()};"
            f" border: 1px solid {_rgb(scheme.row_border).name()}; border-radius: 4px; padding: 4px 12px; }}"
        )
        self.readout.setStyleSheet(f"font-size: 20px; font-weight: 600; color: {pal.accent.name()};")
        self.hint.setStyleSheet(f"color: {pal.hint.name()}; font-size: 12px;")

    def _show(self, total: int):
        self.readout.setText(describe(total))

    def _selected(self, _total: int):
        print("Selected:", self.picker.values(), "-", describe(self.picker.total()), flush=True)
        self.hint.setText("Selected: " + describe(self.picker.total()))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Demo()
    if len(sys.argv) > 2 and sys.argv[1] == "--shot":
        w.show()
        w.picker.set_total(1 * PLACES[0] + 2 * PLACES[1] + 3 * PLACES[2] + 7 * PLACES[3] + 30, animate=False)
        w.picker.rollers[4].pos += 0.3  # caught mid-turn
        w.picker.rollers[3].lift = 1.0  # one held up, as while dragging
        for i, s in enumerate(theme.SCHEMES):
            w.scheme.setCurrentIndex(i)
            app.processEvents()
            w.grab().save(os.path.join(sys.argv[2], f"roller_{s.id}.png"))
        sys.exit(0)
    w.show()
    w.raise_()
    w.activateWindow()
    sys.exit(app.exec())
