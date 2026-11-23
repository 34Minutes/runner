"""Three color schemes for the floating arrow, lists, and highlights.

Dark is the original look: dark surfaces and yellow highlights. Medium sits
between the other two. Bright uses beige surfaces and amber highlights.

Widgets read `current()` when they paint or apply a stylesheet. Call `use()`
before creating widgets, and again before asking open widgets to restyle.
"""

from __future__ import annotations

import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path


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
    dialog_selected_bg="#415f91",
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
    dialog_selected_bg="#ffd292",
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
    dialog_selected_bg="#70869c",
    dialog_selected_fg="#f7f8fa",
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


# ------------------------------------------------------------- dialogs
#
# Add, Edit, and Manage windows, message boxes, and the schedule pickers use
# the same surfaces as the lists: the list frame as the window, the search
# box for fields, the list rows for buttons, and the list's highlight for
# the default button and selection. Everything is solid; a see-through
# window would show the desktop through a form.


def _channels(colour: str) -> tuple[int, int, int]:
    """(r, g, b) from '#rgb', '#rrggbb', or 'rgb(a)(r, g, b[, a])'."""
    if colour.startswith("#"):
        digits = colour[1:]
        if len(digits) == 3:
            digits = "".join(c * 2 for c in digits)
        return int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16)
    r, g, b = (int(n) for n in re.findall(r"\d+", colour)[:3])
    return r, g, b


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def solid(colour: str) -> str:
    """The colour without its transparency, as #rrggbb."""
    return _hex(_channels(colour))


def mix(a: str, b: str, t: float) -> str:
    """t of the way from colour a to colour b, as #rrggbb."""
    ca, cb = _channels(a), _channels(b)
    return _hex(tuple(round(x + (y - x) * t) for x, y in zip(ca, cb)))  # type: ignore[arg-type]


@dataclass(frozen=True)
class DialogColors:
    window: str
    text: str
    muted: str
    disabled: str
    field: str
    field_alt: str
    field_border: str
    focus: str
    button: str
    button_border: str
    button_hover: str
    button_hover_text: str
    default: str
    default_border: str
    default_text: str
    selection: str
    selection_text: str
    check: str
    check_mark: str
    scroll_handle: str


def dialog_colors(scheme: ColorScheme | None = None) -> DialogColors:
    scheme = _pick(scheme)
    window = solid(scheme.frame_bg)
    field = solid(scheme.search_bg)
    return DialogColors(
        window=window,
        text=solid(scheme.row_fg),
        muted=solid(scheme.hint_fg),
        # Hint text is close to the text in Medium and Bright. Disabled has
        # to read as off at a glance, so it sits well toward the window.
        disabled=mix(window, solid(scheme.row_fg), 0.42),
        field=field,
        field_alt=mix(field, solid(scheme.row_bg), 0.35),
        field_border=solid(scheme.search_border),
        focus=solid(scheme.search_focus),
        button=solid(scheme.row_bg),
        button_border=solid(scheme.row_border),
        button_hover=solid(scheme.hover_bg),
        button_hover_text=solid(scheme.hover_fg),
        default=solid(scheme.selected_bg),
        default_border=solid(scheme.selected_border),
        default_text=solid(scheme.selected_fg),
        selection=scheme.dialog_selected_bg,
        selection_text=scheme.dialog_selected_fg,
        check=_hex(scheme.toggle_on),
        check_mark=_hex(scheme.toggle_knob),
        scroll_handle=solid(scheme.scroll_handle),
    )


def _icon_file(name: str, svg: str) -> str:
    """Write a small SVG once and return its path for a stylesheet url()."""
    folder = Path(tempfile.gettempdir()) / "runner-ui-icons"
    path = folder / name
    if not path.exists():
        folder.mkdir(parents=True, exist_ok=True)
        path.write_text(svg, encoding="utf-8")
    return path.as_posix()


def check_icon(colour: str) -> str:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 14 14">'
        f'<path d="M3 7.4 L5.8 10.1 L11 4" fill="none" stroke="{colour}" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round"/></svg>'
    )
    return _icon_file(f"check-{colour.lstrip('#')}.svg", svg)


_DIALOG_QSS = """
QDialog, QMessageBox {{ background: {window}; color: {text}; }}
QLabel, QCheckBox {{ color: {text}; background: transparent; }}
QLabel:disabled, QCheckBox:disabled {{ color: {disabled}; }}
QToolTip {{ background: {field}; color: {text}; border: 1px solid {field_border}; padding: 4px; }}

QLineEdit {{
    background: {field}; color: {text}; border: 1px solid {field_border};
    border-radius: 5px; padding: 4px 6px; selection-background-color: {selection};
    selection-color: {selection_text};
}}
QLineEdit:focus {{ border: 1px solid {focus}; }}
QLineEdit:disabled {{ color: {disabled}; }}

QPushButton {{
    background: {button}; color: {text}; border: 1px solid {button_border};
    border-radius: 6px; padding: 5px 14px; min-height: 18px;
}}
QPushButton:hover {{ background: {button_hover}; color: {button_hover_text}; border-color: {default_border}; }}
QPushButton:pressed {{ background: {default}; color: {default_text}; }}
QPushButton:default {{ background: {default}; color: {default_text}; border-color: {default_border}; }}
QPushButton:default:hover {{ background: {button_hover}; color: {button_hover_text}; }}
QPushButton:disabled {{ background: {window}; color: {disabled}; border-color: {field_border}; }}
QPushButton:focus {{ outline: none; }}

QListWidget, QTableWidget, QScrollArea, QAbstractScrollArea {{
    background: {field}; alternate-background-color: {field_alt}; color: {text};
    border: 1px solid {field_border}; border-radius: 5px;
    selection-background-color: {selection}; selection-color: {selection_text};
    outline: none;
}}
QListWidget::item {{ padding: 4px 6px; }}
QListWidget::item:selected {{ background: {selection}; color: {selection_text}; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QHeaderView {{ background: {window}; border: none; }}
QHeaderView::section {{
    background: {button}; color: {text}; border: none;
    border-right: 1px solid {field_border}; border-bottom: 1px solid {field_border};
    padding: 5px 8px;
}}
QTableCornerButton::section {{ background: {button}; border: none; }}

ToggleSwitch {{ color: {text}; }}
ToggleSwitch:disabled {{ color: {disabled}; }}

QCheckBox {{ spacing: 8px; }}
QListWidget::indicator {{
    width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid {button_border}; background: {field};
}}
QListWidget::indicator:checked {{ background: {check}; border-color: {check}; image: url({check_url}); }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid {button_border}; background: {field};
}}
QCheckBox::indicator:hover {{ border-color: {focus}; }}
QCheckBox::indicator:checked {{ background: {check}; border-color: {check}; image: url({check_url}); }}
QCheckBox::indicator:disabled {{ background: {window}; border-color: {field_border}; }}

QScrollBar:vertical {{ width: 10px; background: transparent; margin: 2px; }}
QScrollBar:horizontal {{ height: 10px; background: transparent; margin: 2px; }}
QScrollBar::handle {{ background: {scroll_handle}; border-radius: 3px; min-height: 24px; min-width: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
"""


def dialog_qss(scheme: ColorScheme | None = None) -> str:
    colors = dialog_colors(scheme)
    return _DIALOG_QSS.format(**asdict(colors), check_url=check_icon(colors.check_mark))


def dialog_palette(base, scheme: ColorScheme | None = None):
    """base (a QPalette) recoloured for a dialog, for widgets that paint from the palette."""
    from PySide6.QtGui import QColor, QPalette

    colors = dialog_colors(scheme)
    palette = QPalette(base)
    role = QPalette.ColorRole
    for name, value in (
        (role.Window, colors.window),
        (role.WindowText, colors.text),
        (role.Base, colors.field),
        (role.AlternateBase, colors.field_alt),
        (role.Text, colors.text),
        (role.Button, colors.button),
        (role.ButtonText, colors.text),
        (role.Highlight, colors.selection),
        (role.HighlightedText, colors.selection_text),
        (role.ToolTipBase, colors.field),
        (role.ToolTipText, colors.text),
        (role.PlaceholderText, colors.muted),
        (role.Mid, colors.field_border),
        (role.Midlight, colors.button_border),
    ):
        palette.setColor(name, QColor(value))
    disabled = QPalette.ColorGroup.Disabled
    for name in (role.WindowText, role.Text, role.ButtonText):
        palette.setColor(disabled, name, QColor(colors.disabled))
    return palette


def style_dialog(widget) -> None:
    """Give a dialog or message box the active scheme's colours."""
    # Style sheet first, and polished now: the first polish with a style
    # sheet puts back the palette the widget had before it, which would undo
    # a palette set earlier.
    widget.setStyleSheet(dialog_qss())
    widget.ensurePolished()
    widget.setPalette(dialog_palette(widget.palette()))
