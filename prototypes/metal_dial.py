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

import calendar
import datetime as dt
import math
import random
import sys
from dataclasses import dataclass

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
    QStaticText,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from runner.ui import theme

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ---------- colours ----------
def _rgb(text: str) -> QColor:
    """'rgba(1, 2, 3, 200)' or '#abc' from theme.py, as an opaque QColor."""
    if text.startswith("rgb"):
        parts = [int(float(v)) for v in text[text.index("(") + 1 : -1].split(",")[:3]]
        return QColor(*parts)
    return QColor(text)


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
    )


@dataclass(frozen=True)
class DialPalette:
    metal: QColor  # the ring metal's own colour
    shine: QColor  # where it catches the light
    shadow: QColor  # where it faces away
    text: QColor
    text_relief: QColor  # the engraving's lit or shaded edge
    tick: QColor
    accent: QColor  # selected values and the index mark
    background: QColor
    hint: QColor


def palette_for(scheme: theme.ColorScheme) -> DialPalette:
    """The dial's metal for one of Runner's colour schemes."""
    bg = _rgb(scheme.frame_bg)
    if scheme.id == "bright":  # polished brass, engraved dark
        return DialPalette(
            metal=QColor(196, 150, 78), shine=QColor(255, 242, 206), shadow=QColor(104, 68, 22),
            text=_rgb(scheme.row_fg), text_relief=QColor(255, 240, 205, 170),
            tick=QColor(92, 60, 24), accent=QColor(140, 40, 8),
            background=bg, hint=_rgb(scheme.hint_fg),
        )
    if scheme.id == "medium":  # satin titanium, gold accent
        return DialPalette(
            metal=QColor(104, 110, 126), shine=QColor(226, 230, 238), shadow=QColor(44, 47, 56),
            text=_rgb(scheme.row_fg), text_relief=QColor(0, 0, 0, 150),
            tick=QColor(200, 204, 214), accent=_rgb(scheme.drag_border).lighter(112),
            background=bg, hint=_rgb(scheme.hint_fg),
        )
    return DialPalette(  # dark: gunmetal steel, blue accent
        metal=QColor(60, 63, 70), shine=QColor(196, 202, 214), shadow=QColor(16, 17, 20),
        text=_rgb(scheme.row_fg), text_relief=QColor(0, 0, 0, 190),
        tick=QColor(150, 156, 168), accent=_rgb(scheme.selected_border).lighter(115),
        background=bg, hint=_rgb(scheme.hint_fg),
    )


def brushed(c: QPointF, metal: QColor, shine: QColor, shadow: QColor, strength: float = 1.0,
            light_deg: float = 125.0) -> QConicalGradient:
    """Circular brushed metal: two bright lobes facing the light, two dark ones across."""
    g = QConicalGradient(c, 0)
    lo = _mix(shadow, metal, 0.35)
    for k in range(49):
        a = k / 48 * 360.0
        f = (0.5 + 0.5 * math.cos(math.radians(2 * (a - light_deg)))) ** 2.4
        f = 0.5 + (f - 0.5) * strength
        col = _mix(lo, metal, f * 2) if f < 0.5 else _mix(metal, shine, (f - 0.5) * 2 * 0.85)
        g.setColorAt(k / 48, col)
    return g


# ---------- rings ----------
class Ring:
    """One rotating ring: its items and its motion. The widget paints it."""

    FRICTION = 2.4
    COAST_MIN = 30.0
    SPRING = 16.0

    def __init__(self, name, items, label_every, tone, seed):
        self.name = name
        self.items = list(items)
        self.label_every = label_every
        self.tone = tone  # rings alternate slightly lighter and darker
        self.r_out = self.r_in = 0.0  # fractions of the dial radius, set by layout
        self.rotation = 0.0
        self.velocity = 0.0
        self.target: float | None = None
        self.index = 0
        self.spring = self.SPRING
        self.lift = 0.0  # 0 resting in the dial, 1 raised while held
        self.lift_target = 0.0
        rnd = random.Random(seed)  # the brushing pattern, fixed per ring
        self.grain = [(rnd.random(), rnd.random() < 0.5, rnd.uniform(6, 26)) for _ in range(40)]

    @property
    def step(self) -> float:
        return 360.0 / len(self.items)

    def index_at(self, rotation: float) -> int:
        return round(-rotation / self.step) % len(self.items)

    def rotation_for(self, index: int) -> float:
        base = -index * self.step
        return base + 360.0 * round((self.rotation - base) / 360.0)

    def jump_to(self, index: int):
        self.index = index % len(self.items)
        self.rotation = self.rotation_for(self.index)
        self.velocity, self.target = 0.0, None

    def step_by(self, n: int):
        base = self.target if self.target is not None else self.rotation_for(self.index)
        self.target = base - n * self.step
        self.velocity = 0.0

    def moving(self) -> bool:
        return self.target is not None or self.velocity != 0.0

    def tick(self, dt_s: float):
        if self.target is None and abs(self.velocity) > self.COAST_MIN:
            self.rotation += self.velocity * dt_s
            self.velocity *= math.exp(-self.FRICTION * dt_s)
            return
        if self.target is None:
            self.target = self.rotation_for(self.index_at(self.rotation))
        diff = self.target - self.rotation
        if abs(diff) < 0.05:
            self.rotation, self.target, self.velocity = self.target, None, 0.0
            self.spring = self.SPRING
        else:
            self.rotation += diff * min(1.0, dt_s * self.spring)


class MetalDial(QWidget):
    changed = Signal(object)  # datetime.datetime
    selected = Signal(object)  # datetime.datetime, when the centre is clicked

    OUTER, HUB = 0.95, 0.25  # ring area and centre knob, as fractions of the dial radius
    LIFT_SCALE = 0.05
    LIFT_SHADOW = 0.045
    LIFT_SPEED = 11.0

    def __init__(self, when: dt.datetime | None = None, *, show_minutes=True,
                 scheme: theme.ColorScheme = theme.DARK, parent=None):
        super().__init__(parent)
        when = when or dt.datetime.now()
        self.years = list(range(when.year, when.year + 12))
        self.year = Ring("Year", [str(y) for y in self.years], 1, 0, 1)
        self.month = Ring("Month", MONTHS, 1, 1, 2)
        self.day = Ring("Day", [str(d) for d in range(1, 32)], 1, 0, 3)
        self.hour = Ring("Hour", [f"{h:02d}" for h in range(24)], 1, 1, 4)
        self.minute = Ring("Minute", [f"{m:02d}" for m in range(60)], 5, 0, 5)
        self.palette_ = palette_for(scheme)
        self._bases: dict[tuple, QPixmap] = {}
        self._texts: dict[tuple, QStaticText] = {}
        self._bezel: QPixmap | None = None
        self._bezel_key: tuple | None = None
        self._show_minutes = show_minutes
        self._layout()

        self.year.jump_to(0)
        self.month.jump_to(when.month - 1)
        self._fit_days()
        self.day.jump_to(when.day - 1)
        self.hour.jump_to(when.hour)
        self.minute.jump_to(when.minute if show_minutes else 0)
        self.focus_ring = len(self.rings) - 1

        self._grab: Ring | None = None
        self._hover: Ring | None = None
        self._hub_hover = False
        self._hub_down = False
        self._flash = 0.0  # accent rim round the centre after a select, fading
        self._press = 0.0  # how far the centre is pushed in, 0 up to 1 fully down
        self._last_angle = 0.0
        self._samples: list[tuple[int, float]] = []
        self._wheel = 0
        self._clock = QElapsedTimer()
        self._clock.start()
        self._last_tick = 0
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self.setMinimumSize(360, 360)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # ---------- settings ----------
    def set_scheme(self, scheme: theme.ColorScheme):
        self.palette_ = palette_for(scheme)
        self.update()

    def show_minutes(self) -> bool:
        return self._show_minutes

    def set_show_minutes(self, show: bool):
        if show == self._show_minutes:
            return
        self._show_minutes = show
        if not show:
            self.minute.jump_to(0)  # times fall on the hour
        self._layout()
        self.focus_ring = min(self.focus_ring, len(self.rings) - 1)
        self.changed.emit(self.value())
        self.update()

    def _layout(self):
        """The knob keeps its size; the rings shown share the space around it."""
        self.rings = [self.year, self.month, self.day, self.hour]
        if self._show_minutes:
            self.rings.append(self.minute)
        band = (self.OUTER - self.HUB) / len(self.rings)
        for i, ring in enumerate(self.rings):
            ring.r_out = self.OUTER - i * band
            ring.r_in = ring.r_out - band
        self.hub = self.HUB

    # ---------- value ----------
    def value(self) -> dt.datetime:
        minute = self.minute.index if self._show_minutes else 0
        return dt.datetime(self.years[self.year.index], self.month.index + 1, self.day.index + 1,
                           self.hour.index, minute)

    def set_value(self, when: dt.datetime):
        if when.year in self.years:
            self.year.jump_to(self.years.index(when.year))
        self.month.jump_to(when.month - 1)
        self._fit_days()
        self.day.jump_to(when.day - 1)
        self.hour.jump_to(when.hour)
        self.minute.jump_to(when.minute if self._show_minutes else 0)
        self.changed.emit(self.value())
        self.update()

    def spin_to(self, when: dt.datetime):
        """Turn every ring to `when`, outer rings slowest, so the dial visibly
        spins there instead of jumping."""
        if when.year not in self.years:
            self.set_value(when)
            return
        targets = {
            self.year: self.years.index(when.year),
            self.month: when.month - 1,
            self.day: when.day - 1,
            self.hour: when.hour,
            self.minute: when.minute if self._show_minutes else 0,
        }
        # The day ring takes the target month's length now, so it lands right.
        n = calendar.monthrange(when.year, when.month)[1]
        if len(self.day.items) != n:
            keep = min(self.day.index, n - 1)
            self.day.items = [str(d) for d in range(1, n + 1)]
            self.day.jump_to(keep)
        for speed, (ring, index) in zip((4.5, 5.5, 6.5, 7.5, 8.5), targets.items()):
            ring.velocity = 0.0
            ring.target = ring.rotation_for(index)
            ring.spring = speed
        self._start()

    def _days_in_month(self) -> int:
        return calendar.monthrange(self.years[self.year.index], self.month.index + 1)[1]

    def _fit_days(self):
        """Give the day ring as many days as the chosen month has."""
        n = self._days_in_month()
        if len(self.day.items) != n:
            keep = min(self.day.index, n - 1)
            self.day.items = [str(d) for d in range(1, n + 1)]
            self.day.jump_to(keep)

    # ---------- geometry ----------
    def _radius(self) -> float:
        return min(self.width(), self.height()) * 0.47

    def _center(self) -> QPointF:
        return QPointF(self.width() / 2, self.height() / 2)

    def _ring_at(self, pos) -> Ring | None:
        c, R = self._center(), self._radius()
        d = math.hypot(pos.x() - c.x(), pos.y() - c.y()) / R
        return next((r for r in self.rings if r.r_in <= d < r.r_out), None)

    def _on_hub(self, pos) -> bool:
        c = self._center()
        return math.hypot(pos.x() - c.x(), pos.y() - c.y()) <= self.hub * self._radius()

    def _select(self):
        """Settle any ring still turning, then report the date it shows."""
        for ring in self.rings:
            if ring.moving():  # a step lands where it was going; a flick where it is
                aim = ring.target if ring.target is not None else ring.rotation
                ring.jump_to(ring.index_at(aim))
        self._grab = None
        self._sync()
        self._flash = 1.0
        self._start()
        self.selected.emit(self.value())

    def _angle_at(self, pos) -> float:
        c = self._center()
        return math.degrees(math.atan2(pos.y() - c.y(), pos.x() - c.x()))

    # ---------- input ----------
    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._on_hub(event.position()):
            self._hub_down = True
            self._start()
            return
        ring = self._ring_at(event.position())
        if ring is None:
            return
        self._grab = ring
        self.focus_ring = self.rings.index(ring)
        ring.velocity, ring.target = 0.0, None
        ring.lift_target = 1.0
        self._samples.clear()
        self._last_angle = self._angle_at(event.position())
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        self._start()

    def mouseMoveEvent(self, event):
        if self._grab is None:
            hub = self._on_hub(event.position())
            hover = None if self._hub_down else self._ring_at(event.position())
            if hover is not self._hover or hub != self._hub_hover:
                self._hover, self._hub_hover = hover, hub
                if hub:
                    self.setCursor(Qt.CursorShape.PointingHandCursor)
                else:
                    self.setCursor(Qt.CursorShape.OpenHandCursor if hover else Qt.CursorShape.ArrowCursor)
                self.update()
            return
        angle = self._angle_at(event.position())
        delta = (angle - self._last_angle + 180.0) % 360.0 - 180.0
        self._last_angle = angle
        self._grab.rotation += delta
        now = self._clock.elapsed()
        self._samples.append((now, delta))
        self._samples = [s for s in self._samples if now - s[0] <= 100]
        self._sync()
        self.update()

    def mouseReleaseEvent(self, event):
        if self._hub_down:
            self._hub_down = False
            if self._on_hub(event.position()):
                self._select()
            self._start()
            return
        ring, self._grab = self._grab, None
        if ring is None:
            return
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        now = self._clock.elapsed()
        recent = [s for s in self._samples if now - s[0] <= 80]
        ring.velocity = 0.0
        if recent:
            span = max(16, now - recent[0][0] + 16)
            ring.velocity = sum(d for _, d in recent) / (span / 1000.0)
        ring.target = None
        ring.lift_target = 0.0
        if ring.velocity == 0.0:
            ring.target = ring.rotation_for(ring.index_at(ring.rotation))
        self._start()

    def leaveEvent(self, event):
        if self._hover is not None or self._hub_hover:
            self._hover, self._hub_hover = None, False
            self.update()

    def wheelEvent(self, event):
        ring = self._ring_at(event.position()) or self.rings[self.focus_ring]
        self.focus_ring = self.rings.index(ring)
        self._wheel += event.angleDelta().y()
        while abs(self._wheel) >= 120:
            n = 1 if self._wheel > 0 else -1
            self._wheel -= 120 * n
            ring.step_by(n)
        self._start()
        event.accept()

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Up:
            self.focus_ring = max(0, self.focus_ring - 1)
        elif key == Qt.Key.Key_Down:
            self.focus_ring = min(len(self.rings) - 1, self.focus_ring + 1)
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self._select()
        elif key in (Qt.Key.Key_Right, Qt.Key.Key_Left):
            self.rings[self.focus_ring].step_by(1 if key == Qt.Key.Key_Right else -1)
            self._start()
        else:
            super().keyPressEvent(event)
            return
        self.update()

    # ---------- motion ----------
    def _start(self):
        self._last_tick = self._clock.elapsed()
        if not self._timer.isActive():
            self._timer.start()

    def _tick(self):
        now = self._clock.elapsed()
        dt_s = min(0.05, max(0.001, (now - self._last_tick) / 1000.0))
        self._last_tick = now
        busy = False
        for ring in self.rings:
            if ring is not self._grab and ring.moving():
                ring.tick(dt_s)
                busy = busy or ring.moving()
            gap = ring.lift_target - ring.lift
            if abs(gap) > 0.002:
                ring.lift += gap * min(1.0, dt_s * self.LIFT_SPEED)
                busy = True
            else:
                ring.lift = ring.lift_target
        press_to = 1.0 if self._hub_down else 0.0
        if self._press != press_to:
            # Goes down fast, like a button, and springs back a little slower.
            speed = 45.0 if self._hub_down else 16.0
            gap = press_to - self._press
            self._press = press_to if abs(gap) < 0.01 else self._press + gap * min(1.0, dt_s * speed)
            busy = True
        if self._flash > 0.0:
            self._flash = max(0.0, self._flash - dt_s * 1.8)
            busy = True
        self._sync()
        self.update()
        if not busy and self._grab is None:
            self._timer.stop()

    def _sync(self):
        before = self.value()
        for ring in self.rings:
            ring.index = ring.index_at(ring.rotation)
        if self._grab is None and not any(r.moving() for r in self.rings):
            self._fit_days()
        else:  # mid-spin: keep the value valid, fix the ring once it stops
            self.day.index = min(self.day.index, self._days_in_month() - 1)
        after = self.value()
        if after != before:
            self.changed.emit(after)

    # ---------- painting ----------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        c, R = self._center(), self._radius()
        pal = self.palette_

        self._paint_bezel(p, c, R)
        raised = [ring for ring in self.rings if ring.lift > 0.001]
        for i, ring in enumerate(self.rings):
            if ring in raised:
                self._paint_well(p, c, R, ring)
            else:
                lit = (i == self.focus_ring and self.hasFocus()) or ring is self._hover
                self._paint_ring(p, c, R, ring, lit)
        self._paint_hub(p, c, R)
        for ring in raised:
            self._paint_raised(p, c, R, ring)
        self._paint_window(p, c, R, pal)
        p.end()

    @staticmethod
    def _annulus(c: QPointF, ro: float, ri: float) -> QPainterPath:
        path = QPainterPath()
        path.addEllipse(c, ro, ro)
        path.addEllipse(c, ri, ri)  # odd-even fill leaves this as a hole
        return path

    def _edge(self, p: QPainter, c: QPointF, r: float, width: float, raised: bool):
        """A bevelled edge: lit at the top left, shaded at the bottom right."""
        g = QLinearGradient(c.x() - r, c.y() - r, c.x() + r, c.y() + r)
        hi, lo = QColor(255, 255, 255, 150), QColor(0, 0, 0, 170)
        g.setColorAt(0.0, hi if raised else lo)
        g.setColorAt(1.0, lo if raised else hi)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QBrush(g), width))
        p.drawEllipse(c, r, r)

    def _paint_bezel(self, p: QPainter, c: QPointF, R: float):
        """The rim and its shadow never move: drawn once per size and scheme."""
        dpr = self.devicePixelRatioF()
        key = (self.width(), self.height(), dpr, id(self.palette_))
        if self._bezel_key != key:
            pix = QPixmap(math.ceil(self.width() * dpr), math.ceil(self.height() * dpr))
            pix.setDevicePixelRatio(dpr)
            pix.fill(Qt.GlobalColor.transparent)
            bp = QPainter(pix)
            bp.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._draw_bezel(bp, c, R)
            bp.end()
            self._bezel, self._bezel_key = pix, key
        p.drawPixmap(0, 0, self._bezel)

    def _draw_bezel(self, p: QPainter, c: QPointF, R: float):
        pal = self.palette_
        p.setPen(Qt.PenStyle.NoPen)
        sh = QRadialGradient(c + QPointF(0, R * 0.05), R * 1.08)
        sh.setColorAt(0.86, QColor(0, 0, 0, 150))
        sh.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(sh)
        p.drawEllipse(c + QPointF(0, R * 0.05), R * 1.08, R * 1.08)

        # Polished rim: a mirror-like horizon, tinted by the scheme's metal.
        g = QLinearGradient(c.x(), c.y() - R, c.x(), c.y() + R)
        g.setColorAt(0.00, _mix(pal.shine, QColor(255, 255, 255), 0.5))
        g.setColorAt(0.38, _mix(pal.metal, pal.shine, 0.55))
        g.setColorAt(0.50, _mix(pal.shadow, pal.metal, 0.4))
        g.setColorAt(0.62, _mix(pal.metal, pal.shine, 0.25))
        g.setColorAt(1.00, pal.shadow)
        p.setBrush(g)
        p.drawEllipse(c, R, R)
        self._edge(p, c, R - 1, max(1.0, R * 0.008), raised=True)
        self._edge(p, c, R * self.OUTER + R * 0.01, max(1.0, R * 0.01), raised=False)

    def _paint_well(self, p: QPainter, c: QPointF, R: float, ring: Ring):
        """The empty channel a raised ring leaves behind."""
        ro, ri = ring.r_out * R, ring.r_in * R
        p.setPen(Qt.PenStyle.NoPen)
        g = QRadialGradient(c, ro)
        g.setColorAt(ri / ro, QColor(0, 0, 0))
        g.setColorAt(1.0, _mix(QColor(0, 0, 0), self.palette_.shadow, 0.5))
        p.setBrush(g)
        p.drawPath(self._annulus(c, ro, ri))

    def _paint_raised(self, p: QPainter, c: QPointF, R: float, ring: Ring):
        """A held ring: larger, lit, and casting a shadow onto the dial."""
        t = ring.lift
        scale = 1.0 + self.LIFT_SCALE * t
        ro, ri = ring.r_out * R * scale, ring.r_in * R * scale
        p.setPen(Qt.PenStyle.NoPen)
        for k, alpha in ((1.0, 70), (0.6, 70), (0.3, 60)):
            off = QPointF(0, R * self.LIFT_SHADOW * t * k)
            spread = R * 0.012 * t * (1.4 - k)
            p.setBrush(QColor(0, 0, 0, int(alpha * t)))
            p.drawPath(self._annulus(c + off, ro + spread, max(0.0, ri - spread)))
        p.save()
        p.translate(c)
        p.scale(scale, scale)
        p.translate(-c)
        self._paint_ring(p, c, R, ring, lit=True)
        p.restore()

    def _paint_ring(self, p: QPainter, c: QPointF, R: float, ring: Ring, lit: bool):
        pal = self.palette_
        ro, ri = ring.r_out * R, ring.r_in * R
        band = ro - ri
        metal = pal.metal.lighter(110) if ring.tone else pal.metal.darker(106)
        if lit:
            metal = metal.lighter(115)
        face = ro - R * 0.007
        base = self._ring_base(ring, R, metal)
        p.save()
        p.drawPixmap(QPointF(c.x() - ro - 2, c.y() - ro - 2), base)

        # Ticks and labels turn with the ring; their engraving stays lit from above.
        n = len(ring.items)
        p.translate(c)
        p.rotate(ring.rotation)
        top = -face + R * 0.012
        for i in range(n):
            labeled = i % ring.label_every == 0
            length = band * (0.17 if labeled else 0.10)
            width = max(1.0, R * (0.007 if labeled else 0.004))
            p.save()
            p.rotate(i * ring.step)
            p.setPen(QPen(pal.tick if labeled else _mix(pal.tick, metal, 0.4), width,
                          Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
            p.drawLine(QPointF(0, top), QPointF(0, top + length))
            p.restore()

        font = QFont(self.font())
        font.setBold(True)
        longest = max(len(s) for s in ring.items)
        mid = -(ro - band * 0.56)
        # Wider bands allow bigger labels, but no wider than the arc each one gets,
        # so a ring nearer the centre (fewer pixels around) never crowds.
        arc = 2 * math.pi * -mid / math.ceil(n / ring.label_every)
        fit = 0.72 * arc / (0.62 * longest)
        font.setPixelSize(max(7, int(min(band * (0.34 if longest <= 2 else 0.30), R * 0.085, fit))))
        p.setFont(font)
        relief = max(1.0, R * 0.005)
        for i in range(n):
            selected = i == ring.index
            if not selected and i % ring.label_every:
                continue
            gap = min((i - ring.index) % n, (ring.index - i) % n)
            if not selected and ring.label_every > 1 and gap <= 2:
                continue  # the selected minute shows in the window instead
            angle = i * ring.step
            screen = math.radians(ring.rotation + angle)
            # A one-pixel step straight down the screen, in this label's rotated frame.
            down = QPointF(relief * math.sin(screen), relief * math.cos(screen))
            text = self._static_text(ring.items[i], font)
            size = text.size()
            at = QPointF(-size.width() / 2, mid - size.height() / 2)
            p.save()
            p.rotate(angle)
            p.setPen(pal.text_relief)
            p.drawStaticText(at + down, text)
            p.setPen(pal.accent if selected else pal.text)
            p.drawStaticText(at, text)
            p.restore()
        p.restore()

    def _static_text(self, label: str, font: QFont) -> QStaticText:
        """Each label is laid out once and reused on every frame."""
        key = (label, font.pixelSize())
        text = self._texts.get(key)
        if text is None:
            text = QStaticText(label)
            text.setTextFormat(Qt.TextFormat.PlainText)
            text.prepare(font=font)
            self._texts[key] = text
        return text

    def _ring_base(self, ring: Ring, R: float, metal: QColor) -> QPixmap:
        """The ring's metal, grain, and bevels. The light never moves, so these
        look the same at every angle: draw them once and reuse the picture."""
        dpr = self.devicePixelRatioF()
        key = (ring.name, round(R, 2), dpr, ring.r_out, ring.r_in, metal.rgb(), id(self.palette_))
        pix = self._bases.get(key)
        if pix is not None:
            return pix
        if len(self._bases) > 40:
            self._bases.clear()
        pal = self.palette_
        ro, ri = ring.r_out * R, ring.r_in * R
        side = 2 * ro + 4
        pix = QPixmap(math.ceil(side * dpr), math.ceil(side * dpr))
        pix.setDevicePixelRatio(dpr)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(ro + 2, ro + 2)
        p.setClipPath(self._annulus(c, ro + 1, ri))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 220))
        p.drawEllipse(c, ro, ro)  # groove
        face = ro - R * 0.007
        p.setBrush(brushed(c, metal, pal.shine, pal.shadow))
        p.drawEllipse(c, face, face)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for frac, light, alpha in ring.grain:  # fine circular lathe marks
            r = ri + (face - ri) * frac
            p.setPen(QPen(QColor(255, 255, 255, int(alpha)) if light else QColor(0, 0, 0, int(alpha)), 1))
            p.drawEllipse(c, r, r)
        self._edge(p, c, face - R * 0.003, max(1.0, R * 0.006), raised=True)
        self._edge(p, c, ri + R * 0.003, max(1.0, R * 0.006), raised=False)
        p.end()
        self._bases[key] = pix
        return pix

    def _paint_hub(self, p: QPainter, c: QPointF, R: float):
        """The centre button. Pressed, it sinks into the dial and its dome turns concave."""
        pal = self.palette_
        k = self._press
        r = self.hub * R
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 220))
        p.drawEllipse(c, r, r)
        # Pushed in, the face gets smaller and drops a touch, so the dark gap
        # round it widens at the top: it has gone below the rings.
        top = r - R * (0.012 + 0.016 * k)
        cc = c + QPointF(0, R * 0.007 * k)
        hub_metal = _mix(pal.metal, pal.shine, 0.55 * (1 - 0.35 * k))
        p.setBrush(brushed(cc, hub_metal, QColor(255, 255, 255), pal.shadow, strength=1.1, light_deg=135))
        p.drawEllipse(cc, top, top)
        # Up: a dome lit from the top left. Down: a dish, lit from the bottom right.
        up = QRadialGradient(cc - QPointF(top * 0.35, top * 0.4), top * 1.35)
        up.setColorAt(0.0, QColor(255, 255, 255, int(110 * (1 - k))))
        up.setColorAt(0.55, QColor(255, 255, 255, 0))
        up.setColorAt(1.0, QColor(0, 0, 0, int(120 * (1 - k))))
        p.setBrush(up)
        p.drawEllipse(cc, top, top)
        if k > 0.0:
            dish = QRadialGradient(cc + QPointF(top * 0.3, top * 0.35), top * 1.3)
            dish.setColorAt(0.0, QColor(255, 255, 255, int(60 * k)))
            dish.setColorAt(0.5, QColor(255, 255, 255, 0))
            dish.setColorAt(1.0, QColor(0, 0, 0, int(150 * k)))
            p.setBrush(dish)
            p.drawEllipse(cc, top, top)
            # The rim of the hole shades the top of the face.
            lip = QLinearGradient(0, cc.y() - top, 0, cc.y() + top * 0.1)
            lip.setColorAt(0.0, QColor(0, 0, 0, int(140 * k)))
            lip.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.setBrush(lip)
            p.drawEllipse(cc, top, top)
        if self._hub_hover and k < 1.0:
            p.setBrush(QColor(255, 255, 255, int(28 * (1 - k))))
            p.drawEllipse(cc, top, top)
        self._edge(p, cc, top, max(1.0, R * 0.007), raised=k < 0.5)
        glow = max(self._flash, 0.45 if self._hub_hover else 0.0)
        if glow > 0.0:
            rim = QColor(pal.accent)
            rim.setAlphaF(min(1.0, glow))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(rim, max(1.5, R * (0.010 + 0.012 * self._flash))))
            p.drawEllipse(cc, top + R * 0.004, top + R * 0.004)
            p.setPen(Qt.PenStyle.NoPen)

        when = self.value()
        ink = _mix(pal.shadow, QColor(0, 0, 0), 0.6 + 0.2 * k)
        scale = 1 - 0.05 * k
        font = QFont(self.font())
        font.setBold(True)
        font.setPixelSize(max(8, int(r * 0.30 * scale)))
        p.setFont(font)
        p.setPen(ink)
        p.drawText(QRectF(cc.x() - r, cc.y() - r * 0.5, 2 * r, r * 0.45), Qt.AlignmentFlag.AlignCenter,
                   when.strftime("%a"))
        font.setPixelSize(max(8, int(r * 0.36 * scale)))
        p.setFont(font)
        p.drawText(QRectF(cc.x() - r, cc.y(), 2 * r, r * 0.5), Qt.AlignmentFlag.AlignCenter,
                   when.strftime("%H:%M"))

    def _paint_window(self, p: QPainter, c: QPointF, R: float, pal: DialPalette):
        """A fixed glass window at the top, across every ring, and the index mark."""
        half = R * 0.085
        rect = QRectF(c.x() - half, c.y() - R * 0.965, 2 * half, R * (0.965 - self.hub - 0.005))
        path = QPainterPath()
        path.addRoundedRect(rect, half * 0.6, half * 0.6)
        g = QLinearGradient(rect.left(), 0, rect.right(), 0)
        g.setColorAt(0.0, QColor(255, 255, 255, 46))
        g.setColorAt(0.3, QColor(255, 255, 255, 12))
        g.setColorAt(0.7, QColor(255, 255, 255, 8))
        g.setColorAt(1.0, QColor(255, 255, 255, 34))
        p.setBrush(g)
        p.setPen(QPen(QColor(255, 255, 255, 120), max(1.0, R * 0.005)))
        p.drawPath(path)

        tip_y = c.y() - R * 0.955
        base_y = c.y() - R * 0.998
        w = R * 0.04
        p.setPen(QPen(pal.accent.darker(220), max(1.0, R * 0.005)))
        p.setBrush(pal.accent)
        p.drawPolygon([QPointF(c.x() - w, base_y), QPointF(c.x() + w, base_y), QPointF(c.x(), tip_y)])


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
