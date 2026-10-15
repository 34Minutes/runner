"""A simple sliding toggle switch widget for PySide6 (Qt Widgets).

Replaces QCheckBox for on/off settings with a modern switch look + slide animation.
"""

from PySide6.QtCore import Property, QPropertyAnimation, QEasingCurve, Qt, QSize, QRect
from PySide6.QtGui import QPainter, QColor, QPen, QPalette
from PySide6.QtWidgets import QAbstractButton


class ToggleSwitch(QAbstractButton):
    """Sliding on/off toggle switch.

    API is similar to QCheckBox for the parts we use:
      - setChecked(bool), isChecked()
      - toggled signal
      - setText(str)  (text appears to the right of the switch)
    """

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)

        # Visual metrics (easy to tweak) — made more compact for menus
        self._track_width = 32
        self._track_height = 16
        self._knob_diameter = 12
        self._track_margin = 2

        # Animation state: current left offset of the knob inside the track
        self._knob_offset = self._track_margin

        self._animation = QPropertyAnimation(self, b"knob_offset", self)
        self._animation.setDuration(130)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutQuad)

        self.toggled.connect(self._on_toggled)

        # Make sure we have reasonable size for layout (compact by default)
        h = max(self._track_height + 4, 22)
        self.setFixedHeight(h)

    def sizeHint(self) -> QSize:
        fm = self.fontMetrics()
        text_w = fm.horizontalAdvance(self.text()) + 10 if self.text() else 0
        h = max(self._track_height + 4, fm.height() + 4)
        return QSize(self._track_width + text_w + 8, h)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def hitButton(self, pos) -> bool:
        # Whole widget (switch + text) is clickable
        return self.rect().contains(pos)

    # --- animation property ---
    def _get_knob_offset(self) -> int:
        return self._knob_offset

    def _set_knob_offset(self, value: int):
        self._knob_offset = value
        self.update()

    knob_offset = Property(int, _get_knob_offset, _set_knob_offset)

    def _on_toggled(self, checked: bool):
        self._animation.stop()
        if checked:
            end = self._track_width - self._knob_diameter - self._track_margin
        else:
            end = self._track_margin
        self._animation.setEndValue(end)
        self._animation.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        try:
            # Colors matching the app's dark theme
            if self.isChecked():
                track_color = QColor(70, 110, 170)  # accent blue from hover
                track_border = QColor(90, 130, 190)
            else:
                track_color = QColor(70, 70, 75)
                track_border = QColor(95, 95, 100)

            knob_color = QColor(245, 245, 247)

            # Track (rounded pill)
            track_rect = QRect(
                0,
                (self.height() - self._track_height) // 2,
                self._track_width,
                self._track_height,
            )
            painter.setPen(QPen(track_border, 1))
            painter.setBrush(track_color)
            painter.drawRoundedRect(track_rect, self._track_height / 2, self._track_height / 2)

            # Knob (circle that slides)
            knob_x = track_rect.left() + self._knob_offset
            knob_y = track_rect.top() + self._track_margin
            knob_rect = QRect(knob_x, knob_y, self._knob_diameter, self._knob_diameter)

            painter.setPen(Qt.NoPen)
            painter.setBrush(knob_color)
            painter.drawEllipse(knob_rect)

            # Optional subtle inner ring on knob for polish
            painter.setPen(QPen(QColor(200, 200, 205, 120), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(knob_rect.adjusted(2, 2, -2, -2))

            # Text to the right of the switch
            if self.text():
                text_rect = QRect(
                    self._track_width + 8,
                    0,
                    self.width() - self._track_width - 8,
                    self.height(),
                )
                text_color = self.palette().color(QPalette.ColorRole.Text)
                painter.setPen(text_color)
                painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, self.text())
        finally:
            painter.end()  # ensure we don't leave an active painter (prevents backingstore/painter state crashes)

    def setChecked(self, checked: bool):
        super().setChecked(checked)
        # Snap the knob to the correct position without anim when set programmatically
        if checked:
            self._knob_offset = self._track_width - self._knob_diameter - self._track_margin
        else:
            self._knob_offset = self._track_margin
        self.update()

    # Convenience so existing .isChecked() / toggled usage keeps working exactly
    # (QAbstractButton already provides isChecked, toggled, etc.)