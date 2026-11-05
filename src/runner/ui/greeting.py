"""Startup hint around the arrow.

The first launch on a machine uses the large default arrow. Every launch shows
a flashing yellow border plus a bubble with two lines: resize the arrow, then
drag it. Later launches reuse the saved size and position. Hovering or clicking
the arrow, resizing it, or clicking the bubble fades that hint out over about
a second. It stays gone until Runner is started again.
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPoint,
    QPointF,
    QRect,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
)
from PySide6.QtGui import QColor, QCursor, QFont, QFontMetrics, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QApplication, QWidget

from ..config import (
    DEFAULT_TRIGGER_HEIGHT,
    DEFAULT_TRIGGER_WIDTH,
    ConfigManager,
)

_FLASH_INTERVAL_MS = 450
_FADE_MS = 1000
_TAIL = 16
_GAP = 10
_PAD_X = 18
_PAD_Y = 12
_LINE_GAP = 4
GREETING_LINES = (
    "Resize arrow to preferred size",
    "Drag arrow to preferred location",
)
# Space outside the arrow for the greeting stroke. The arrow widget itself
# stays at the saved size; this frame is a separate window around it.
_BORDER_PAD = 8


def ensure_visible_trigger_size(cfg: ConfigManager, trigger: QWidget | None = None) -> None:
    """Raise a still-small saved arrow up to the default size, once.

    Later resizes are kept, including a size smaller than the default.
    """
    settings = cfg.config.settings
    if settings.applied_visible_trigger_size:
        return
    width = max(int(settings.trigger_width), DEFAULT_TRIGGER_WIDTH)
    height = max(int(settings.trigger_height), DEFAULT_TRIGGER_HEIGHT)
    cfg.update_settings(
        trigger_width=width,
        trigger_height=height,
        applied_visible_trigger_size=True,
    )
    if isinstance(trigger, QWidget):
        trigger.resize(width, height)


def clamp_trigger_to_screen(trigger: QWidget) -> bool:
    """Move a real trigger window fully inside the available screen.

    Returns True when the top-left changed. Non-widgets (test doubles) are ignored.
    """
    if not isinstance(trigger, QWidget):
        return False
    screen = trigger.screen() or QApplication.primaryScreen()
    if screen is None:
        return False
    avail = screen.availableGeometry()
    geo = trigger.frameGeometry()
    x, y = geo.x(), geo.y()
    if geo.width() <= avail.width():
        x = min(max(x, avail.left()), avail.right() - geo.width() + 1)
    else:
        x = avail.left()
    if geo.height() <= avail.height():
        y = min(max(y, avail.top()), avail.bottom() - geo.height() + 1)
    else:
        y = avail.top()
    if x == geo.x() and y == geo.y():
        return False
    trigger.move(x, y)
    return True


def greeting_bubble_rect(
    anchor: QRect,
    box: QSize,
    avail: QRect,
    tail: int = _TAIL,
    gap: int = _GAP,
) -> tuple[QRect, str]:
    """Place the bubble (including its tail) beside the arrow, fully on screen.

    The returned side is where the tail sits on the bubble: left, right, top, or bottom.
    """
    side = QSize(box.width() + tail, box.height())
    vertical = QSize(box.width(), box.height() + tail)
    candidates = (
        (QPoint(anchor.right() + 1 + gap, anchor.center().y() - side.height() // 2), "left", side),
        (QPoint(anchor.left() - gap - side.width(), anchor.center().y() - side.height() // 2), "right", side),
        (QPoint(anchor.center().x() - vertical.width() // 2, anchor.bottom() + 1 + gap), "top", vertical),
        (QPoint(anchor.center().x() - vertical.width() // 2, anchor.top() - gap - vertical.height()), "bottom", vertical),
    )
    for pos, tail_side, size in candidates:
        rect = QRect(pos, size)
        if _fits(rect, anchor, avail):
            return rect, tail_side
        clamped = _clamp_rect(rect, avail)
        if _fits(clamped, anchor, avail):
            return clamped, tail_side
    fallback_pos, fallback_side, fallback_size = candidates[1]
    return _clamp_rect(QRect(fallback_pos, fallback_size), avail), fallback_side


def bubble_box_size(font: QFont | None = None) -> QSize:
    """Bubble body for the two greeting lines, without the tail."""
    metrics = QFontMetrics(font or QFont())
    text_w = max(metrics.horizontalAdvance(line) for line in GREETING_LINES)
    line_h = metrics.height()
    text_h = line_h * len(GREETING_LINES) + _LINE_GAP * (len(GREETING_LINES) - 1)
    return QSize(text_w + _PAD_X * 2, text_h + _PAD_Y * 2)


def _paint_greeting_lines(painter: QPainter, box: QRect, font: QFont) -> None:
    """Draw the two first-run lines, dark on the yellow fill."""
    painter.setFont(font)
    painter.setPen(QColor(20, 20, 20))
    metrics = QFontMetrics(font)
    line_h = metrics.height()
    total = line_h * len(GREETING_LINES) + _LINE_GAP * (len(GREETING_LINES) - 1)
    y = box.top() + max(0, (box.height() - total) // 2)
    for line in GREETING_LINES:
        text_rect = QRect(box.left() + _PAD_X, y, box.width() - _PAD_X * 2, line_h)
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            line,
        )
        y += line_h + _LINE_GAP


def _fits(rect: QRect, anchor: QRect, avail: QRect) -> bool:
    if not avail.contains(rect):
        return False
    # A few pixels of clearance so the tail does not cover the arrow's resize edge.
    return not rect.intersects(anchor.adjusted(-4, -4, 4, 4))


def _clamp_rect(rect: QRect, avail: QRect) -> QRect:
    clamped = QRect(rect)
    if clamped.width() >= avail.width():
        clamped.moveLeft(avail.left())
    else:
        clamped.moveLeft(min(max(clamped.left(), avail.left()), avail.right() - clamped.width() + 1))
    if clamped.height() >= avail.height():
        clamped.moveTop(avail.top())
    else:
        clamped.moveTop(min(max(clamped.top(), avail.top()), avail.bottom() - clamped.height() + 1))
    return clamped


class GreetingBubble(QWidget):
    """Yellow speech bubble shown next to the arrow. Clicks dismiss it for this launch."""

    def __init__(self) -> None:
        super().__init__(None)
        self._tail_side = "left"
        self._flash_on = True
        self._opacity = 1.0
        self._on_dismiss = None
        self._box = bubble_box_size(self.font())
        self.setFixedSize(self._box.width() + _TAIL, self._box.height())
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_dismiss_handler(self, handler) -> None:
        self._on_dismiss = handler

    def set_flash_on(self, flash_on: bool) -> None:
        self._flash_on = flash_on
        self.update()

    def set_opacity(self, opacity: float) -> None:
        """Fade the whole bubble, including the text. 1 is solid, 0 is gone."""
        self._opacity = max(0.0, min(1.0, float(opacity)))
        self.update()

    def place_near(self, trigger: QWidget) -> None:
        screen = trigger.screen() or QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen is not None else QRect(0, 0, 1440, 900)
        self._box = bubble_box_size(self.font())
        rect, tail_side = greeting_bubble_rect(trigger.frameGeometry(), self._box, avail)
        self._tail_side = tail_side
        self.setFixedSize(rect.size())
        self.move(rect.topLeft())

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if self._on_dismiss is not None:
            self._on_dismiss()
        event.accept()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setOpacity(self._opacity)
        try:
            box, tip, base_a, base_b = self._bubble_geometry()
            border = QColor(255, 214, 0) if self._flash_on else QColor(230, 176, 0)
            pen_w = 4 if self._flash_on else 3
            fill = QColor(255, 241, 140)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, 60))
            painter.drawRoundedRect(box.adjusted(2, 3, 2, 3), 14, 14)

            painter.setPen(QPen(border, pen_w))
            painter.setBrush(fill)
            inset = pen_w // 2
            painter.drawRoundedRect(box.adjusted(inset, inset, -inset, -inset), 12, 12)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(fill)
            painter.drawPolygon(QPolygonF([tip, base_a, base_b]))

            _paint_greeting_lines(painter, box, self.font())
        finally:
            painter.end()

    def _bubble_geometry(self):
        full = self.rect()
        tail = _TAIL
        if self._tail_side == "left":
            box = full.adjusted(tail, 0, 0, 0)
            tip = QPointF(1, box.center().y())
            base_a = QPointF(tail + 2, box.center().y() - 10)
            base_b = QPointF(tail + 2, box.center().y() + 10)
        elif self._tail_side == "right":
            box = full.adjusted(0, 0, -tail, 0)
            tip = QPointF(full.right() - 1, box.center().y())
            base_a = QPointF(box.right() - 2, box.center().y() - 10)
            base_b = QPointF(box.right() - 2, box.center().y() + 10)
        elif self._tail_side == "top":
            box = full.adjusted(0, tail, 0, 0)
            tip = QPointF(box.center().x(), 1)
            base_a = QPointF(box.center().x() - 10, tail + 2)
            base_b = QPointF(box.center().x() + 10, tail + 2)
        else:
            box = full.adjusted(0, 0, 0, -tail)
            tip = QPointF(box.center().x(), full.bottom() - 1)
            base_a = QPointF(box.center().x() - 10, box.bottom() - 2)
            base_b = QPointF(box.center().x() + 10, box.bottom() - 2)
        return box, tip, base_a, base_b


class GreetingBorder(QWidget):
    """Yellow rim drawn around the arrow, not on top of it, so the arrow keeps its size."""

    def __init__(self) -> None:
        super().__init__(None)
        self._flash_on = True
        self._opacity = 1.0
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def set_flash_on(self, flash_on: bool) -> None:
        self._flash_on = flash_on
        self.update()

    def set_opacity(self, opacity: float) -> None:
        self._opacity = max(0.0, min(1.0, float(opacity)))
        self.update()

    def place_around(self, trigger: QWidget) -> None:
        pad = _BORDER_PAD
        geo = trigger.frameGeometry()
        self.setFixedSize(geo.width() + pad * 2, geo.height() + pad * 2)
        self.move(geo.x() - pad, geo.y() - pad)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        if self._opacity <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setOpacity(self._opacity)
        if self._flash_on:
            color = QColor(255, 230, 0)
            pen_w = 6
        else:
            color = QColor(255, 196, 0)
            pen_w = 4
        inset = pen_w // 2
        painter.setBrush(Qt.BrushStyle.NoBrush)
        pen = QPen(color, pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawRoundedRect(self.rect().adjusted(inset, inset, -inset, -inset), 10, 10)
        painter.end()


class StartupGreeting(QObject):
    """Flashing border plus bubble. Fades out for the rest of this launch after a hover or click."""

    def __init__(self, parent: QObject | None = None, *, show_bubble: bool = True) -> None:
        super().__init__(parent)
        self._bubble = GreetingBubble()
        self._bubble.set_dismiss_handler(self.dismiss_for_session)
        self._border = GreetingBorder()
        self._trigger: QWidget | None = None
        self._dismissed = False
        self._show_bubble = show_bubble
        self._flash_on = True
        self._timer = QTimer(self)
        self._timer.setInterval(_FLASH_INTERVAL_MS)
        self._timer.timeout.connect(self._on_flash)
        self._fade = QVariantAnimation(self)
        self._fade.setDuration(_FADE_MS)
        self._fade.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._fade.valueChanged.connect(self._on_fade_value)
        self._fade.finished.connect(self._finish_fade)

    @property
    def bubble(self) -> GreetingBubble:
        return self._bubble

    @property
    def border(self) -> GreetingBorder:
        return self._border

    @property
    def dismissed(self) -> bool:
        return self._dismissed

    def present(self, trigger: QWidget, *, show_bubble: bool | None = None) -> None:
        """Show the hint around trigger. Does nothing after it was dismissed this launch.

        The bubble is shown on every launch. show_bubble False keeps the flashing
        border and leaves the bubble hidden.
        """
        if show_bubble is not None:
            self._show_bubble = show_bubble
        if self._dismissed or not isinstance(trigger, QWidget):
            return
        self._attach(trigger)
        # The pointer is already on the arrow, so this launch has been noticed.
        if trigger.isVisible() and trigger.rect().contains(trigger.mapFromGlobal(QCursor.pos())):
            self.dismiss_for_session()
            return
        self._flash_on = True
        trigger.set_greeting_highlight(True, True, 1.0)
        self._border.set_opacity(1.0)
        self._border.set_flash_on(True)
        self._border.place_around(trigger)
        self._border.show()
        if self._show_bubble:
            self._bubble.set_opacity(1.0)
            self._bubble.set_flash_on(True)
            self._bubble.place_near(trigger)
            self._bubble.show()
        else:
            self._bubble.hide()
        self._border.stackUnder(trigger)
        trigger.raise_()
        if not self._timer.isActive():
            self._timer.start()

    def show_again(self, trigger: QWidget) -> None:
        """Used when the edit-screen switch is turned back on during this launch."""
        self._fade.stop()
        self._dismissed = False
        self._bubble.set_opacity(1.0)
        self.present(trigger)

    def dismiss_for_session(self) -> None:
        """Fade the hint out, then keep it hidden until Runner is started again."""
        if self._dismissed:
            return
        self._dismissed = True
        self._timer.stop()
        if not self._hint_is_showing():
            self._finish_fade()
            return
        # Hold the bright frame and fade that, instead of flashing while it leaves.
        self._flash_on = True
        self._bubble.set_flash_on(True)
        if self._trigger is not None:
            self._trigger.set_greeting_highlight(True, True, 1.0)
        self._fade.stop()
        self._fade.setStartValue(1.0)
        self._fade.setEndValue(0.0)
        self._fade.start()

    def shutdown(self) -> None:
        self._fade.stop()
        self._timer.stop()
        self._detach()
        self._bubble.hide()
        self._bubble.deleteLater()
        self._border.hide()
        self._border.deleteLater()

    def _hint_is_showing(self) -> bool:
        try:
            bubble_visible = self._bubble.isVisible()
        except RuntimeError:
            bubble_visible = False
        highlighted = self._trigger is not None and getattr(self._trigger, "_greeting_highlight", False)
        return bubble_visible or highlighted

    def _on_fade_value(self, value) -> None:
        if self._fade.state() != QVariantAnimation.State.Running:
            return
        opacity = float(value)
        try:
            self._bubble.set_opacity(opacity)
        except RuntimeError:
            return
        try:
            self._border.set_opacity(opacity)
        except RuntimeError:
            return
        if self._trigger is not None:
            self._trigger.set_greeting_highlight(True, True, opacity)

    def _finish_fade(self) -> None:
        # stop() can emit finished on some Qt builds. Ignore that re-entry.
        if getattr(self, "_finishing_fade", False):
            return
        self._finishing_fade = True
        try:
            self._fade.stop()
            try:
                self._bubble.hide()
                self._bubble.set_opacity(1.0)
            except RuntimeError:
                pass
            try:
                self._border.hide()
                self._border.set_opacity(1.0)
            except RuntimeError:
                pass
            if self._trigger is not None:
                self._trigger.set_greeting_highlight(False, False)
        finally:
            self._finishing_fade = False

    def eventFilter(self, obj, event) -> bool:  # type: ignore[override]
        trigger = self._trigger
        bubble = self._bubble
        if obj is not trigger or bubble is None or self._dismissed:
            return False
        try:
            visible = bubble.isVisible()
        except RuntimeError:
            return False
        kind = event.type()
        # Border-only launches still dismiss when the pointer reaches the arrow.
        if kind in (
            QEvent.Type.Enter,
            QEvent.Type.HoverEnter,
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonDblClick,
        ):
            self.dismiss_for_session()
            return False
        if kind == QEvent.Type.MouseMove and trigger.rect().contains(event.position().toPoint()):
            self.dismiss_for_session()
            return False
        if kind in (QEvent.Type.Move, QEvent.Type.Resize):
            self._border.place_around(trigger)
            if visible:
                bubble.place_near(trigger)
        elif kind == QEvent.Type.Hide:
            self._border.hide()
            if visible:
                bubble.hide()
        return False

    def _attach(self, trigger: QWidget) -> None:
        if self._trigger is trigger:
            return
        self._detach()
        self._trigger = trigger
        trigger.installEventFilter(self)

    def _detach(self) -> None:
        if self._trigger is not None:
            self._trigger.removeEventFilter(self)
            self._trigger = None

    def _on_flash(self) -> None:
        self._flash_on = not self._flash_on
        self._bubble.set_flash_on(self._flash_on)
        self._border.set_flash_on(self._flash_on)
        if self._trigger is not None and not self._dismissed:
            self._trigger.set_greeting_highlight(True, self._flash_on)
