"""Central theme palette — single source of truth for the colours
custom-painted widgets and QSS-based dialogs use.

Three variants (dark / light / high_contrast) defined as colour-key
dicts. Widgets read the active palette via ``color(key)`` /
``qcolor(key)`` and register themselves for refresh callbacks via
``register_listener(callback)`` — when the user switches themes
through File > Customize, every registered listener is invoked so
custom-painted widgets can re-render with the new colours.

Usage pattern for a custom-painted widget:

    from .theme_palette import color, qcolor, register_listener

    class MyWidget(QtWidgets.QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            register_listener(self._on_theme_changed)

        def _on_theme_changed(self):
            self.update()  # trigger repaint

        def paintEvent(self, event):
            painter = QtGui.QPainter(self)
            painter.setBrush(qcolor('bg_panel'))
            ...

For QSS-based dialogs (help, customize), call ``build_dialog_qss()``
to rebuild the stylesheet from the active palette.
"""
from __future__ import annotations

from typing import Callable, Dict, List

from PySide6 import QtGui


# ──────────────────────────────────────────────────────────────────────
# Palette definitions
# ──────────────────────────────────────────────────────────────────────
# Keys grouped by purpose:
#   bg          — main window background
#   bg_panel    — secondary panel background (cards, dialogs)
#   border      — neutral border colour
#   text        — body text
#   muted       — secondary / hint text
#   accent      — primary accent (green in dark, similar in light,
#                 yellow in high contrast for accessibility)
#   accent_text — text colour to use ON the accent background
#   chart_*     — colours used by chart widgets
#   warn / error — validation status (kept yellow/red across themes
#                  because they're semantic)

PALETTES: Dict[str, Dict[str, str]] = {
    'dark': {
        'bg': '#0c1622',
        'bg_panel': '#13202f',
        'bg_input': '#1a2532',
        'border': '#314153',
        'text': '#cdd6e0',
        'muted': '#9da7b0',
        'accent': '#73c686',
        'accent_text': '#0c1622',
        'accent_hover': '#8bd599',
        # Chart colours
        'chart_bg': '#0c1622',
        'chart_grid': '#314153',
        'chart_torque': '#73c686',     # green
        'chart_hp': '#5fa9d9',         # blue
        'chart_street': '#73c686',
        'chart_offroad': '#d9a13a',    # gold
        'chart_primary': '#5fa9d9',
        'chart_text': '#9da7b0',
        # Custom widget bars / fills
        'profile_bar_track': '#1a2532',
        'profile_bar_fill': '#5fa9d9',
        # Notice banner (compat warning)
        'notice_bg': '#3a2a18',
        'notice_text': '#f5c98e',
        'notice_border': '#5a3a1a',
        # Semantic status (intentionally same across themes —
        # red = error, yellow = warn — meaning shouldn't shift
        # by theme).
        'warn': '#d9a13a',
        'error': '#d44848',
    },
    'light': {
        'bg': '#f1f3f6',
        'bg_panel': '#ffffff',
        'bg_input': '#ffffff',
        'border': '#c8d0d9',
        'text': '#1c2330',
        'muted': '#6b7785',
        'accent': '#2a8540',           # darker green for contrast on light
        'accent_text': '#ffffff',
        'accent_hover': '#3aa055',
        'chart_bg': '#ffffff',
        'chart_grid': '#d4dae3',
        'chart_torque': '#2a8540',
        'chart_hp': '#1e6da3',
        'chart_street': '#2a8540',
        'chart_offroad': '#a06800',
        'chart_primary': '#1e6da3',
        'chart_text': '#6b7785',
        'profile_bar_track': '#e7ecf2',
        'profile_bar_fill': '#1e6da3',
        'notice_bg': '#fff3e0',
        'notice_text': '#7a4a00',
        'notice_border': '#d9a13a',
        'warn': '#b87900',
        'error': '#c0392b',
    },
    'high_contrast': {
        'bg': '#000000',
        'bg_panel': '#000000',
        'bg_input': '#000000',
        'border': '#ffffff',
        'text': '#ffffff',
        'muted': '#cccccc',
        'accent': '#ffff00',
        'accent_text': '#000000',
        'accent_hover': '#ffffaa',
        'chart_bg': '#000000',
        'chart_grid': '#ffffff',
        'chart_torque': '#00ff00',
        'chart_hp': '#00ffff',
        'chart_street': '#00ff00',
        'chart_offroad': '#ffff00',
        'chart_primary': '#00ffff',
        'chart_text': '#ffffff',
        'profile_bar_track': '#1a1a1a',
        'profile_bar_fill': '#ffff00',
        'notice_bg': '#000000',
        'notice_text': '#ffff00',
        'notice_border': '#ffff00',
        # In high contrast we keep semantic colours but brighten
        # them so they pop against pure black.
        'warn': '#ffff00',
        'error': '#ff5555',
    },
}


# ──────────────────────────────────────────────────────────────────────
# Active palette + listener registry
# ──────────────────────────────────────────────────────────────────────
_active_name: str = 'dark'
_listeners: List[Callable[[], None]] = []


def active() -> str:
    """Return the currently-active palette name."""
    return _active_name


def set_active(name: str) -> None:
    """Switch the active palette and notify every registered listener
    so custom-painted widgets can repaint. No-op if *name* isn't a
    known palette."""
    global _active_name
    if name not in PALETTES:
        return
    if name == _active_name:
        return
    _active_name = name
    for cb in list(_listeners):
        try:
            cb()
        except Exception:
            # Listener failures shouldn't take down the theme switch.
            pass


def color(key: str) -> str:
    """Return the hex colour string for *key* in the active palette.
    Falls back to the dark palette's value if the key is unknown."""
    p = PALETTES.get(_active_name) or PALETTES['dark']
    return p.get(key) or PALETTES['dark'].get(key, '#000000')


def qcolor(key: str) -> QtGui.QColor:
    """Return a QColor for *key* in the active palette."""
    return QtGui.QColor(color(key))


def register_listener(callback: Callable[[], None]) -> None:
    """Register *callback* to be invoked when the active palette
    changes. Safe to call multiple times — duplicates are kept (each
    callback fires once per registration)."""
    _listeners.append(callback)


def unregister_listener(callback: Callable[[], None]) -> None:
    """Remove *callback* from the listener list. Safe to call even
    when the callback isn't registered."""
    while callback in _listeners:
        _listeners.remove(callback)


# ──────────────────────────────────────────────────────────────────────
# QSS builder for dialogs that need to rebuild their stylesheet on
# theme change. Centralises the shared dialog look so help_dialog and
# customize_dialog can share it.
# ──────────────────────────────────────────────────────────────────────
def build_dialog_qss(ui_scale: float = 1.0) -> str:
    """Return a QSS string for modal popup dialogs (Help, Customize),
    built from the active palette. Re-run after theme OR scale changes.

    ``ui_scale`` is multiplied into every px-based font and metric
    so the dialog respects the user's UI scale preference. Without
    this, the dialog stays at the hardcoded base size while the rest
    of the app grows.
    """
    s = max(0.5, float(ui_scale or 1.0))
    # Scaled font sizes (px) — we use px in dialog QSS because pt
    # is already scaled by app.setFont() and would compound.
    fs_title    = int(round(18 * s))
    fs_section  = int(round(13 * s))
    fs_body     = int(round(12 * s))
    fs_hint     = int(round(11 * s))
    fs_browser  = int(round(13 * s))
    # Scaled metric sizes — combo height grows so larger scales are
    # actually clickable.
    combo_h     = int(round(22 * s))
    radio_box   = int(round(14 * s))
    radio_r     = max(1, radio_box // 2)
    arrow_w     = int(round(20 * s))
    arrow_size  = int(round(8 * s))
    # Pre-build the SVG down-arrow inline so the dropdown indicator
    # is always visible and themed (Qt hides its default arrow as
    # soon as we style any QComboBox subcontrol).
    arrow_color = color('text').lstrip('#')
    return f"""
QDialog {{
    background-color: {color('bg')};
    color: {color('text')};
}}
QLabel {{ color: {color('text')}; background: transparent; }}
QLabel[role="dialogTitle"] {{
    font-size: {fs_title}px;
    font-weight: 700;
    padding-bottom: 4px;
}}
QLabel[role="dialogSubtitle"] {{
    color: {color('muted')};
    font-size: {fs_body}px;
    padding-bottom: 8px;
}}
QLabel[role="sectionHeader"] {{
    color: {color('text')};
    font-size: {fs_section}px;
    font-weight: 600;
    padding-top: 10px;
}}
QLabel[role="hint"] {{
    color: {color('muted')};
    font-size: {fs_hint}px;
    padding: 2px 0 8px 0;
}}
QGroupBox {{
    background: {color('bg_panel')};
    color: {color('text')};
    border: 1px solid {color('border')};
    border-radius: 5px;
    margin-top: 14px;
    padding: 14px 12px 12px 12px;
    font-size: {fs_section}px;
    font-weight: 600;
}}
QGroupBox::title {{
    /* Float the title over the top border. Background MUST match
       the dialog background (not panel), otherwise the title sits
       on a different colour from what's underneath the border, which
       is what made it look like a black/yellow box in light/HC. */
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    top: 0px;
    padding: 0 8px;
    background-color: {color('bg')};
    color: {color('text')};
    font-weight: 600;
}}
QLineEdit {{
    background: {color('bg_input')};
    color: {color('text')};
    border: 1px solid {color('border')};
    border-radius: 4px;
    padding: 6px 10px;
    font-size: {fs_body}px;
}}
QLineEdit:focus {{ border-color: {color('accent')}; }}
QTreeWidget {{
    background: {color('bg_panel')};
    color: {color('text')};
    border: 1px solid {color('border')};
    border-radius: 4px;
    padding: 4px;
    font-size: {fs_body}px;
    show-decoration-selected: 1;
}}
QTreeWidget::item {{
    padding: 6px 4px;
    border-radius: 3px;
}}
QTreeWidget::item:hover {{
    background: rgba(115, 198, 134, 0.10);
}}
QTreeWidget::item:selected {{
    background: {color('accent')};
    color: {color('accent_text')};
}}
QTextBrowser {{
    background: {color('bg_panel')};
    color: {color('text')};
    border: 1px solid {color('border')};
    border-radius: 4px;
    padding: 14px 18px;
    font-size: {fs_browser}px;
}}
QRadioButton {{
    color: {color('text')};
    padding: 4px 0;
    font-size: {fs_body}px;
}}
QRadioButton::indicator {{
    width: {radio_box}px; height: {radio_box}px;
    border: 1px solid {color('border')};
    border-radius: {radio_r}px;
    background: {color('bg_input')};
}}
QRadioButton::indicator:checked {{
    background: {color('accent')};
    border: 1px solid {color('accent')};
}}
QCheckBox {{
    color: {color('text')};
    padding: 4px 0;
    font-size: {fs_body}px;
}}
QCheckBox::indicator {{
    width: {radio_box}px; height: {radio_box}px;
    border: 1px solid {color('border')};
    border-radius: 3px;
    background: {color('bg_input')};
}}
QCheckBox::indicator:checked {{
    background: {color('accent')};
    border: 1px solid {color('accent')};
}}
QComboBox {{
    background: {color('bg_input')};
    color: {color('text')};
    border: 1px solid {color('border')};
    border-radius: 4px;
    padding: 5px 10px;
    padding-right: {arrow_w + 4}px;
    min-height: {combo_h}px;
    font-size: {fs_body}px;
}}
QComboBox:hover {{ border-color: {color('accent')}; }}
QComboBox:focus {{ border-color: {color('accent')}; }}
QComboBox::drop-down {{
    /* Make the drop-down area visible + give it a left border so
       the user can see where the dropdown handle is. */
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: {arrow_w}px;
    border-left: 1px solid {color('border')};
    background: transparent;
}}
QComboBox::down-arrow {{
    /* Inline SVG triangle so the arrow is always present and
       themed. Qt's default arrow disappears as soon as any
       QComboBox subcontrol is styled, so we draw our own. */
    image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 8'><path d='M1 1.5L6 6.5L11 1.5' stroke='%23{arrow_color}' stroke-width='1.8' fill='none' stroke-linecap='round' stroke-linejoin='round'/></svg>");
    width: {arrow_size}px;
    height: {arrow_size}px;
}}
QComboBox QAbstractItemView {{
    background: {color('bg_panel')};
    color: {color('text')};
    selection-background-color: {color('accent')};
    selection-color: {color('accent_text')};
    border: 1px solid {color('border')};
    font-size: {fs_body}px;
    padding: 2px;
}}
QComboBox QAbstractItemView::item {{
    min-height: {combo_h}px;
    padding: 4px 8px;
}}
QPushButton {{
    background: transparent;
    color: {color('text')};
    border: 1px solid {color('border')};
    border-radius: 4px;
    padding: 6px 14px;
    font-size: {fs_body}px;
}}
QPushButton:hover {{
    border-color: {color('accent')};
    color: {color('accent')};
}}
QPushButton[primary="true"] {{
    background: {color('accent')};
    color: {color('accent_text')};
    border-color: {color('accent')};
    font-weight: 600;
}}
QPushButton[primary="true"]:hover {{
    background: {color('accent_hover')};
    border-color: {color('accent_hover')};
}}
QMessageBox {{
    background-color: {color('bg')};
    color: {color('text')};
}}
QMessageBox QLabel {{
    color: {color('text')};
    font-size: {fs_body}px;
}}
"""
