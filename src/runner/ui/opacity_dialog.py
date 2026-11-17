"""A slider for the opacity of the arrow's rounded box."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget

from ..config import AppConfig
from .stay_on_top import StayOnTopDialog
from .theme import current, opacity_percent


class OpacityDialog(StayOnTopDialog):
    """Modeless panel. Moving a rule applies that opacity immediately."""

    def __init__(
        self,
        config: AppConfig,
        on_change: Callable[[int], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("opacityDialog")
        self.setWindowTitle("Opacity")
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._on_change = on_change
        settings = config.settings
        scheme = current()
        self._box_percent = int(getattr(settings, "box_opacity", -1))

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(12)
        root.addWidget(self._rule(
            "Box",
            "boxOpacity",
            opacity_percent(scheme.trigger_fill, self._box_percent),
        ))
        self.setMinimumWidth(280)

    def _rule(self, title: str, object_name: str, shown: int) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        label = QLabel(title)
        label.setMinimumWidth(48)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setObjectName(object_name)
        slider.setRange(0, 100)
        slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        slider.setTickInterval(25)
        slider.setSingleStep(1)
        slider.setPageStep(10)
        slider.setMinimumWidth(160)
        readout = QLabel(f"{shown}%")
        readout.setObjectName(object_name + "Readout")
        readout.setMinimumWidth(40)
        readout.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        slider.blockSignals(True)
        slider.setValue(shown)
        slider.blockSignals(False)
        slider.valueChanged.connect(
            lambda value, caption=readout: self._on_slider(value, caption)
        )

        layout.addWidget(label)
        layout.addWidget(slider, 1)
        layout.addWidget(readout)
        return row

    def _on_slider(self, value: int, caption: QLabel) -> None:
        caption.setText(f"{value}%")
        self._box_percent = value
        # -1 keeps the scheme alpha until this slider actually moves.
        self._on_change(self._box_percent)

    def sync_from_scheme(self) -> None:
        """A slider still on the scheme alpha shows that scheme. A chosen percent stays."""
        if self._box_percent < 0:
            self._show_rule("boxOpacity", opacity_percent(current().trigger_fill, -1))

    def _show_rule(self, object_name: str, shown: int) -> None:
        slider = self.findChild(QSlider, object_name)
        readout = self.findChild(QLabel, object_name + "Readout")
        if slider is None or readout is None:
            return
        slider.blockSignals(True)
        slider.setValue(shown)
        slider.blockSignals(False)
        readout.setText(f"{shown}%")
