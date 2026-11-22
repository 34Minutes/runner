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

The demo window is prototypes/interval_roller.py.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, QSizeF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QImage,
    QPainterPath,
    QPen,
    QPixmap,
    QStaticText,
)
from PySide6.QtWidgets import QWidget

from . import theme
from .date_dial import DialPalette, _mix, palette_for  # the same materials as the dial


# ---------- the interval ----------
@dataclass(frozen=True)
class Unit:
    name: str
    singular: str
    radix: int  # how many make one of the unit on the left (months: the roller's range)


UNITS = (
    Unit("Months", "month", 100),
    Unit("Weeks", "week", 4),
    Unit("Days", "day", 7),
    Unit("Hours", "hour", 24),
    Unit("Minutes", "minute", 60),
)


def _places() -> list[int]:
    """How many minutes-or-carry steps one notch of each roller is worth."""
    places, p = [], 1
    for unit in reversed(UNITS):
        places.append(p)
        p *= unit.radix
    return list(reversed(places))


PLACES = _places()
MAX_TOTAL = PLACES[0] * UNITS[0].radix - 1


def digits(total: int) -> list[int]:
    out = []
    for place, unit in zip(PLACES, UNITS):
        out.append((total // place) % unit.radix)
    return out


def describe(total: int) -> str:
    parts = [f"{d} {u.singular}{'' if d == 1 else 's'}" for d, u in zip(digits(total), UNITS) if d]
    if not parts:
        return "No interval"
    if len(parts) == 1:
        return "Every " + parts[0]
    return "Every " + ", ".join(parts[:-1]) + " and " + parts[-1]


# ---------- one roller ----------
class Roller:
    """A drum of numbers. `committed` is the notch it rests on (unwrapped, so a
    wrap from 59 to 0 keeps turning forward); `pos` is where it is drawn."""

    FRICTION = 3.2
    COAST_MIN = 1.2  # notches per second below which a flick stops coasting
    SPRING = 14.0

    def __init__(self, index: int, unit: Unit):
        self.index = index
        self.unit = unit
        self.wraps = index > 0  # the leftmost has nothing to carry into
        self.committed = 0
        self.pos = 0.0
        self.velocity = 0.0  # notches per second while coasting
        self.dragging = False
        self.lift = 0.0  # 0 resting in the rim, 1 raised while held
        self.lift_target = 0.0

    @property
    def n(self) -> int:
        return self.unit.radix

    def show_digit(self, d: int):
        """Turn to digit d the short way round, as a carry does."""
        if not self.wraps:
            self.committed = d
            return
        diff = (d - self.committed) % self.n
        if diff > self.n / 2:
            diff -= self.n
        self.committed += diff

    def moving(self) -> bool:
        return (self.dragging or self.velocity != 0.0 or abs(self.pos - self.committed) > 0.002
                or self.lift != self.lift_target)


def _drum_light(t: float) -> float:
    """How brightly a brushed drum shines at height t (0 top, 1 bottom), lit from
    above: broad soft lobes, as on the dial, never a mirror's sharp edge."""
    v = 0.16 + 0.30 * math.sin(math.pi * t)  # the cylinder turning away top and bottom
    v += 0.70 * math.exp(-(((t - 0.15) / 0.10) ** 2))  # the lobe facing the light
    v += 0.28 * math.exp(-(((t - 0.80) / 0.08) ** 2))  # a fainter one below
    return max(0.0, min(1.0, v))


def _drum_spec(t: float) -> float:
    """The shine on top of the brushing: how far toward white at height t."""
    s = 0.85 * math.exp(-(((t - 0.145) / 0.028) ** 2))  # the light itself, reflected
    s += 0.30 * math.exp(-(((t - 0.145) / 0.07) ** 2))  # its bloom
    s += 0.40 * math.exp(-(((t - 0.815) / 0.018) ** 2))  # a thin second reflection
    return min(0.92, s)


# ---------- the widget ----------
class IntervalRoller(QWidget):
    changed = Signal(int)  # the interval, as a mixed-radix total (see digits())
    selected = Signal(int)  # the Select key was pressed; the total, as for changed

    STEP_DEG = 30.0  # angle between neighbouring numbers on the drum
    LABEL_H = 26

    def __init__(self, total: int = 60, *, scheme: theme.ColorScheme = theme.DARK, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(440, 220)
        self.rollers = [Roller(i, u) for i, u in enumerate(UNITS)]
        self._total = 0
        self.focus_roller = len(self.rollers) - 2  # hours
        self.palette_: DialPalette = palette_for(scheme)
        self.scheme = scheme
        self._texts: dict[tuple[str, int], QStaticText] = {}
        self._bases: dict[tuple, QPixmap] = {}
        self._noise: dict[int, QImage] = {}
        self._bezel: QPixmap | None = None
        self._bezel_key: tuple | None = None
        self._grain = []  # each drum's lathe lines, fixed
        for i in range(len(self.rollers) + 1):  # the last is the Select key
            rnd = random.Random(i + 1)
            self._grain.append([(rnd.random(), rnd.random() < 0.5, rnd.uniform(6, 26)) for _ in range(140)])
        self._wheel_acc = 0
        self._press: tuple[Roller, float, float, bool] | None = None  # roller, start y, start pos, moved
        self._drag_samples: list[tuple[float, float]] = []
        self._key_hover = False
        self._key_down = False
        self._key_press = 0.0  # how far the Select key is pushed in, 0 up to 1 down
        self._key_flash = 0.0  # accent rim after a select, fading
        self.setMouseTracking(True)

        self._clock = QElapsedTimer()
        self._clock.start()
        self._last = 0
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._animate)

        self.set_total(total, animate=False)

    # ----- value -----
    def total(self) -> int:
        return self._total

    def values(self) -> dict[str, int]:
        return {u.name: d for u, d in zip(UNITS, digits(self._total))}

    def set_total(self, total: int, animate: bool = True):
        self._total = max(0, min(MAX_TOTAL, total))
        for r, d in zip(self.rollers, digits(self._total)):
            r.show_digit(d)
            if not animate:
                r.pos = float(r.committed)
        self._kick()
        self.changed.emit(self._total)

    def step(self, roller: Roller, n: int) -> bool:
        """Add n notches on this roller; the others carry. False if it hits 0 or the top."""
        new = self._total + n * PLACES[roller.index]
        if new < 0 or new > MAX_TOTAL:
            return False
        self.set_total(new)
        return True

    def set_scheme(self, scheme: theme.ColorScheme):
        self.scheme = scheme
        self.palette_ = palette_for(scheme)
        self.update()

    # ----- motion -----
    def _kick(self):
        if not self._timer.isActive():
            self._last = self._clock.elapsed()
            self._timer.start()
        self.update()

    def _follow(self, roller: Roller):
        """Commit every notch the roller's been turned past by hand or by coasting."""
        while round(roller.pos) != roller.committed:
            way = 1 if roller.pos > roller.committed else -1
            if not self.step(roller, way):
                limit = roller.committed + 0.35 * way  # stops against zero or the top
                roller.pos = min(roller.pos, limit) if way > 0 else max(roller.pos, limit)
                roller.velocity = 0.0
                break

    def _animate(self):
        now = self._clock.elapsed()
        dt_s = min(0.05, (now - self._last) / 1000.0)
        self._last = now
        busy = False
        press_to = 1.0 if self._key_down else 0.0
        if self._key_press != press_to:
            # Down fast, like a key, and back up a little slower.
            gap = press_to - self._key_press
            speed = 45.0 if self._key_down else 16.0
            self._key_press = press_to if abs(gap) < 0.01 else self._key_press + gap * min(1.0, dt_s * speed)
            busy = True
        if self._key_flash > 0.0:
            self._key_flash = max(0.0, self._key_flash - dt_s * 1.8)
            busy = True
        for r in self.rollers:
            if r.lift != r.lift_target:
                diff = r.lift_target - r.lift
                r.lift = r.lift_target if abs(diff) < 0.01 else r.lift + diff * min(1.0, dt_s * self.LIFT_SPEED)
            if r.dragging:
                busy = True
                continue
            if r.velocity:
                r.pos += r.velocity * dt_s
                r.velocity *= math.exp(-Roller.FRICTION * dt_s)
                if abs(r.velocity) < Roller.COAST_MIN:
                    r.velocity = 0.0
                self._follow(r)
            else:
                diff = r.committed - r.pos
                r.pos = r.committed if abs(diff) < 0.002 else r.pos + diff * min(1.0, dt_s * Roller.SPRING)
            busy = busy or r.moving()
        if not busy:
            self._timer.stop()
        self.update()

    # ----- geometry -----
    MARGIN = 10.0
    SIDE = 22.0  # bezel beside the drums
    TOP = 34.0  # bezel above the drums, where the unit names are engraved
    BOTTOM = 18.0

    def _geometry(self) -> tuple[QRectF, list[QRectF], float, QRectF]:
        """The bezel, each drum's slot, the drum radius, and the Select key.

        The key is a drum's size, to the right of the drums, in its own recess.
        """
        n = len(self.rollers)
        h = self.height() - 2 * self.MARGIN - self.TOP - self.BOTTOM
        drum_h = max(80.0, min(h, 300.0))
        gap = max(6.0, drum_h * 0.05)
        key_gap = gap * 3
        w = min((self.width() - 2 * self.MARGIN - 2 * self.SIDE - (n - 1) * gap - key_gap) / (n + 1),
                drum_h * 0.62)
        total_w = (n + 1) * w + (n - 1) * gap + key_gap
        x0 = (self.width() - total_w) / 2
        y0 = self.MARGIN + self.TOP + (h - drum_h) / 2
        slots = [QRectF(x0 + i * (w + gap), y0, w, drum_h) for i in range(n)]
        key = QRectF(slots[-1].right() + key_gap, y0, w, drum_h)
        bezel = QRectF(x0 - self.SIDE, y0 - self.TOP, total_w + 2 * self.SIDE, drum_h + self.TOP + self.BOTTOM)
        return bezel, slots, drum_h / 2, key

    def _layout(self) -> tuple[QRectF, list[QRectF], float]:
        """The bezel, each drum's slot, and the drum radius."""
        bezel, slots, radius, _ = self._geometry()
        return bezel, slots, radius

    def _key_rect(self) -> QRectF:
        return self._geometry()[3]

    def _on_key(self, pos: QPointF) -> bool:
        return self._key_rect().contains(pos)

    def can_select(self) -> bool:
        return self._total > 0

    def select(self) -> None:
        """Press the Select key: report the interval, if there is one."""
        if not self.can_select():
            return
        self._key_flash = 1.0
        self._kick()
        self.selected.emit(self._total)

    def _roller_at(self, pos: QPointF) -> Roller | None:
        _, slots, _ = self._layout()
        for r, s in zip(self.rollers, slots):
            if s.adjusted(-4, -self.TOP, 4, 4).contains(pos):
                return r
        return None

    def _notch_px(self) -> float:
        return self._layout()[2] * math.radians(self.STEP_DEG)
    # ----- input -----
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._on_key(e.position()):
            if self.can_select():
                self._key_down = True
                self._kick()
            return
        r = self._roller_at(e.position())
        if r is None:
            return
        self.focus_roller = r.index
        r.velocity = 0.0
        r.dragging = True
        r.lift_target = 1.0
        self._press = (r, e.position().y(), r.pos, False)
        self._drag_samples = [(self._clock.elapsed() / 1000.0, r.pos)]
        self._kick()

    def mouseMoveEvent(self, e):
        hover = self._on_key(e.position())
        if hover != self._key_hover:
            self._key_hover = hover
            usable = hover and self.can_select()
            self.setCursor(Qt.CursorShape.PointingHandCursor if usable else Qt.CursorShape.ArrowCursor)
            self.update()
        if not self._press:
            return
        r, y0, p0, moved = self._press
        dy = e.position().y() - y0
        if abs(dy) > 3:
            moved = True
        self._press = (r, y0, p0, moved)
        if not moved:
            return
        r.pos = p0 - dy / self._notch_px()  # drag down: smaller numbers come round
        self._follow(r)
        t = self._clock.elapsed() / 1000.0
        self._drag_samples = [s for s in self._drag_samples if t - s[0] < 0.08] + [(t, r.pos)]
        self.update()

    def mouseReleaseEvent(self, e):
        if self._key_down:
            self._key_down = False
            if self._on_key(e.position()):  # moving off first cancels, as on any button
                self.select()
            self._kick()
            return
        if not self._press:
            return
        r, _, _, moved = self._press
        self._press = None
        r.dragging = False
        r.lift_target = 0.0
        if moved:
            (t0, p0), (t1, p1) = self._drag_samples[0], self._drag_samples[-1]
            if t1 - t0 > 0.005:
                v = (p1 - p0) / (t1 - t0)
                r.velocity = v if abs(v) > 4.0 else 0.0
        else:  # a click above the middle steps down, below steps up
            _, slots, _ = self._layout()
            self.step(r, -1 if e.position().y() < slots[r.index].center().y() else 1)
        self._kick()

    def leaveEvent(self, e):
        if self._key_hover:
            self._key_hover = False
            self.update()

    def wheelEvent(self, e):
        r = self._roller_at(e.position())
        if r is None:
            return
        self.focus_roller = r.index
        self._wheel_acc += e.angleDelta().y()
        while abs(self._wheel_acc) >= 120:
            way = 1 if self._wheel_acc > 0 else -1
            self._wheel_acc -= 120 * way
            self.step(r, way)
        self.update()

    def keyPressEvent(self, e):
        k = e.key()
        if k in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            way = -1 if k == Qt.Key.Key_Left else 1
            self.focus_roller = max(0, min(len(self.rollers) - 1, self.focus_roller + way))
            self.update()
        elif k in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            self.step(self.rollers[self.focus_roller], 1 if k == Qt.Key.Key_Up else -1)
        elif k in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.select()
        else:
            super().keyPressEvent(e)

    # ----- painting -----
    LIFT_SCALE = 0.04
    LIFT_SPEED = 11.0
    LIFT_SHADOW = 0.06  # of the drum's height
    CORNER = 8.0

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        pal = self.palette_
        p.fillRect(self.rect(), pal.background)
        bezel, slots, radius, key = self._geometry()
        self._paint_bezel(p, bezel, slots)
        self._paint_key(p, key)

        resting = [(r, s) for r, s in zip(self.rollers, slots) if r.lift <= 0.001]
        raised = [(r, s) for r, s in zip(self.rollers, slots) if r.lift > 0.001]
        for r, s in resting:
            self._paint_drum(p, r, s, radius, lit=False)
        for r, s in raised:
            self._paint_well(p, s)
            self._paint_raised(p, r, s, radius)
        self._paint_window(p, slots, radius)

    # bezel
    def _paint_bezel(self, p: QPainter, bezel: QRectF, slots: list[QRectF]):
        """The rim never moves: drawn once per size and scheme."""
        dpr = self.devicePixelRatioF()
        key = (self.width(), self.height(), dpr, id(self.palette_), self.focus_roller, self.hasFocus())
        if self._bezel_key != key:
            pix = QPixmap(math.ceil(self.width() * dpr), math.ceil(self.height() * dpr))
            pix.setDevicePixelRatio(dpr)
            pix.fill(Qt.GlobalColor.transparent)
            bp = QPainter(pix)
            bp.setRenderHint(QPainter.RenderHint.Antialiasing)
            bp.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            self._draw_bezel(bp, bezel, slots, self._key_rect())
            bp.end()
            self._bezel, self._bezel_key = pix, key
        p.drawPixmap(0, 0, self._bezel)

    def _draw_bezel(self, p: QPainter, bezel: QRectF, slots: list[QRectF], key: QRectF):
        pal = self.palette_
        radius = 18.0
        p.setPen(Qt.PenStyle.NoPen)
        for grow, drop, alpha in ((10, 9, 30), (6, 6, 45), (3, 4, 60)):  # soft shadow beneath
            p.setBrush(QColor(0, 0, 0, alpha))
            p.drawRoundedRect(bezel.adjusted(-grow, -grow + drop, grow, grow + drop), radius + grow, radius + grow)

        # Polished rim: a mirror-like horizon, tinted by the scheme's metal.
        g = QLinearGradient(0, bezel.top(), 0, bezel.bottom())
        g.setColorAt(0.00, _mix(pal.shine, QColor(255, 255, 255), 0.5))
        g.setColorAt(0.38, _mix(pal.metal, pal.shine, 0.55))
        g.setColorAt(0.50, _mix(pal.shadow, pal.metal, 0.4))
        g.setColorAt(0.62, _mix(pal.metal, pal.shine, 0.25))
        g.setColorAt(1.00, pal.shadow)
        p.setBrush(g)
        p.drawRoundedRect(bezel, radius, radius)
        self._edge(p, bezel.adjusted(0.5, 0.5, -0.5, -0.5), radius, 1.6, raised=True)

        # The recess the drums turn in.
        recess = QRectF(slots[0].left() - 6, slots[0].top() - 6,
                        slots[-1].right() - slots[0].left() + 12, slots[0].height() + 12)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_mix(QColor(0, 0, 0), pal.shadow, 0.35))
        p.drawRoundedRect(recess, self.CORNER + 4, self.CORNER + 4)
        self._edge(p, recess, self.CORNER + 4, 2.0, raised=False)
        for s in slots:  # each drum's own groove
            p.setBrush(QColor(0, 0, 0, 200))
            p.drawRoundedRect(s.adjusted(-1.5, -1.5, 1.5, 1.5), self.CORNER + 1, self.CORNER + 1)
        # The Select key's own recess, the same depth as the drums'.
        hole = key.adjusted(-6, -6, 6, 6)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_mix(QColor(0, 0, 0), pal.shadow, 0.35))
        p.drawRoundedRect(hole, self.CORNER + 4, self.CORNER + 4)
        self._edge(p, hole, self.CORNER + 4, 2.0, raised=False)
        p.setBrush(QColor(0, 0, 0, 200))
        p.drawRoundedRect(key.adjusted(-1.5, -1.5, 1.5, 1.5), self.CORNER + 1, self.CORNER + 1)

        # Unit names engraved into the rim.
        font = QFont(self.font())
        font.setPixelSize(12)
        font.setBold(True)
        font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 110)
        p.setFont(font)
        ink = _mix(pal.shadow, QColor(0, 0, 0), 0.6)
        lit = QColor(255, 255, 255, 120)
        for r, s in zip(self.rollers, slots):
            box = QRectF(s.left() - 10, bezel.top() + 4, s.width() + 20, self.TOP - 10)
            flags = Qt.AlignmentFlag.AlignCenter
            p.setPen(lit)
            p.drawText(box.translated(0, 1), flags, r.unit.name.upper())
            focused = self.hasFocus() and r.index == self.focus_roller
            p.setPen(pal.accent.darker(130) if focused else ink)
            p.drawText(box, flags, r.unit.name.upper())
            if focused:  # a small inlaid bar under the focused drum
                bar = QRectF(s.center().x() - s.width() * 0.18, s.bottom() + 8, s.width() * 0.36, 3)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(pal.accent)
                p.drawRoundedRect(bar, 1.5, 1.5)

    def _edge(self, p: QPainter, rect: QRectF, radius: float, width: float, raised: bool):
        """A bevelled edge: lit at the top left, shaded at the bottom right."""
        g = QLinearGradient(rect.topLeft(), rect.bottomRight())
        hi, lo = QColor(255, 255, 255, 150), QColor(0, 0, 0, 170)
        g.setColorAt(0.0, hi if raised else lo)
        g.setColorAt(1.0, lo if raised else hi)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QBrush(g), width))
        p.drawRoundedRect(rect, radius, radius)

    # drums
    def _drum_base(self, index: int, size: QSizeF, lit: bool) -> QPixmap:
        """The drum's brushed metal, lathe lines and bevels. The light never
        moves, so they look the same however far it turns: draw them once."""
        dpr = self.devicePixelRatioF()
        key = (index, round(size.width(), 1), round(size.height(), 1), lit, dpr, id(self.palette_))
        pix = self._bases.get(key)
        if pix is not None:
            return pix
        if len(self._bases) > 40:
            self._bases.clear()
        metal = self._drum_metal(index)
        if lit:
            metal = metal.lighter(115)
        w, h = size.width(), size.height()
        pix = QPixmap(math.ceil(w * dpr), math.ceil(h * dpr))
        pix.setDevicePixelRatio(dpr)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0, 0, w, h)
        clip = QPainterPath()
        clip.addRoundedRect(rect, self.CORNER, self.CORNER)
        p.setClipPath(clip)

        # Brushed aluminium turned into a drum: soft lobes of light, as on the dial.
        g = QLinearGradient(0, 0, 0, h)
        for k in range(129):
            t = k / 128
            col = self._metal_at(min(1.0, _drum_light(t) + (0.06 if lit else 0.0)), metal)
            g.setColorAt(t, _mix(col, QColor(255, 255, 255), _drum_spec(t)))
        p.fillRect(rect, g)

        # Brushing: a faint fine texture under the dial's own kind of lathe lines.
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Overlay)
        p.setOpacity(0.24)
        p.drawImage(rect, self._brush_noise(index))
        p.setOpacity(1.0)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        for frac, light, alpha in self._grain[index]:  # fine lathe lines round the drum
            x = 1 + (w - 2) * frac
            p.setPen(QPen(QColor(255, 255, 255, int(alpha)) if light else QColor(0, 0, 0, int(alpha)), 1))
            p.drawLine(QPointF(x, 0), QPointF(x, h))
        p.setClipping(False)
        self._edge(p, rect.adjusted(0.75, 0.75, -0.75, -0.75), self.CORNER, 1.4, raised=True)
        p.end()
        self._bases[key] = pix
        return pix

    BLACKEN = 0.62  # how far the drums' metal is taken toward black

    def _drum_metal(self, index: int) -> QColor:
        """The scheme's metal, blackened, alternating a shade lighter and darker like the dial's rings."""
        base = _mix(self.palette_.metal, QColor(0, 0, 0), self.BLACKEN)
        return base.lighter(118) if index % 2 else base

    def _metal_at(self, f: float, metal: QColor) -> QColor:
        """The dial's ramp: soft shadow, the metal, then most of the way to its shine."""
        pal = self.palette_
        lo = _mix(_mix(pal.shadow, QColor(0, 0, 0), 0.6), metal, 0.35)
        return _mix(lo, metal, f * 2) if f < 0.5 else _mix(metal, pal.shine, (f - 0.5) * 2 * 0.85)

    def _brush_noise(self, index: int) -> QImage:
        """Random grey per column, a few rows tall: stretched down the drum it
        becomes the long streaks of brushed metal."""
        img = self._noise.get(index)
        if img is None:
            rnd = random.Random(100 + index)
            cols, rows = 480, 4
            data = bytes(max(0, min(255, int(rnd.gauss(128, 22)))) for _ in range(cols * rows))
            img = QImage(data, cols, rows, cols, QImage.Format.Format_Grayscale8).copy()
            self._noise[index] = img
        return img

    def _paint_drum(self, p: QPainter, r: Roller, slot: QRectF, radius: float, lit: bool):
        pal = self.palette_
        p.drawPixmap(slot.topLeft(), self._drum_base(r.index, slot.size(), lit))
        clip = QPainterPath()
        clip.addRoundedRect(slot.adjusted(1, 1, -1, -1), self.CORNER, self.CORNER)
        p.save()
        p.setClipPath(clip)
        metal = self._drum_metal(r.index)
        cx, cy = slot.center().x(), slot.center().y()
        # Black metal takes light engraving in every scheme, and an accent light enough to read on it.
        ink = _mix(pal.shine, QColor(255, 255, 255), 0.4)
        tick = _mix(pal.shine, metal, 0.35)
        accent = pal.accent if pal.accent.lightnessF() > 0.45 else pal.accent.lighter(190)

        # Ticks at both sides, a long one by each number and a short one between.
        tick_in = slot.width() * 0.13
        for k in range(math.floor(r.pos * 2) - 6, math.ceil(r.pos * 2) + 7):
            i = k / 2
            if not r.wraps and not 0 <= i <= r.n - 1:
                continue
            theta = math.radians((i - r.pos) * self.STEP_DEG)
            if abs(theta) >= math.radians(84):
                continue
            y = cy + radius * math.sin(theta)
            major = k % 2 == 0
            length = tick_in * (1.0 if major else 0.55)
            col = tick if major else _mix(tick, metal, 0.4)
            p.setPen(QPen(col, max(1.0, radius * (0.016 if major else 0.010) * math.cos(theta)),
                          Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
            p.drawLine(QPointF(slot.left() + 3, y), QPointF(slot.left() + 3 + length, y))
            p.drawLine(QPointF(slot.right() - 3, y), QPointF(slot.right() - 3 - length, y))

        # Engraved numbers: the engraving's edge catches the light from above.
        font = QFont(self.font())
        font.setPixelSize(max(10, int(radius * 0.40)))
        font.setBold(True)
        font.setFeature(QFont.Tag("tnum"), 1)
        p.setFont(font)
        relief = max(1.0, radius * 0.012)
        for i in range(math.floor(r.pos) - 3, math.ceil(r.pos) + 4):
            if not r.wraps and not 0 <= i < r.n:
                continue
            theta = math.radians((i - r.pos) * self.STEP_DEG)
            if abs(theta) >= math.radians(86):
                continue
            text = self._static_text(f"{i % r.n:02d}", font)
            size = text.size()
            at = QPointF(-size.width() / 2, -size.height() / 2)
            near = max(0.0, 1.0 - abs(i - r.pos) * 2.0)  # 1 when it sits in the window
            p.save()
            p.translate(cx, cy + radius * math.sin(theta))
            p.scale(1.0, math.cos(theta))
            p.setPen(QColor(0, 0, 0, 200))
            p.drawStaticText(at + QPointF(0, relief), text)
            p.setPen(_mix(ink, accent, near))
            p.drawStaticText(at, text)
            p.restore()

        self._paint_depth_and_gloss(p, slot)
        p.restore()

    @staticmethod
    def _paint_depth_and_gloss(p: QPainter, slot: QRectF, gloss_k: float = 1.0):
        # Depth: the drum turns into shadow toward the top and bottom of its slot.
        shade = QLinearGradient(0, slot.top(), 0, slot.bottom())
        dark = QColor(0, 0, 0)
        for at, alpha in ((0.0, 140), (0.08, 35), (0.18, 0), (0.84, 0), (0.93, 40), (1.0, 150)):
            dark.setAlpha(alpha)
            shade.setColorAt(at, QColor(dark))
        p.fillRect(slot, shade)

        # Gloss: the drum's clear coat reflects the light over the numbers too.
        gloss = QLinearGradient(0, slot.top(), 0, slot.bottom())
        for at, alpha in ((0.08, 0), (0.125, 40), (0.145, 95), (0.165, 40), (0.21, 0),
                          (0.79, 0), (0.815, 45), (0.84, 0)):
            gloss.setColorAt(at, QColor(255, 255, 255, int(alpha * gloss_k)))
        p.fillRect(slot, gloss)

    def _paint_key(self, p: QPainter, slot: QRectF):
        """The Select key: a drum's size and metal, with SELECT down its face.

        Pressed, it sinks into its recess and its top falls into shadow.
        """
        pal = self.palette_
        k = self._key_press
        usable = self.can_select()
        lit = self._key_hover and usable and k < 0.5
        # Pushed in: a little smaller and lower, so the dark gap round it opens at the top.
        inset = slot.width() * 0.035 * k
        face = slot.adjusted(inset, inset + slot.height() * 0.012 * k, -inset, -inset + slot.height() * 0.012 * k)
        p.drawPixmap(face.topLeft(), self._drum_base(len(self.rollers), face.size(), lit))
        clip = QPainterPath()
        clip.addRoundedRect(face.adjusted(1, 1, -1, -1), self.CORNER, self.CORNER)
        p.save()
        p.setClipPath(clip)
        metal = self._drum_metal(len(self.rollers))

        # SELECT, one letter under the next, engraved like the numbers.
        letters = "SELECT"
        font = QFont(self.font())
        font.setBold(True)
        pitch = face.height() * 0.70 / len(letters)
        font.setPixelSize(max(9, int(min(pitch * 0.82, face.width() * 0.42))))
        p.setFont(font)
        ink = _mix(pal.shine, QColor(255, 255, 255), 0.4)
        accent = pal.accent if pal.accent.lightnessF() > 0.45 else pal.accent.lighter(190)
        if not usable:
            ink = _mix(ink, metal, 0.65)
        elif lit or self._key_flash > 0:
            ink = _mix(ink, accent, max(0.75 if lit else 0.0, self._key_flash))
        relief = max(1.0, face.height() * 0.006)
        top = face.center().y() - pitch * len(letters) / 2
        for i, ch in enumerate(letters):
            box = QRectF(face.left(), top + i * pitch, face.width(), pitch)
            p.setPen(QColor(0, 0, 0, 200 if usable else 120))
            p.drawText(box.translated(0, relief), Qt.AlignmentFlag.AlignCenter, ch)
            p.setPen(ink)
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, ch)

        self._paint_depth_and_gloss(p, face, gloss_k=1.0 - 0.7 * k)
        if k > 0:
            # The rim of the recess shades the top of the sunken key.
            lip = QLinearGradient(0, face.top(), 0, face.top() + face.height() * 0.35)
            lip.setColorAt(0.0, QColor(0, 0, 0, int(170 * k)))
            lip.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.fillRect(face, lip)
            p.fillRect(face, QColor(0, 0, 0, int(45 * k)))
        p.restore()
        self._edge(p, face.adjusted(0.75, 0.75, -0.75, -0.75), self.CORNER, 1.4, raised=k < 0.5)

        glow = max(self._key_flash, 0.5 if lit else 0.0)
        if glow > 0:
            rim = QColor(pal.accent)
            rim.setAlphaF(min(1.0, glow))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(rim, 1.5 + 1.5 * self._key_flash))
            p.drawRoundedRect(face.adjusted(-2, -2, 2, 2), self.CORNER + 2, self.CORNER + 2)

    def _paint_well(self, p: QPainter, slot: QRectF):
        """The empty channel a raised drum leaves behind."""
        g = QLinearGradient(0, slot.top(), 0, slot.bottom())
        g.setColorAt(0.0, QColor(0, 0, 0))
        g.setColorAt(1.0, _mix(QColor(0, 0, 0), self.palette_.shadow, 0.5))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(slot, self.CORNER, self.CORNER)

    def _paint_raised(self, p: QPainter, r: Roller, slot: QRectF, radius: float):
        """A held drum: larger, lit, and casting a shadow onto the rim."""
        t = r.lift
        scale = 1.0 + self.LIFT_SCALE * t
        c = slot.center()
        p.setPen(Qt.PenStyle.NoPen)
        for k, alpha in ((1.0, 70), (0.6, 70), (0.3, 60)):
            off = slot.height() * self.LIFT_SHADOW * t * k
            spread = slot.width() * 0.04 * t * (1.4 - k)
            shadow = QRectF(slot.left() - spread, slot.top() - spread + off,
                            slot.width() + 2 * spread, slot.height() + 2 * spread)
            shadow = QRectF(c.x() + (shadow.left() - c.x()) * scale, c.y() + (shadow.top() - c.y()) * scale,
                            shadow.width() * scale, shadow.height() * scale)
            p.setBrush(QColor(0, 0, 0, int(alpha * t)))
            p.drawRoundedRect(shadow, self.CORNER + spread, self.CORNER + spread)
        p.save()
        p.translate(c)
        p.scale(scale, scale)
        p.translate(-c)
        self._paint_drum(p, r, slot, radius, lit=True)
        p.restore()

    def _paint_window(self, p: QPainter, slots: list[QRectF], radius: float):
        """A fixed glass window across every drum at the reading line, and the index marks."""
        pal = self.palette_
        half = radius * math.sin(math.radians(self.STEP_DEG)) * 0.55
        cy = slots[0].center().y()
        band = QRectF(slots[0].left() - 5, cy - half, slots[-1].right() - slots[0].left() + 10, 2 * half)
        path = QPainterPath()
        path.addRoundedRect(band, half * 0.6, half * 0.6)
        g = QLinearGradient(0, band.top(), 0, band.bottom())
        g.setColorAt(0.0, QColor(255, 255, 255, 46))
        g.setColorAt(0.3, QColor(255, 255, 255, 12))
        g.setColorAt(0.7, QColor(255, 255, 255, 8))
        g.setColorAt(1.0, QColor(255, 255, 255, 34))
        p.setBrush(g)
        p.setPen(QPen(QColor(255, 255, 255, 120), 1.2))
        p.drawPath(path)

        w = 5.0  # index marks on the rim, pointing in at the reading line
        p.setPen(QPen(pal.accent.darker(220), 1))
        p.setBrush(pal.accent)
        left, right = band.left() - 3, band.right() + 3
        p.drawPolygon([QPointF(left - w * 1.6, cy - w), QPointF(left - w * 1.6, cy + w), QPointF(left, cy)])
        p.drawPolygon([QPointF(right + w * 1.6, cy - w), QPointF(right + w * 1.6, cy + w), QPointF(right, cy)])

    def _static_text(self, label: str, font: QFont) -> QStaticText:
        """Each number is laid out once and reused on every frame."""
        key = (label, font.pixelSize())
        text = self._texts.get(key)
        if text is None:
            text = QStaticText(label)
            text.setTextFormat(Qt.TextFormat.PlainText)
            text.prepare(font=font)
            self._texts[key] = text
        return text
