"""Three color schemes for the floating arrow, lists, and highlights.

Dark is the original look: dark surfaces and yellow highlights. Medium sits
between the other two. Bright uses beige surfaces and amber highlights.

Widgets read `current()` when they paint or apply a stylesheet. Call `use()`
before creating widgets, and again before asking open widgets to restyle.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ColorScheme:
    """One complete palette. Stylesheet helpers fill these tokens into the Qt rules."""

    id: str
    label: str
    trigger_fill: tuple[int, int, int, int]
    trigger_chevron: tuple[int, int, int, int]
    frame_bg: str
    frame_border: str
    heading_fg: str
    search_bg: str
    search_fg: str
    search_border: str
    search_focus: str
    scroll_handle: str
    hint_fg: str
    row_bg: str
    row_fg: str
    row_border: str
    hover_bg: str
    hover_fg: str
    hover_border: str
    pressed_bg: str
    pressed_fg: str
    selected_bg: str
    selected_fg: str
    selected_border: str
    selected_hover_bg: str
    selected_hover_fg: str
    selected_hover_border: str
    drag_bg: str
    drag_fg: str
    drag_border: str
    submenu_bg: str
    submenu_border: str
    submenu_drag_bg: str
    toggle_on: tuple[int, int, int]
    toggle_on_border: tuple[int, int, int]
    toggle_off: tuple[int, int, int]
    toggle_off_border: tuple[int, int, int]
    toggle_knob: tuple[int, int, int]
    toggle_knob_ring: tuple[int, int, int, int]
    dialog_drag_border: str
    dialog_selected_bg: str
    dialog_selected_fg: str
    tray_icon: str


# The shipped look. Tokens match the stylesheets this scheme replaced.
DARK = ColorScheme(
    id="dark",
    label="Dark",
    trigger_fill=(30, 30, 30, 170),
    trigger_chevron=(230, 230, 230, 210),
    frame_bg="rgba(35, 35, 38, 245)",
    frame_border="rgba(80, 80, 85, 200)",
    heading_fg="#b4b4ba",
    search_bg="rgba(25, 25, 28, 200)",
    search_fg="#ddd",
    search_border="rgba(70, 70, 75, 180)",
    search_focus="rgba(90, 120, 180, 200)",
    scroll_handle="rgba(120, 120, 125, 160)",
    hint_fg="#888",
    row_bg="rgba(55, 55, 60, 200)",
    row_fg="#eee",
    row_border="rgba(90, 90, 95, 180)",
    hover_bg="rgba(70, 110, 170, 210)",
    hover_fg="#eee",
    hover_border="rgba(100, 140, 200, 220)",
    pressed_bg="rgba(50, 85, 140, 230)",
    pressed_fg="#eee",
    selected_bg="rgba(65, 95, 145, 225)",
    selected_fg="#eee",
    selected_border="rgba(120, 160, 220, 240)",
    selected_hover_bg="rgba(75, 115, 175, 230)",
    selected_hover_fg="#eee",
    selected_hover_border="rgba(130, 170, 230, 250)",
    drag_bg="rgba(80, 120, 180, 235)",
    drag_fg="#eee",
    drag_border="rgba(255, 220, 70, 240)",
    submenu_bg="rgba(48, 52, 64, 210)",
    submenu_border="rgba(90, 100, 120, 180)",
    submenu_drag_bg="rgba(70, 110, 170, 235)",
    toggle_on=(70, 110, 170),
    toggle_on_border=(90, 130, 190),
    toggle_off=(70, 70, 75),
    toggle_off_border=(95, 95, 100),
    toggle_knob=(245, 245, 247),
    toggle_knob_ring=(200, 200, 205, 120),
    dialog_drag_border="#ffd600",
    dialog_selected_bg="#3c3c3c",
    dialog_selected_fg="#f2f2f2",
    tray_icon="#0a84ff",
)

# Warm beige surfaces and amber highlights. Light enough to read as bright,
# with sand and tan in place of white.
BRIGHT = ColorScheme(
    id="bright",
    label="Bright",
    trigger_fill=(214, 156, 64, 240),
    trigger_chevron=(62, 40, 16, 245),
    frame_bg="rgba(228, 204, 160, 248)",
    frame_border="rgba(176, 132, 68, 230)",
    heading_fg="#5a3e22",
    search_bg="rgba(214, 186, 138, 235)",
    search_fg="#3a2a18",
    search_border="rgba(168, 128, 72, 215)",
    search_focus="rgba(176, 108, 32, 230)",
    scroll_handle="rgba(168, 124, 64, 185)",
    hint_fg="#6a5030",
    row_bg="rgba(242, 222, 186, 242)",
    row_fg="#3a2a18",
    row_border="rgba(186, 148, 96, 215)",
    hover_bg="rgba(214, 156, 64, 242)",
    hover_fg="#3a2a18",
    hover_border="rgba(160, 108, 36, 245)",
    pressed_bg="rgba(196, 136, 48, 246)",
    pressed_fg="#2a1c0c",
    selected_bg="rgba(255, 210, 146, 245)",
    selected_fg="#3a2a18",
    selected_border="rgba(176, 120, 44, 240)",
    selected_hover_bg="rgba(214, 156, 64, 246)",
    selected_hover_fg="#3a2a18",
    selected_hover_border="rgba(160, 108, 36, 250)",
    drag_bg="rgba(255, 198, 102, 250)",
    drag_fg="#3a2a18",
    drag_border="rgba(176, 96, 24, 255)",
    submenu_bg="rgba(214, 186, 138, 242)",
    submenu_border="rgba(160, 120, 64, 220)",
    submenu_drag_bg="rgba(255, 198, 102, 250)",
    toggle_on=(196, 132, 48),
    toggle_on_border=(214, 156, 64),
    toggle_off=(206, 184, 150),
    toggle_off_border=(168, 142, 104),
    toggle_knob=(255, 236, 206),
    toggle_knob_ring=(196, 154, 96, 160),
    dialog_drag_border="#d4892a",
    dialog_selected_bg="#f0d7a8",
    dialog_selected_fg="#3a2a14",
    tray_icon="#e09a3a",
)

# Mid gray, dusty blue, and muted gold. Less contrast than Dark, less chroma
# than Bright, so it can sit on a patterned desktop without taking over.
MEDIUM = ColorScheme(
    id="medium",
    label="Medium",
    trigger_fill=(92, 98, 112, 220),
    trigger_chevron=(248, 244, 232, 235),
    frame_bg="rgba(78, 82, 94, 242)",
    frame_border="rgba(138, 144, 158, 205)",
    heading_fg="#e4e5ea",
    search_bg="rgba(62, 66, 76, 225)",
    search_fg="#eeeeee",
    search_border="rgba(124, 130, 142, 185)",
    search_focus="rgba(186, 156, 96, 220)",
    scroll_handle="rgba(176, 180, 190, 175)",
    hint_fg="#d8d9de",
    row_bg="rgba(104, 110, 124, 225)",
    row_fg="#f3f3f5",
    row_border="rgba(150, 156, 170, 190)",
    hover_bg="rgba(90, 118, 142, 232)",
    hover_fg="#ffffff",
    hover_border="rgba(156, 180, 200, 225)",
    pressed_bg="rgba(72, 96, 118, 238)",
    pressed_fg="#f4f6f8",
    selected_bg="rgba(112, 134, 156, 232)",
    selected_fg="#f7f8fa",
    selected_border="rgba(170, 190, 208, 230)",
    selected_hover_bg="rgba(90, 118, 142, 238)",
    selected_hover_fg="#ffffff",
    selected_hover_border="rgba(176, 198, 216, 240)",
    drag_bg="rgba(78, 96, 114, 242)",
    drag_fg="#fff8ea",
    drag_border="rgba(212, 176, 96, 245)",
    submenu_bg="rgba(90, 98, 114, 225)",
    submenu_border="rgba(140, 150, 166, 190)",
    submenu_drag_bg="rgba(78, 96, 114, 242)",
    toggle_on=(118, 146, 168),
    toggle_on_border=(150, 174, 192),
    toggle_off=(100, 104, 114),
    toggle_off_border=(132, 136, 146),
    toggle_knob=(236, 236, 238),
    toggle_knob_ring=(190, 192, 198, 120),
    dialog_drag_border="#c6a35e",
    dialog_selected_bg="#5e6574",
    dialog_selected_fg="#f4f4f6",
    tray_icon="#7f96ab",
)

SCHEMES: tuple[ColorScheme, ...] = (DARK, MEDIUM, BRIGHT)
_BY_ID = {scheme.id: scheme for scheme in SCHEMES}

_LAUNCH_QSS = """
QPushButton {{
    background-color: {row_bg};
    color: {row_fg};
    border: 1px solid {row_border};
    border-radius: 5px;
    padding: 4px 10px;
    text-align: left;
    font-size: 13px;
}}
QPushButton:hover {{
    background-color: {hover_bg};
    color: {hover_fg};
    border: 1px solid {hover_border};
}}
QPushButton:pressed {{
    background-color: {pressed_bg};
    color: {pressed_fg};
}}
QPushButton[kbSelected="true"] {{
    background-color: {selected_bg};
    color: {selected_fg};
    border: 1px solid {selected_border};
}}
QPushButton[kbSelected="true"]:hover {{
    background-color: {selected_hover_bg};
    color: {selected_hover_fg};
    border: 1px solid {selected_hover_border};
}}
QPushButton[dragging="true"],
QPushButton[dragging="true"]:hover,
QPushButton[dragging="true"]:pressed,
QPushButton[kbSelected="true"][dragging="true"],
QPushButton[kbSelected="true"][dragging="true"]:hover,
QPushButton[kbSelected="true"][dragging="true"]:pressed {{
    background-color: {drag_bg};
    color: {drag_fg};
    border: 4px solid {drag_border};
    border-radius: 6px;
    padding: 1px 7px;
}}
"""

_SUBMENU_QSS = """
QPushButton {{
    background-color: {submenu_bg};
    color: {row_fg};
    border: 1px solid {submenu_border};
    border-radius: 5px;
    padding: 4px 10px;
    text-align: left;
    font-size: 13px;
}}
QPushButton:hover {{
    background-color: {hover_bg};
    color: {hover_fg};
    border: 1px solid {hover_border};
}}
QPushButton[dragging="true"],
QPushButton[dragging="true"]:hover,
QPushButton[dragging="true"]:pressed {{
    background-color: {submenu_drag_bg};
    color: {drag_fg};
    border: 4px solid {drag_border};
    border-radius: 6px;
    padding: 1px 7px;
}}
"""

_current: ColorScheme = DARK


def resolve(scheme_id: str | None) -> ColorScheme:
    """The scheme for a saved id. Missing and unknown ids use Dark."""
    if not scheme_id:
        return DARK
    return _BY_ID.get(scheme_id, DARK)


def with_opacity(color: tuple[int, int, int, int], percent: int) -> tuple[int, int, int, int]:
    """`color` with its alpha replaced by a 0-100 percent. Below 0, the alpha stays."""
    if percent < 0:
        return color
    clamped = max(0, min(100, int(percent)))
    return (color[0], color[1], color[2], int(round(clamped * 255 / 100)))


def current() -> ColorScheme:
    return _current


def use(scheme_id: str | None) -> ColorScheme:
    """Make `scheme_id` the palette widgets read. Unknown ids use Dark."""
    global _current
    _current = resolve(scheme_id)
    return _current


def _pick(scheme: ColorScheme | None) -> ColorScheme:
    return current() if scheme is None else scheme


def launch_button_qss(scheme: ColorScheme | None = None) -> str:
    return _LAUNCH_QSS.format(**asdict(_pick(scheme)))


def submenu_qss(scheme: ColorScheme | None = None) -> str:
    return _SUBMENU_QSS.format(**asdict(_pick(scheme)))


def frame_qss(scheme: ColorScheme | None = None) -> str:
    scheme = _pick(scheme)
    return (
        "QFrame {"
        f" background-color: {scheme.frame_bg};"
        f" border: 1px solid {scheme.frame_border};"
        " border-radius: 8px;"
        "}"
    )


def heading_qss(scheme: ColorScheme | None = None) -> str:
    scheme = _pick(scheme)
    return (
        "QLabel#listHeading {"
        f" color: {scheme.heading_fg};"
        " font-size: 11px;"
        " background: transparent;"
        " border: none;"
        " padding: 0px 2px 0px 2px;"
        "}"
    )


def search_qss(scheme: ColorScheme | None = None) -> str:
    scheme = _pick(scheme)
    return (
        "QLineEdit {"
        f" background: {scheme.search_bg};"
        f" color: {scheme.search_fg};"
        f" border: 1px solid {scheme.search_border};"
        " border-radius: 4px;"
        " padding: 3px 6px;"
        " font-size: 12px;"
        "}"
        "QLineEdit:focus {"
        f" border: 1px solid {scheme.search_focus};"
        "}"
    )


def scroll_qss(scheme: ColorScheme | None = None) -> str:
    scheme = _pick(scheme)
    return (
        "QScrollArea { background: transparent; border: none; }"
        "QScrollBar:vertical { width: 6px; background: transparent; }"
        "QScrollBar::handle:vertical {"
        f" background: {scheme.scroll_handle};"
        " border-radius: 3px;"
        "}"
    )


def hint_qss(scheme: ColorScheme | None = None) -> str:
    scheme = _pick(scheme)
    return f"color: {scheme.hint_fg}; font-size: 11px; padding: 8px;"


def ghost_qss(scheme: ColorScheme | None = None) -> str:
    scheme = _pick(scheme)
    return (
        "QLabel {"
        f" background-color: {scheme.drag_bg};"
        f" color: {scheme.drag_fg};"
        f" border: 4px solid {scheme.drag_border};"
        " border-radius: 6px;"
        " padding: 1px 7px;"
        " font-size: 13px;"
        "}"
    )
