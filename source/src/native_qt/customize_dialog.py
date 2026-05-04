"""File > Customize popup. Three controls: theme, UI scale, language.

The dialog reads + writes ``customize_settings.json`` via the
``customize_settings`` module. Applying changes:

  - Theme + UI scale  → re-apply at runtime via ``apply_theme(app, ...)``,
                        no restart required.
  - Language          → preference is saved + activated immediately
                        for any *new* widgets (e.g. Help dialogs
                        opened after the change). Already-built
                        widgets — most importantly the menu bar —
                        only re-translate after restart, so the
                        dialog pops a one-time "restart required"
                        notice when the user picks a different
                        language than the one the app booted into.
                        Languages with a real translation pack in
                        ``src/translations/<code>.json`` are listed
                        without a "translation pending" suffix; the
                        rest get the suffix so the user knows which
                        ones are aspirational.

Modal QDialog; pops via ``open_customize_dialog(parent)``.
"""
from __future__ import annotations

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

import customize_settings as _cs
from .theme import apply_theme
from . import theme_palette as _palette
from . import scale as _scale
from i18n import _ as _t


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
        self.setWindowTitle(_t("Customize Frog Mod Editor"))
        # Build QSS from the active palette + register a listener so
        # the dialog re-themes itself live as the user clicks the
        # theme radios (otherwise the dialog stays in the OLD theme
        # while the rest of the app switches).
        try:
            self.setStyleSheet(_palette.build_dialog_qss(_scale.active()))
            _palette.register_listener(self._refresh_dialog_qss)
            _scale.register_listener(self._refresh_dialog_qss)
        except Exception:
            self.setStyleSheet(_DIALOG_QSS)
        self.setModal(True)
        self.resize(_scale.sx(520), _scale.sx(540))

        self._initial = _cs.load()  # snapshot for revert-on-cancel

        self._build_ui()
        self._populate_from(self._initial)

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(8)

        title = QtWidgets.QLabel(_t("Customize"))
        title.setProperty('role', 'dialogTitle')
        outer.addWidget(title)
        sub = QtWidgets.QLabel(_t(
            "Adjust appearance, scale, and language. Changes apply "
            "immediately — close the dialog to confirm or click "
            "Cancel to revert."
        ))
        sub.setProperty('role', 'dialogSubtitle')
        sub.setWordWrap(True)
        outer.addWidget(sub)

        # ── Theme section ──
        theme_box = QtWidgets.QGroupBox(_t("Theme"))
        theme_layout = QtWidgets.QVBoxLayout(theme_box)
        theme_layout.setSpacing(2)
        theme_hint = QtWidgets.QLabel(_t(
            "Pick the colour scheme. High contrast is designed for "
            "accessibility (low-vision users) and bright-light "
            "environments where the dark theme is hard to read."
        ))
        theme_hint.setProperty('role', 'hint')
        theme_hint.setWordWrap(True)
        theme_layout.addWidget(theme_hint)
        self._theme_group = QtWidgets.QButtonGroup(self)
        self._theme_buttons = {}
        for key, label in (
            ('dark', _t('Dark (default)')),
            ('light', _t('Light')),
            ('high_contrast', _t('High Contrast')),
        ):
            rb = QtWidgets.QRadioButton(label)
            self._theme_group.addButton(rb)
            self._theme_buttons[key] = rb
            theme_layout.addWidget(rb)
            rb.toggled.connect(self._on_theme_changed)
        outer.addWidget(theme_box)

        # ── UI scale section ──
        scale_box = QtWidgets.QGroupBox(_t("UI Scale"))
        scale_layout = QtWidgets.QVBoxLayout(scale_box)
        scale_layout.setSpacing(2)
        scale_hint = QtWidgets.QLabel(_t(
            "Scales font size + most widget metrics. Larger sizes "
            "are easier on the eyes; smaller sizes fit more "
            "information on screen."
        ))
        scale_hint.setProperty('role', 'hint')
        scale_hint.setWordWrap(True)
        scale_layout.addWidget(scale_hint)
        self._scale_combo = QtWidgets.QComboBox()
        for value, label in (
            (0.85, _t('Small (85%)')),
            (1.00, _t('Default (100%)')),
            (1.15, _t('Large (115%)')),
            (1.30, _t('Extra Large (130%)')),
            (1.50, _t('Huge (150%)')),
            (1.75, _t('High-DPI (175%)')),
            (2.00, _t('Maximum (200%)')),
        ):
            self._scale_combo.addItem(label, value)
        self._scale_combo.currentIndexChanged.connect(self._on_scale_changed)
        scale_layout.addWidget(self._scale_combo)
        outer.addWidget(scale_box)

        # ── Language section ──
        lang_box = QtWidgets.QGroupBox(_t("Language"))
        lang_layout = QtWidgets.QVBoxLayout(lang_box)
        lang_layout.setSpacing(2)
        lang_hint = QtWidgets.QLabel(_t(
            "Preferred interface language. Note: only English is "
            "currently translated. Selecting another language saves "
            "your preference but the UI stays in English until "
            "translation packs are added in a future update."
        ))
        lang_hint.setProperty('role', 'hint')
        lang_hint.setWordWrap(True)
        lang_layout.addWidget(lang_hint)
        # Probe the translations dir so the UI honestly tells the user
        # which languages have a real pack vs. preference-only.
        translated_codes = self._discover_translated_codes()
        self._lang_combo = QtWidgets.QComboBox()
        for code in _cs.VALID_LANGUAGES:
            label = _cs.LANGUAGE_LABELS.get(code, code)
            if code != 'en' and code not in translated_codes:
                label += '  (translation pending)'
            self._lang_combo.addItem(label, code)
        self._lang_combo.currentIndexChanged.connect(self._on_language_changed)
        lang_layout.addWidget(self._lang_combo)
        outer.addWidget(lang_box)

        # ── Output folders section ──
        # Two folder pickers: where Pack Mod writes the .pak file, and
        # where Deploy enabled Lua mods writes the per-mod folders.
        # Setting these lets the user skip the manual copy-paste step
        # by pointing at the Motor Town install paths directly.
        folders_box = QtWidgets.QGroupBox(_t("Output Folders"))
        folders_layout = QtWidgets.QVBoxLayout(folders_box)
        folders_layout.setSpacing(4)
        folders_hint = QtWidgets.QLabel(_t(
            "Optional. Set these to write generated mods directly into "
            "your Motor Town install instead of copy-pasting them by "
            "hand. Leave blank to keep the historical behaviour "
            "(save dialog for .paks, lua_mod_output/ for Lua mods)."
        ))
        folders_hint.setProperty('role', 'hint')
        folders_hint.setWordWrap(True)
        folders_layout.addWidget(folders_hint)

        self._pak_dir_edit, pak_row = self._make_folder_row(
            _t(".pak export folder (typical: <Motor Town>/MotorTown/Content/Paks/~mods/)"),
            self._on_browse_pak_folder,
        )
        folders_layout.addLayout(pak_row)

        self._lua_dir_edit, lua_row = self._make_folder_row(
            _t("Lua mods deployment folder (typical: <Motor Town>/MotorTown/Binaries/Win64/ue4ss/Mods/)"),
            self._on_browse_lua_folder,
        )
        folders_layout.addLayout(lua_row)
        outer.addWidget(folders_box)

        outer.addStretch(1)

        # ── Footer ──
        footer = QtWidgets.QHBoxLayout()
        footer.setSpacing(8)
        footer.addStretch(1)

        cancel_btn = QtWidgets.QPushButton(_t("Cancel"))
        cancel_btn.clicked.connect(self._on_cancel)
        footer.addWidget(cancel_btn)

        ok_btn = QtWidgets.QPushButton(_t("Done"))
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
        # Folder paths
        self._pak_dir_edit.setText(str(settings.get('pak_output_dir') or ''))
        self._lua_dir_edit.setText(str(settings.get('lua_output_dir') or ''))

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
            'pak_output_dir': self._pak_dir_edit.text().strip(),
            'lua_output_dir': self._lua_dir_edit.text().strip(),
        }

    # ── Folder picker helpers ──
    def _make_folder_row(self, label_text: str, on_browse) -> tuple:
        """Build one folder picker row: label + read-only path edit +
        Browse + Clear buttons. Returns (line_edit, layout) so the
        caller can store the edit widget for later read/write."""
        row_label = QtWidgets.QLabel(label_text)
        row_label.setProperty('role', 'hint')
        row_label.setWordWrap(True)
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(6)
        edit = QtWidgets.QLineEdit()
        edit.setReadOnly(False)  # editable so user can paste a path
        edit.setPlaceholderText(_t("(not set — using default)"))
        browse_btn = QtWidgets.QPushButton(_t("Browse…"))
        browse_btn.clicked.connect(on_browse)
        clear_btn = QtWidgets.QPushButton(_t("Clear"))
        clear_btn.clicked.connect(lambda: edit.setText(""))
        row.addWidget(edit, 1)
        row.addWidget(browse_btn, 0)
        row.addWidget(clear_btn, 0)
        # Assemble label + row into a vertical container so the label
        # sits above the row.
        wrapper = QtWidgets.QVBoxLayout()
        wrapper.setSpacing(2)
        wrapper.setContentsMargins(0, 6, 0, 0)
        wrapper.addWidget(row_label)
        wrapper.addLayout(row)
        return edit, wrapper

    def _on_browse_pak_folder(self) -> None:
        start = self._pak_dir_edit.text().strip() or self._initial.get('pak_output_dir') or ''
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self, _t("Choose .pak export folder"), start
        )
        if path:
            self._pak_dir_edit.setText(path)

    def _on_browse_lua_folder(self) -> None:
        start = self._lua_dir_edit.text().strip() or self._initial.get('lua_output_dir') or ''
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self, _t("Choose Lua mods deployment folder"), start
        )
        if path:
            self._lua_dir_edit.setText(path)

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

    @staticmethod
    def _discover_translated_codes() -> set:
        """Scan src/translations/ for *.json packs and return the set
        of ISO codes that have a real translation file shipped."""
        try:
            import os as _os
            from i18n import TRANSLATIONS_DIR
            if not _os.path.isdir(TRANSLATIONS_DIR):
                return set()
            return {
                _os.path.splitext(name)[0].lower()
                for name in _os.listdir(TRANSLATIONS_DIR)
                if name.endswith('.json')
            }
        except Exception:
            return set()

    def _on_language_changed(self, _index: int = 0) -> None:
        # Activate the new language immediately so newly-built widgets
        # (e.g. the Help dialog opened after this change) pick it up.
        # Already-rendered widgets — most importantly the menu bar
        # built once at startup — stay in the old language until the
        # app is restarted. Qt doesn't expose a clean "re-translate
        # the live tree" hook for our manual _t() pattern, so we tell
        # the user honestly that a restart is required for the new
        # language to flow through every existing widget.
        new_code = str(self._lang_combo.currentData() or 'en')
        initial_code = str(self._initial.get('language', 'en'))
        try:
            from i18n import set_language
            set_language(new_code)
        except Exception:
            pass
        # Only prompt if the user actually picked something different
        # from what the app booted into — flipping back to the start
        # language doesn't need a restart.
        if new_code != initial_code and not getattr(self, '_lang_warned', False):
            self._lang_warned = True
            try:
                box = QtWidgets.QMessageBox(self)
                box.setIcon(QtWidgets.QMessageBox.Icon.Information)
                box.setWindowTitle(_t("Restart Required"))
                box.setText(_t(
                    "Language preference saved. Please restart "
                    "Frog Mod Editor for the new language to take "
                    "effect throughout the interface."
                ))
                box.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Ok)
                box.exec()
            except Exception:
                pass

    # ── Footer actions ──
    def _refresh_dialog_qss(self) -> None:
        """Listener fired by theme_palette.set_active OR scale.set_active
        when the user changes theme/scale via the dialog — rebuilds
        the dialog's stylesheet so its own chrome reflects the new
        palette + scale immediately."""
        try:
            self.setStyleSheet(_palette.build_dialog_qss(_scale.active()))
        except Exception:
            pass

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
