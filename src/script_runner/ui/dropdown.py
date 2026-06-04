"""Animated dropdown panel containing the launcher buttons.

Shown below the trigger on hover. Handles its own mouse tracking so the list
stays visible while the mouse travels from the arrow into the list.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QEvent, QPropertyAnimation, QEasingCurve, QTimer, Signal, QPoint, QRect
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QScrollArea,
    QWidget as QW,
    QFrame,
    QLabel,
    QPushButton,
)

from ..config import AppConfig, Launcher
from .launch_button import LaunchButton


class DropdownPanel(QWidget):
    """The expanding list of launch buttons. Animated show/hide."""

    launch_requested = Signal(Launcher)  # emitted when a button is clicked
    manage_requested = Signal()  # open the full manager dialog
    hover_enter = Signal()
    hover_leave = Signal()

    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._buttons: list[LaunchButton] = []
        self._animation: QPropertyAnimation | None = None
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._do_hide)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            # Note: we intentionally allow focus for keyboard (Esc, arrows)
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

        # Main container frame for nice border/background
        self._frame = QFrame(self)
        self._frame.setFrameShape(QFrame.Shape.StyledPanel)
        self._frame.setFrameShadow(QFrame.Shadow.Raised)
        self._frame.setStyleSheet(
            """
            QFrame {
                background-color: rgba(35, 35, 38, 245);
                border: 1px solid rgba(80, 80, 85, 200);
                border-radius: 8px;
            }
            """
        )

        self._layout = QVBoxLayout(self._frame)
        self._layout.setContentsMargins(6, 6, 6, 6)
        self._layout.setSpacing(3)

        # Scroll area in case there are many items
        self._scroll = QScrollArea(self._frame)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { width: 6px; background: transparent; }"
            "QScrollBar::handle:vertical { background: rgba(120,120,125,160); border-radius: 3px; }"
        )

        self._button_container = QWidget()
        self._button_container.setStyleSheet("background: transparent;")
        self._button_layout = QVBoxLayout(self._button_container)
        self._button_layout.setContentsMargins(0, 0, 0, 0)
        self._button_layout.setSpacing(2)

        self._scroll.setWidget(self._button_container)
        self._layout.addWidget(self._scroll)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._frame)

        self.hide()  # start hidden
        self.setFixedWidth(config.settings.dropdown_width)

        self._hide_timer.setInterval(140)  # small grace period

    def set_width(self, width: int) -> None:
        self.setFixedWidth(width)

    def rebuild_buttons(self, launchers: list[Launcher]) -> None:
        """Replace all buttons with current enabled launchers."""
        # Clear
        for b in self._buttons:
            b.deleteLater()
        self._buttons.clear()

        for launcher in launchers:
            btn = LaunchButton(launcher, self._button_container)
            btn.clicked.connect(lambda checked=False, l=launcher: self._on_button_clicked(l))
            self._button_layout.addWidget(btn)
            self._buttons.append(btn)

        # Always add a "Manage..." entry at the bottom for discoverability
        if launchers:
            self._button_layout.addSpacing(6)
        manage_btn = QPushButton("Manage launchers...")
        manage_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #7aa2f7; border: none; padding: 4px; font-size: 11px; }"
            "QPushButton:hover { text-decoration: underline; }"
        )
        manage_btn.clicked.connect(self.manage_requested.emit)
        self._button_layout.addWidget(manage_btn)
        self._buttons.append(manage_btn)

        # Add a small hint at bottom if empty
        if not launchers:
            hint = QLabel("No launchers yet.\nRight-click the arrow → Add new launcher...")
            hint.setStyleSheet("color: #888; font-size: 11px; padding: 8px;")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._button_layout.addWidget(hint)
            self._buttons.append(hint)  # type: ignore  # for cleanup

        self._update_height_for_content()

    def _update_height_for_content(self) -> None:
        # Compute natural height based on children (cap at ~420)
        self._button_container.adjustSize()
        natural_h = self._button_container.sizeHint().height() + 12
        max_h = 420
        target_h = min(natural_h, max_h)
        self._frame.setFixedHeight(target_h)
        self.setFixedHeight(target_h)

    def _on_button_clicked(self, launcher: Launcher) -> None:
        self.launch_requested.emit(launcher)
        # Hide after a short delay so click feedback is visible
        QTimer.singleShot(80, self.start_hide_animation)

    def position_below(self, trigger: QWidget) -> None:
        """Position this panel directly below the trigger widget."""
        pos = trigger.mapToGlobal(QPoint(0, trigger.height()))
        # Slight horizontal centering or left-align
        x = pos.x() + (trigger.width() - self.width()) // 2
        self.move(x, pos.y())

    # --- Hover handling (combined area: trigger + this panel) ---
    def enterEvent(self, event: QEvent) -> None:  # type: ignore[override]
        self._cancel_hide()
        self.hover_enter.emit()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # type: ignore[override]
        self._schedule_hide()
        self.hover_leave.emit()
        super().leaveEvent(event)

    def _schedule_hide(self) -> None:
        self._hide_timer.start()

    def _cancel_hide(self) -> None:
        self._hide_timer.stop()

    def _do_hide(self) -> None:
        self.start_hide_animation()

    # --- Animations ---
    def start_show_animation(self) -> None:
        self._cancel_hide()
        self.show()
        self.raise_()
        self.setFocus(Qt.FocusReason.OtherFocusReason)  # allow Esc key

        start_h = 8
        end_h = self._frame.height()

        # We animate the height of the frame + opacity of whole widget
        self._frame.setFixedHeight(start_h)
        self.setWindowOpacity(0.0)

        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(self._config.settings.animation_duration_ms)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        height_anim = QPropertyAnimation(self._frame, b"minimumHeight", self)
        height_anim.setDuration(self._config.settings.animation_duration_ms)
        height_anim.setStartValue(start_h)
        height_anim.setEndValue(end_h)
        height_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Also set maximum so it doesn't grow during anim
        self._frame.setMaximumHeight(end_h)

        def on_finished():
            self._frame.setMinimumHeight(0)
            self._frame.setMaximumHeight(16777215)
            self._frame.setFixedHeight(end_h)
            self.setWindowOpacity(1.0)

        height_anim.finished.connect(on_finished)

        self._animation = anim  # keep ref
        anim.start()
        height_anim.start()

    def start_hide_animation(self) -> None:
        if not self.isVisible():
            return

        current_h = self._frame.height()
        start_op = self.windowOpacity()

        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(int(self._config.settings.animation_duration_ms * 0.7))
        anim.setStartValue(start_op)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.InCubic)

        height_anim = QPropertyAnimation(self._frame, b"minimumHeight", self)
        height_anim.setDuration(int(self._config.settings.animation_duration_ms * 0.75))
        height_anim.setStartValue(current_h)
        height_anim.setEndValue(6)
        height_anim.setEasingCurve(QEasingCurve.Type.InCubic)

        def on_finished():
            self.hide()
            self.setWindowOpacity(1.0)
            self._frame.setMinimumHeight(0)
            self._frame.setMaximumHeight(16777215)
            self._frame.setFixedHeight(self._frame.sizeHint().height() or 120)

        height_anim.finished.connect(on_finished)

        self._animation = anim
        anim.start()
        height_anim.start()

    def force_hide(self) -> None:
        """Immediate hide (used on launch or escape)."""
        self._cancel_hide()
        self.hide()
        self.setWindowOpacity(1.0)

    def keyPressEvent(self, event):  # type: ignore[override]
        if event.key() == Qt.Key.Key_Escape:
            self.force_hide()
            event.accept()
        else:
            super().keyPressEvent(event)
