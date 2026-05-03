"""File > Customize popup. Three controls: theme, UI scale, language.

The dialog reads + writes ``customize_settings.json`` via the
``customize_settings`` module. Applying changes:

  - Theme + UI scale  → re-apply at runtime via ``apply_theme(app, ...)``,
                        no restart required.
  - Language          → preference is saved, but actual translation
                        is English-only for now (no .qm translation
                        packs shipped yet). The dialog tells the user
                        this honestly.

Modal QDialog; pops via ``open_customize_dialog(parent)``.
"""
from __future__ import annotations

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

import customize_settings as _cs
from .theme import apply_theme


# Local palette — matches the help dialog so the two popups feel
# consistent. We don't reach into the global theme module because
# the dialog needs to render correctly even mid-theme-change.
_BG          = "#0c1622"
_BG_PANEL    = "#13202f"
_BORDER      = "#314153"
_TEXT        = "#cdd6e0"
_MUTED       = "#9da7b0"
_ACCENT      = "#73c686"
_ACCENT_TEXT = "#0c1622"


_DIALOG_QSS = f"""
QDialog {{
    background-color: {_BG};
    color: {_TEXT};
}}
QLabel {{ color: {_TEXT}; background: transparent; }}
QLabel[role="dialogTitle"] {{
    font-size: 18px;
    font-weight: 700;
}}
QLabel[role="dialogSubtitle"] {{
    color: {_MUTED};
    font-size: 12px;
    padding-bottom: 8px;
}}
QLabel[role="sectionHeader"] {{
    color: {_TEXT};
    font-size: 13px;
    font-weight: 600;
    padding-top: 10px;
}}
QLabel[role="hint"] {{
    color: {_MUTED};
    font-size: 11px;
    padding: 2px 0 8px 0;
}}
QGroupBox {{
    background: {_BG_PANEL};
    border: 1px solid {_BORDER};
    border-radius: 5px;
    margin-top: 12px;
    padding: 8px 12px 12px 12px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    color: {_TEXT};
    font-weight: 600;
}}
QRadioButton {{ color: {_TEXT}; padding: 4px 0; }}
QRadioButton::indicator {{
    width: 14px; height: 14px;
    border: 1px solid #6b7c8e;
    border-radius: 7px;
    background: #1a2532;
}}
QRadioButton::indicator:checked {{
    background: {_ACCENT};
    border: 1px solid {_ACCENT};
}}
QComboBox {{
    background: {_BG_PANEL};
    color: {_TEXT};
    border: 1px solid {_BORDER};
    border-radius: 4px;
    padding: 5px 10px;
    min-height: 22px;
    font-size: 12px;
}}
QComboBox QAbstractItemView {{
    background: {_BG_PANEL};
    color: {_TEXT};
    selection-background-color: {_ACCENT};
    selection-color: {_ACCENT_TEXT};
    border: 1px solid {_BORDER};
}}
QPushButton {{
    background: transparent;
    color: {_TEXT};
    border: 1px solid {_BORDER};
    border-radius: 4px;
    padding: 6px 14px;
    font-size: 12px;
}}
QPushButton:hover {{ border-color: {_ACCENT}; color: {_ACCENT}; }}
QPushButton[primary="true"] {{
    background: {_ACCENT};
    color: {_ACCENT_TEXT};
    border-color: {_ACCENT};
    font-weight: 600;
}}
QPushButton[primary="true"]:hover {{
    background: #8bd599;
    border-color: #8bd599;
}}
"""


class CustomizeDialog(QtWidgets.QDialog):
    """Modal popup for changing theme, UI scale, language."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Customize Frog Mod Editor")
        self.setStyleSheet(_DIALOG_QSS)
        self.setModal(True)
        self.resize(520, 540)

        self._initial = _cs.load()  # snapshot for revert-on-cancel

        self._build_ui()
        self._populate_from(self._initial)

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(8)

        title = QtWidgets.QLabel("Customize")
        title.setProperty('role', 'dialogTitle')
        outer.addWidget(title)
        sub = QtWidgets.QLabel(
            "Adjust appearance, scale, and language. Changes apply "
            "immediately — close the dialog to confirm or click "
            "Cancel to revert."
        )
        sub.setProperty('role', 'dialogSubtitle')
        sub.setWordWrap(True)
        outer.addWidget(sub)

        # ── Theme section ──
        theme_box = QtWidgets.QGroupBox("Theme")
        theme_layout = QtWidgets.QVBoxLayout(theme_box)
        theme_layout.setSpacing(2)
        theme_hint = QtWidgets.QLabel(
            "Pick the colour scheme. High contrast is designed for "
            "accessibility (low-vision users) and bright-light "
            "environments where the dark theme is hard to read."
        )
        theme_hint.setProperty('role', 'hint')
        theme_hint.setWordWrap(True)
        theme_layout.addWidget(theme_hint)
        self._theme_group = QtWidgets.QButtonGroup(self)
        self._theme_buttons = {}
        for key, label in (
            ('dark', 'Dark (default)'),
            ('light', 'Light'),
            ('high_contrast', 'High Contrast'),
        ):
            rb = QtWidgets.QRadioButton(label)
            self._theme_group.addButton(rb)
            self._theme_buttons[key] = rb
            theme_layout.addWidget(rb)
            rb.toggled.connect(self._on_theme_changed)
        outer.addWidget(theme_box)

        # ── UI scale section ──
        scale_box = QtWidgets.QGroupBox("UI Scale")
        scale_layout = QtWidgets.QVBoxLayout(scale_box)
        scale_layout.setSpacing(2)
        scale_hint = QtWidgets.QLabel(
            "Scales font size + most widget metrics. Larger sizes "
            "are easier on the eyes; smaller sizes fit more "
            "information on screen."
        )
        scale_hint.setProperty('role', 'hint')
        scale_hint.setWordWrap(True)
        scale_layout.addWidget(scale_hint)
        self._scale_combo = QtWidgets.QComboBox()
        for value, label in (
            (0.85, 'Small (85%)'),
            (1.00, 'Default (100%)'),
            (1.15, 'Large (115%)'),
            (1.30, 'Extra Large (130%)'),
        ):
            self._scale_combo.addItem(label, value)
        self._scale_combo.currentIndexChanged.connect(self._on_scale_changed)
        scale_layout.addWidget(self._scale_combo)
        outer.addWidget(scale_box)

        # ── Language section ──
        lang_box = QtWidgets.QGroupBox("Language")
        lang_layout = QtWidgets.QVBoxLayout(lang_box)
        lang_layout.setSpacing(2)
        lang_hint = QtWidgets.QLabel(
            "Preferred interface language. Note: only English is "
            "currently translated. Selecting another language saves "
            "your preference but the UI stays in English until "
            "translation packs are added in a future update."
        )
        lang_hint.setProperty('role', 'hint')
        lang_hint.setWordWrap(True)
        lang_layout.addWidget(lang_hint)
        self._lang_combo = QtWidgets.QComboBox()
        for code in _cs.VALID_LANGUAGES:
            label = _cs.LANGUAGE_LABELS.get(code, code)
            if code != 'en':
                label += '  (translation pending)'
            self._lang_combo.addItem(label, code)
        self._lang_combo.currentIndexChanged.connect(self._on_language_changed)
        lang_layout.addWidget(self._lang_combo)
        outer.addWidget(lang_box)

        outer.addStretch(1)

        # ── Footer ──
        footer = QtWidgets.QHBoxLayout()
        footer.setSpacing(8)
        footer.addStretch(1)

        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.clicked.connect(self._on_cancel)
        footer.addWidget(cancel_btn)

        ok_btn = QtWidgets.QPushButton("Done")
        ok_btn.setProperty('primary', True)
        ok_btn.clicked.connect(self._on_done)
        footer.addWidget(ok_btn)

        outer.addLayout(footer)

    # ------------------------------------------------------------------
    def _populate_from(self, settings: dict) -> None:
        """Reflect *settings* in the UI controls without firing
        changed signals (otherwise we'd re-apply the theme on every
        radio toggle during init)."""
        # Theme
        theme = settings.get('theme', 'dark')
        rb = self._theme_buttons.get(theme) or self._theme_buttons['dark']
        rb.blockSignals(True)
        rb.setChecked(True)
        rb.blockSignals(False)
        # Scale
        scale = settings.get('ui_scale', 1.0)
        for i in range(self._scale_combo.count()):
            if abs(self._scale_combo.itemData(i) - scale) < 0.01:
                self._scale_combo.blockSignals(True)
                self._scale_combo.setCurrentIndex(i)
                self._scale_combo.blockSignals(False)
                break
        # Language
        lang = settings.get('language', 'en')
        for i in range(self._lang_combo.count()):
            if self._lang_combo.itemData(i) == lang:
                self._lang_combo.blockSignals(True)
                self._lang_combo.setCurrentIndex(i)
                self._lang_combo.blockSignals(False)
                break

    # ── Live change handlers ──
    def _current_settings(self) -> dict:
        # Theme
        theme = 'dark'
        for key, rb in self._theme_buttons.items():
            if rb.isChecked():
                theme = key
                break
        return {
            'theme': theme,
            'ui_scale': float(self._scale_combo.currentData() or 1.0),
            'language': str(self._lang_combo.currentData() or 'en'),
        }

    def _apply_now(self) -> None:
        cfg = self._current_settings()
        app = QtWidgets.QApplication.instance()
        if app is None:
            return
        try:
            apply_theme(app, theme=cfg['theme'], ui_scale=cfg['ui_scale'])
        except Exception:
            # Theme failures shouldn't crash the dialog — they'd
            # leave the user stuck unable to revert.
            pass

    def _on_theme_changed(self, _checked: bool = False) -> None:
        # Only handle the "now-checked" radio (toggled fires twice:
        # once for the unchecked, once for the newly-checked button).
        if not self.sender().isChecked():
            return
        self._apply_now()

    def _on_scale_changed(self, _index: int = 0) -> None:
        self._apply_now()

    def _on_language_changed(self, _index: int = 0) -> None:
        # Language selection doesn't re-apply the theme; the only
        # observable change is the saved preference.
        pass

    # ── Footer actions ──
    def _on_done(self) -> None:
        cfg = self._current_settings()
        _cs.save(cfg)
        self.accept()

    def _on_cancel(self) -> None:
        # Revert any live theme/scale changes by re-applying the
        # snapshot we took at construction time.
        app = QtWidgets.QApplication.instance()
        if app is not None:
            try:
                apply_theme(
                    app,
                    theme=self._initial.get('theme', 'dark'),
                    ui_scale=self._initial.get('ui_scale', 1.0),
                )
            except Exception:
                pass
        self.reject()


def open_customize_dialog(parent: Optional[QtWidgets.QWidget] = None) -> None:
    """Convenience: build + show the Customize dialog modally."""
    dlg = CustomizeDialog(parent)
    dlg.exec()
