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
    QLineEdit,
    QApplication,
)

from ..config import AppConfig, Launcher
from .launch_button import LaunchButton


class DropdownPanel(QWidget):
    """The expanding list of launch buttons. Animated show/hide."""

    launch_requested = Signal(Launcher)  # emitted when a button is clicked
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
        self._anchor_trigger: QWidget | None = None  # for re-positioning after show() on some platforms
        self._grow_from_top: bool = True
        self._fixed_edge_y: int = 0
        self._grow_direction: str = "below"

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
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

        self._search_edit = QLineEdit(self._frame)
        self._search_edit.setPlaceholderText("Filter launchers...")
        self._search_edit.setStyleSheet(
            "QLineEdit { background: rgba(25,25,28,200); color: #ddd; border: 1px solid rgba(70,70,75,180); border-radius: 4px; padding: 3px 6px; font-size: 12px; }"
            "QLineEdit:focus { border: 1px solid rgba(90,120,180,200); }"
        )
        self._search_edit.textChanged.connect(self._apply_filter)
        self._search_edit.installEventFilter(self)

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
        self._layout.addWidget(self._search_edit)
        self._layout.addWidget(self._scroll)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._frame)

        self.hide()  # start hidden
        self.setFixedWidth(config.settings.dropdown_width)

        self._hide_timer.setInterval(140)  # small grace period

        # Respect initial show_filter_box setting
        self.refresh_filter_visibility()

    def set_width(self, width: int) -> None:
        self.setFixedWidth(width)

    def refresh_filter_visibility(self) -> None:
        """Sync whether the filter search box is shown based on current settings.
        Safe to call after the setting is toggled in Manage. Will resize if the
        dropdown is currently visible.
        """
        show = getattr(self._config.settings, "show_filter_box", True)
        if show:
            self._search_edit.show()
        else:
            self._search_edit.hide()
        if self.isVisible():
            self._update_height_for_content()

    def update_height_for_content(self) -> None:
        """Recompute and apply the correct height for the current buttons (public)."""
        self._update_height_for_content()

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

        # Add a small hint at bottom if empty
        if not launchers:
            hint = QLabel("No launchers yet.\nRight-click the arrow → Add new launcher...")
            hint.setStyleSheet("color: #888; font-size: 11px; padding: 8px;")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._button_layout.addWidget(hint)
            self._buttons.append(hint)  # type: ignore  # for cleanup

        self._update_height_for_content()
        # Re-apply any active filter after buttons change (e.g. after add/edit/manage)
        self._apply_filter(self._search_edit.text())

    def _apply_filter(self, text: str) -> None:
        """Hide non-matching buttons (by name); show matching. Then recompute height.
        Empty text shows all.
        """
        q = (text or "").strip().lower()
        for w in self._buttons:
            if isinstance(w, LaunchButton):
                match = q == "" or q in w.launcher.name.lower() or q in (w.launcher.command or "").lower()
                w.setVisible(match)
            elif isinstance(w, QLabel):
                # the empty hint label
                w.setVisible(q == "")
        self._update_height_for_content()

    def _update_height_for_content(self) -> None:
        """Compute the height required so that each button row gets its full height
        (minHeight or sizeHint) + the declared _button_layout spacing (2px) + chrome.

        We sum explicitly from the child widgets because once the _button_container
        has been set as the widget of the QScrollArea (during __init__, before
        rebuild adds children), the container's layout.minimumSize() and sizeHint()
        can report artificially low values (e.g. 68 instead of 88 for 3x28+spacings).
        Using those would cause us to set too-small fixed height on frame/scroll,
        making the inner VBox allocate too little vertical space → children get
        placed with ~20px steps; their minHeight=28 then causes overlaps/squish
        (gaps of -8 instead of +2).
        """
        # Ensure search visibility matches the latest setting (e.g. toggled from Manage while list open)
        show = getattr(self._config.settings, "show_filter_box", True)
        if show != self._search_edit.isVisible():
            if show:
                self._search_edit.show()
            else:
                self._search_edit.hide()

        self._button_container.adjustSize()
        if self._search_edit.isVisible():
            self._search_edit.adjustSize()

        # Explicit sum: robust even when hosted layout reports wrong aggregates.
        inner_h = 0
        sp = self._button_layout.spacing()
        visible_count = 0
        for w in self._buttons:
            if hasattr(w, 'isVisible') and not w.isVisible():
                continue
            if visible_count > 0:
                inner_h += sp
            if hasattr(w, 'sizeHint'):
                try:
                    sh_h = w.sizeHint().height()
                except Exception:
                    sh_h = 0
                mh = getattr(w, 'minimumHeight', lambda: 0)()
                inner_h += max(sh_h, mh, 20)
            else:
                inner_h += 20
            visible_count += 1

        m = self._layout.contentsMargins()
        frame_chrome = m.top() + m.bottom()
        layout_sp = 0
        search_h = 0
        if self._search_edit.isVisible():
            self._search_edit.adjustSize()
            search_h = self._search_edit.height() or self._search_edit.sizeHint().height() or 22
            layout_sp = self._layout.spacing()  # between search and scroll
        # The button_layout (inside container inside scroll) observes an ~8px top inset
        # (first button y≈8). To give the VBoxLayout a rect tall enough for mins + its
        # own spacing(2), we need extra on top of the pure inner_h.
        viewport_chrome = 22  # extra allowance so the inner button_layout rect is large enough for all minHeights + the full declared spacing(2) between each (previously we were 1px short per gap)
        target_h = inner_h + frame_chrome + viewport_chrome + search_h + layout_sp
        max_h = 420
        target_h = min(target_h, max_h)
        self._frame.setFixedHeight(target_h)
        self.setFixedHeight(target_h)

        # Give the inner content a minimumHeight so that when the QScrollArea (resizable)
        # is constrained by the frame's fixed height (or during/after anims), the
        # button_layout still receives enough vertical space to place children with
        # their full minHeight *and* the declared spacing(2).
        self._button_container.setMinimumHeight(inner_h)
        self._scroll.setMinimumHeight(inner_h)

        # Force layout to adopt the size so child layouts (button spacing) get the correct allocation now
        self._frame.updateGeometry()
        self.updateGeometry()

    def _on_button_clicked(self, launcher: Launcher) -> None:
        self.launch_requested.emit(launcher)
        # Note: hide decision (respecting pinned state) is now handled in main.py's on_launch

    def position_adjacent(self, trigger: QWidget) -> None:
        """Position the dropdown relative to the trigger.

        Default: below the arrow, horizontally centered on it.

        If not enough room below (near bottom of screen), flip to above.

        Horizontally shift left/right as needed so the dropdown stays fully on-screen.

        Sets internal flags (_grow_from_top, _fixed_edge_y, _grow_direction) so that
        the show/hide animations grow/shrink *away* from the screen edge (attached to the arrow).
        """
        self._anchor_trigger = trigger

        # Make sure we know our final content size for fitting calculations.
        self._update_height_for_content()

        target_w = self.width()
        target_h = self._frame.height() or 120

        # Trigger in global coordinates.
        trig_pos = trigger.mapToGlobal(QPoint(0, 0))
        trig_rect = QRect(trig_pos, trigger.size())

        # Available screen area (excludes taskbar/dock etc.).
        screen = QApplication.screenAt(trig_pos) or QApplication.primaryScreen()
        avail = screen.availableGeometry()

        overlap = 3

        # --- Preferred below + centered ---
        below_y = trig_rect.bottom() - overlap
        center_x = trig_rect.left() + (trig_rect.width() - target_w) // 2
        below_rect = QRect(center_x, below_y, target_w, target_h)

        # Horizontal clamp for below case (prefer left-align if dropdown wider than screen)
        if below_rect.right() > avail.right():
            below_rect.moveRight(avail.right())
        if below_rect.left() < avail.left():
            below_rect.moveLeft(avail.left())

        space_below = avail.bottom() - trig_rect.bottom()
        fits_below = below_rect.bottom() <= avail.bottom()

        # --- Alternative above ---
        above_y = trig_rect.top() + overlap - target_h
        above_rect = QRect(center_x, above_y, target_w, target_h)

        # Horizontal clamp for above case (prefer left-align if dropdown wider than screen)
        if above_rect.right() > avail.right():
            above_rect.moveRight(avail.right())
        if above_rect.left() < avail.left():
            above_rect.moveLeft(avail.left())

        space_above = trig_rect.top() - avail.top()
        fits_above = above_rect.top() >= avail.top()

        # Choose direction. Prefer below. Fall back to the side with more space.
        if fits_below or (not fits_above and space_below >= space_above):
            direction = "below"
            final_rect = below_rect
        else:
            direction = "above"
            final_rect = above_rect

        # Final vertical clamp (extreme cases: huge list or tiny screen)
        if final_rect.top() < avail.top():
            final_rect.moveTop(avail.top())
        if final_rect.bottom() > avail.bottom():
            final_rect.moveBottom(avail.bottom())

        # Apply position
        self.move(final_rect.topLeft())

        # Compute edge from (possibly clamped) rect so the growth origin matches
        # the actual placed position. This is used by the show/hide animations.
        if direction == "below":
            fixed_edge_y = final_rect.top()
            grow_from_top = True
        else:
            fixed_edge_y = final_rect.bottom()
            grow_from_top = False

        # Store for animations so they expand/contract away from the edge.
        self._grow_direction = direction
        self._fixed_edge_y = fixed_edge_y
        self._grow_from_top = grow_from_top

    # --- Hover handling (combined area: trigger + this panel) ---
    def enterEvent(self, event: QEvent) -> None:  # type: ignore[override]
        self._cancel_hide()
        self.hover_enter.emit()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # type: ignore[override]
        if not self._config.settings.pinned_open:
            self._schedule_hide()
        self.hover_leave.emit()
        super().leaveEvent(event)

    def _schedule_hide(self) -> None:
        if self._config.settings.pinned_open:
            return
        self._hide_timer.start()

    def _cancel_hide(self) -> None:
        self._hide_timer.stop()

    def cancel_hide(self) -> None:
        """Cancel any pending hide timer. Called from main when mouse moves from dd list back to trigger."""
        self._cancel_hide()

    def ensure_visible_and_sized(self) -> None:
        """Ensure the dropdown is visible at the correct full content height.
        Safe to call when pinned_open: prevents unwanted collapses after moves,
        resizes of trigger, or click interactions.
        """
        self._cancel_hide()
        self._update_height_for_content()
        if not self.isVisible():
            self.show()
            self.raise_()  # bring list forward (caller will raise trigger after to keep arrow on top)
            if self._anchor_trigger is not None:
                self.position_adjacent(self._anchor_trigger)
                self.raise_()
            self.setWindowOpacity(1.0)
            # Clear anim constraints so our fixed target from _update rules
            self._frame.setMinimumHeight(0)
            self._frame.setMaximumHeight(16777215)
            self._frame.updateGeometry()
            self.updateGeometry()

    def _do_hide(self) -> None:
        self.start_hide_animation()

    # --- Animations ---
    def start_show_animation(self) -> None:
        self._cancel_hide()
        self.show()
        self.raise_()
        if self._anchor_trigger is not None:
            # Re-apply the computed position *after* show(). On macOS with Frameless+Tool windows,
            # move() before the native window is created by show() can be ignored or reset; doing it
            # right after ensures the dropdown ends up at the correct y relative to the trigger.
            self.position_adjacent(self._anchor_trigger)
            self.raise_()  # re-raise list after possible re-position
        self.setFocus(Qt.FocusReason.OtherFocusReason)  # allow Esc key

        # Ensure we have an accurate target height (buttons + proper spacings) before
        # capturing end_h for the grow animation. Prevents growing to a squished/too-small value.
        self._update_height_for_content()

        # Relax the mins we put on the hosted scroll/content so the frame can start the
        # animation from a small height (8) without the child's minSize fighting the layout.
        self._button_container.setMinimumHeight(0)
        self._scroll.setMinimumHeight(0)

        start_h = 8
        end_h = self._frame.height()

        # Decide starting geometry based on grow direction so the panel "grows away"
        # from the screen edge while staying attached to the arrow.
        grow_from_top = getattr(self, "_grow_from_top", True)
        fixed_edge = getattr(self, "_fixed_edge_y", self.y())

        if grow_from_top:
            # Below: top edge fixed at the attachment point. Grow downward.
            self.move(self.x(), fixed_edge)
            self._frame.setFixedHeight(start_h)
            self.setWindowOpacity(0.0)
            pos_anim = None
        else:
            # Above: bottom edge fixed at the attachment point. Grow upward.
            # Start small with its bottom at the fixed edge.
            init_y = fixed_edge - start_h
            self.move(self.x(), init_y)
            self._frame.setFixedHeight(start_h)
            self.setWindowOpacity(0.0)
            # We also need to animate the y position upward as height grows.
            final_y = fixed_edge - end_h
            pos_anim = QPropertyAnimation(self, b"pos", self)
            pos_anim.setDuration(self._config.settings.animation_duration_ms)
            pos_anim.setStartValue(QPoint(self.x(), init_y))
            pos_anim.setEndValue(QPoint(self.x(), final_y))
            pos_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # We animate the height of the frame + opacity of whole widget
        # (and optionally the pos for above case)
        self._frame.setMaximumHeight(end_h)

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

        def on_finished():
            self._frame.setMinimumHeight(0)
            self._frame.setMaximumHeight(16777215)
            self._frame.setFixedHeight(end_h)
            self.setWindowOpacity(1.0)
            # Restore proper mins for the content now that we are at full open height.
            # This re-enables the "don't squish my spacings" protection.
            self._update_height_for_content()

        height_anim.finished.connect(on_finished)

        self._animation = anim  # keep ref
        anim.start()
        height_anim.start()
        if pos_anim is not None:
            pos_anim.start()

    def start_hide_animation(self) -> None:
        if self._config.settings.pinned_open:
            return
        if not self.isVisible():
            return

        # Relax content mins so the shrink animation on the frame can go all the way down
        # (otherwise child's minSize may prevent the layout from making the frame as small as 6).
        self._button_container.setMinimumHeight(0)
        self._scroll.setMinimumHeight(0)

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

        # For "above" mode we also animate the position so the bottom edge stays fixed
        # to the arrow while the panel shrinks upward.
        pos_anim = None
        grow_from_top = getattr(self, "_grow_from_top", True)
        if not grow_from_top:
            fixed_bottom = getattr(self, "_fixed_edge_y", self.y() + current_h)
            curr_y = self.y()
            end_y = fixed_bottom - 6
            pos_anim = QPropertyAnimation(self, b"pos", self)
            pos_anim.setDuration(int(self._config.settings.animation_duration_ms * 0.7))
            pos_anim.setStartValue(QPoint(self.x(), curr_y))
            pos_anim.setEndValue(QPoint(self.x(), end_y))
            pos_anim.setEasingCurve(QEasingCurve.Type.InCubic)

        def on_finished():
            self._search_edit.clear()
            self.hide()
            self.setWindowOpacity(1.0)
            self._frame.setMinimumHeight(0)
            self._frame.setMaximumHeight(16777215)
            self._frame.setFixedHeight(self._frame.sizeHint().height() or 120)

        height_anim.finished.connect(on_finished)

        self._animation = anim
        anim.start()
        height_anim.start()
        if pos_anim is not None:
            pos_anim.start()

    def force_hide(self) -> None:
        """Immediate hide (used on launch or escape)."""
        self._cancel_hide()
        self._search_edit.clear()
        self.hide()
        self.setWindowOpacity(1.0)
        # Reset to default "below" behavior for next time.
        self._grow_from_top = True
        self._fixed_edge_y = 0
        self._grow_direction = "below"

    def keyPressEvent(self, event):  # type: ignore[override]
        if event.key() == Qt.Key.Key_Escape:
            if self._search_edit.text():
                self._search_edit.clear()
                event.accept()
                return
            if not self._config.settings.pinned_open:
                self.force_hide()
            event.accept()
        else:
            super().keyPressEvent(event)

    def eventFilter(self, obj, event):  # type: ignore[override]
        if obj is self._search_edit and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                if self._search_edit.text():
                    self._search_edit.clear()
                    return True
        return super().eventFilter(obj, event)
