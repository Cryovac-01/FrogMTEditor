"""LUA Scripts tab — one collapsible card per registered Lua mod,
each with its own settings controls, plus a single global Deploy
button that writes every enabled mod's folder into the output
directory and shows a combined result dialog.

Settings are persisted per-mod in data/lua_mods_settings.json so the
user's choices survive across sessions.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

from lua_mods import all_deployers, DEFAULT_OUTPUT_DIR, Setting

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Colour tokens (match economy_panel for visual continuity)
# ---------------------------------------------------------------------------
_BG = "#161c26"
_SURFACE = "#1c2533"
_CARD = "#212c3d"
_BORDER = "#2d3948"
_TEXT = "#edf2f7"
_MUTED = "#8b97a8"
_ACCENT = "#67bfd9"
_SUCCESS = "#6fcf97"
_DANGER = "#f07070"


_SETTINGS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'data', 'lua_mods_settings.json'
)


def _load_persisted() -> Dict[str, Any]:
    if not os.path.isfile(_SETTINGS_PATH):
        return {}
    try:
        with open(_SETTINGS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Could not load lua_mods_settings.json: %s", e)
        return {}


def _save_persisted(data: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_SETTINGS_PATH), exist_ok=True)
        with open(_SETTINGS_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning("Could not save lua_mods_settings.json: %s", e)


def _open_in_file_manager(path: str) -> None:
    try:
        if not os.path.isdir(path):
            return
        if sys.platform == 'win32':
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', path])
        else:
            subprocess.Popen(['xdg-open', path])
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Settings-widget factory
# ---------------------------------------------------------------------------
class _SettingControl:
    """Pairs a Setting descriptor with its Qt widget + value accessors."""

    def __init__(self, setting: Setting, widget: QtWidgets.QWidget,
                 getter: Callable[[], Any], setter: Callable[[Any], None],
                 signal: QtCore.SignalInstance) -> None:
        self.setting = setting
        self.widget = widget
        self.get = getter
        self.set = setter
        self.signal = signal


def _build_mode_control(setting: Setting) -> _SettingControl:
    """4-button exclusive row (Vanilla/Low/High/Off or custom)."""
    container = QtWidgets.QWidget()
    row = QtWidgets.QHBoxLayout(container)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)

    btn_style = f"""
        QPushButton {{
            background: {_CARD};
            color: {_TEXT};
            border: 1px solid {_BORDER};
            border-radius: 4px;
            padding: 6px 14px;
            font-size: 12px;
            font-weight: 600;
        }}
        QPushButton:hover {{ background: {_BORDER}; }}
        QPushButton:checked {{
            background: {_ACCENT};
            color: #0b1410;
            border-color: {_ACCENT};
        }}
    """

    group = QtWidgets.QButtonGroup(container)
    group.setExclusive(True)
    buttons: Dict[str, QtWidgets.QPushButton] = {}
    for opt in (setting.options or []):
        btn = QtWidgets.QPushButton(opt.label)
        btn.setCheckable(True)
        btn.setStyleSheet(btn_style)
        if opt.tooltip:
            btn.setToolTip(opt.tooltip)
        buttons[opt.key] = btn
        group.addButton(btn)
        row.addWidget(btn)
    row.addStretch(1)

    # Default selection
    default = setting.default if setting.default in buttons else next(iter(buttons))
    buttons[default].setChecked(True)

    def getter() -> str:
        for k, b in buttons.items():
            if b.isChecked():
                return k
        return default

    def setter(value: str) -> None:
        if value in buttons:
            buttons[value].setChecked(True)
        else:
            buttons[default].setChecked(True)

    return _SettingControl(
        setting=setting, widget=container,
        getter=getter, setter=setter,
        signal=group.buttonClicked,
    )


def _build_int_control(setting: Setting) -> _SettingControl:
    spin = QtWidgets.QSpinBox()
    spin.setRange(
        int(setting.min_value) if setting.min_value is not None else 0,
        int(setting.max_value) if setting.max_value is not None else 9999,
    )
    spin.setSingleStep(int(setting.step) if setting.step else 1)
    spin.setValue(int(setting.default))
    if setting.suffix:
        spin.setSuffix(setting.suffix)
    if setting.tooltip:
        spin.setToolTip(setting.tooltip)
    spin.setStyleSheet(f"""
        QSpinBox {{
            background: {_CARD};
            color: {_TEXT};
            border: 1px solid {_BORDER};
            border-radius: 4px;
            padding: 4px 6px;
            font-size: 12px;
            min-width: 120px;
        }}
    """)
    return _SettingControl(
        setting=setting, widget=spin,
        getter=lambda: spin.value(),
        setter=lambda v: spin.setValue(int(v)),
        signal=spin.valueChanged,
    )


def _build_float_control(setting: Setting) -> _SettingControl:
    spin = QtWidgets.QDoubleSpinBox()
    spin.setDecimals(2)
    spin.setRange(
        float(setting.min_value) if setting.min_value is not None else 0.0,
        float(setting.max_value) if setting.max_value is not None else 99.0,
    )
    spin.setSingleStep(float(setting.step) if setting.step else 0.1)
    spin.setValue(float(setting.default))
    if setting.suffix:
        spin.setSuffix(setting.suffix)
    if setting.tooltip:
        spin.setToolTip(setting.tooltip)
    spin.setStyleSheet(f"""
        QDoubleSpinBox {{
            background: {_CARD};
            color: {_TEXT};
            border: 1px solid {_BORDER};
            border-radius: 4px;
            padding: 4px 6px;
            font-size: 12px;
            min-width: 120px;
        }}
    """)
    return _SettingControl(
        setting=setting, widget=spin,
        getter=lambda: spin.value(),
        setter=lambda v: spin.setValue(float(v)),
        signal=spin.valueChanged,
    )


def _build_bool_control(setting: Setting) -> _SettingControl:
    cb = QtWidgets.QCheckBox(setting.label)
    cb.setChecked(bool(setting.default))
    if setting.tooltip:
        cb.setToolTip(setting.tooltip)
    return _SettingControl(
        setting=setting, widget=cb,
        getter=lambda: cb.isChecked(),
        setter=lambda v: cb.setChecked(bool(v)),
        signal=cb.stateChanged,
    )


def _build_slider_control(setting: Setting) -> _SettingControl:
    """Horizontal QSlider + live float readout. Step defaults to 0.1 if
    unset. Slider internally uses integer ticks = value / step."""
    step = float(setting.step) if setting.step else 0.1
    lo = float(setting.min_value) if setting.min_value is not None else 0.0
    hi = float(setting.max_value) if setting.max_value is not None else 1.0
    default = float(setting.default)

    def f2i(f: float) -> int:
        return int(round(f / step))

    def i2f(i: int) -> float:
        return round(i * step, 4)

    container = QtWidgets.QWidget()
    row = QtWidgets.QHBoxLayout(container)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(10)

    slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
    slider.setRange(f2i(lo), f2i(hi))
    slider.setSingleStep(1)
    slider.setPageStep(max(1, f2i((hi - lo) / 10.0)))
    slider.setValue(f2i(default))
    slider.setMinimumWidth(220)
    slider.setStyleSheet(f"""
        QSlider::groove:horizontal {{
            background: {_CARD};
            border: 1px solid {_BORDER};
            border-radius: 3px;
            height: 6px;
        }}
        QSlider::sub-page:horizontal {{
            background: {_ACCENT};
            border-radius: 3px;
            height: 6px;
        }}
        QSlider::handle:horizontal {{
            background: {_ACCENT};
            border: 1px solid {_ACCENT};
            width: 16px;
            height: 16px;
            margin: -6px 0;
            border-radius: 8px;
        }}
        QSlider::handle:horizontal:hover {{
            background: #7cd0e6;
        }}
    """)
    if setting.tooltip:
        slider.setToolTip(setting.tooltip)

    readout = QtWidgets.QLabel()
    readout.setMinimumWidth(60)
    readout.setAlignment(
        QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter
    )
    readout.setStyleSheet(
        f"color: {_TEXT}; font-size: 12px; font-weight: 600;"
    )

    def format_val(f: float) -> str:
        text = f"{f:.2f}".rstrip('0').rstrip('.')
        if '.' not in text:
            text += '.0'
        return text + (setting.suffix or '')

    def on_change(_i: int = 0) -> None:
        readout.setText(format_val(i2f(slider.value())))

    slider.valueChanged.connect(on_change)
    on_change()

    row.addWidget(slider, 1)
    row.addWidget(readout)

    return _SettingControl(
        setting=setting, widget=container,
        getter=lambda: i2f(slider.value()),
        setter=lambda v: slider.setValue(f2i(float(v))),
        signal=slider.valueChanged,
    )


def _build_control(setting: Setting) -> _SettingControl:
    if setting.kind == 'mode':
        return _build_mode_control(setting)
    if setting.kind == 'int':
        return _build_int_control(setting)
    if setting.kind == 'float':
        return _build_float_control(setting)
    if setting.kind == 'slider':
        return _build_slider_control(setting)
    if setting.kind == 'bool':
        return _build_bool_control(setting)
    raise ValueError(f"Unknown setting kind: {setting.kind}")


# ---------------------------------------------------------------------------
# Collapsible card — one per mod
# ---------------------------------------------------------------------------
class _ModCard(QtWidgets.QFrame):
    """Collapsible card containing one mod's enable-checkbox, description,
    setting controls, and per-mod deploy button."""

    deploy_requested = QtCore.Signal(str)     # emits MOD_NAME

    def __init__(self, deployer: Any, initial_enabled: bool,
                 initial_config: Dict[str, Any], parent=None) -> None:
        super().__init__(parent)
        self._deployer = deployer
        self._controls: List[_SettingControl] = []
        self._expanded = False

        self.setStyleSheet(f"""
            QFrame {{
                background: {_SURFACE};
                border: 1px solid {_BORDER};
                border-radius: 8px;
            }}
        """)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header row ────────────────────────────────────────────
        header = QtWidgets.QWidget()
        header.setStyleSheet("QWidget { background: transparent; }")
        hl = QtWidgets.QHBoxLayout(header)
        hl.setContentsMargins(14, 10, 14, 10)
        hl.setSpacing(10)

        # Use a plain QPushButton as the enable toggle. Works the same
        # as a QCheckBox (checkable two-state) but renders as a pill
        # that reads "Enabled"/"Disabled" with an accent fill when on
        # — far more visible against the dark card background than a
        # native QCheckBox indicator, which on Fusion style is a small
        # square that blends into the theme.
        self._enable_cb = QtWidgets.QPushButton()
        self._enable_cb.setCheckable(True)
        self._enable_cb.setChecked(initial_enabled)
        self._enable_cb.setToolTip(
            "Tick to include this mod when you click the global "
            "'Deploy enabled Lua mods' button."
        )
        self._enable_cb.setMinimumWidth(92)
        self._enable_cb.setFixedHeight(28)
        self._enable_cb.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._enable_cb.setStyleSheet(f"""
            QPushButton {{
                background: {_CARD};
                color: {_MUTED};
                border: 1px solid {_BORDER};
                border-radius: 14px;
                padding: 0 14px;
                font-size: 12px;
                font-weight: 600;
                text-align: center;
            }}
            QPushButton:hover {{
                border-color: {_ACCENT};
            }}
            QPushButton:checked {{
                background: {_ACCENT};
                color: #0b1410;
                border-color: {_ACCENT};
            }}
        """)

        def _update_enable_label() -> None:
            self._enable_cb.setText(
                "\u2714 Enabled" if self._enable_cb.isChecked() else "Disabled"
            )
        _update_enable_label()
        self._enable_cb.toggled.connect(lambda _=0: _update_enable_label())
        hl.addWidget(self._enable_cb)

        title_label = QtWidgets.QLabel(deployer.UI_TITLE)
        title_label.setStyleSheet(
            f"color: {_TEXT}; font-size: 14px; font-weight: 600;"
        )
        hl.addWidget(title_label)

        subtitle = QtWidgets.QLabel(f"  \u2014  {deployer.MOD_NAME}")
        subtitle.setStyleSheet(f"color: {_MUTED}; font-size: 11px;")
        hl.addWidget(subtitle)

        hl.addStretch(1)

        self._expand_btn = QtWidgets.QPushButton()
        self._expand_btn.setFixedHeight(28)
        self._expand_btn.setMinimumWidth(110)
        self._expand_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._expand_btn.setToolTip("Show or hide this mod's configuration.")
        self._expand_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_CARD};
                color: {_TEXT};
                border: 1px solid {_BORDER};
                border-radius: 4px;
                padding: 0 12px;
                font-size: 12px;
                font-weight: 600;
                text-align: center;
            }}
            QPushButton:hover {{
                background: {_BORDER};
                border-color: {_ACCENT};
            }}
        """)
        self._expand_btn.clicked.connect(self._toggle_expanded)
        hl.addWidget(self._expand_btn)

        # Clicking the title label also toggles expansion.
        title_label.mousePressEvent = lambda _e: self._toggle_expanded()

        root.addWidget(header)

        # ── Body ──────────────────────────────────────────────────
        self._body = QtWidgets.QWidget()
        self._body.setStyleSheet("QWidget { background: transparent; }")
        body_layout = QtWidgets.QVBoxLayout(self._body)
        body_layout.setContentsMargins(14, 0, 14, 14)
        body_layout.setSpacing(10)

        # Description (supports basic HTML)
        desc = QtWidgets.QLabel(deployer.UI_DESCRIPTION)
        desc.setWordWrap(True)
        desc.setTextFormat(QtCore.Qt.TextFormat.RichText)
        desc.setStyleSheet(f"color: {_MUTED}; font-size: 12px;")
        body_layout.addWidget(desc)

        # Settings form
        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(8)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        for setting in deployer.SETTINGS:
            ctrl = _build_control(setting)
            label = QtWidgets.QLabel(setting.label + ":")
            label.setStyleSheet(f"color: {_TEXT}; font-size: 12px;")
            if setting.tooltip:
                label.setToolTip(setting.tooltip)
            form.addRow(label, ctrl.widget)
            # Populate with persisted value if present
            if setting.key in initial_config:
                try:
                    ctrl.set(initial_config[setting.key])
                except Exception:
                    pass
            self._controls.append(ctrl)
        body_layout.addLayout(form)

        # Per-mod action row
        action_row = QtWidgets.QHBoxLayout()
        action_row.setSpacing(8)

        help_btn = QtWidgets.QPushButton("Setup instructions")
        help_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {_ACCENT};
                border: 1px solid {_BORDER};
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 12px;
            }}
            QPushButton:hover {{ background: {_BORDER}; }}
        """)
        help_btn.clicked.connect(self._show_instructions)
        action_row.addWidget(help_btn)

        deploy_btn = QtWidgets.QPushButton("Deploy only this")
        deploy_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_ACCENT};
                color: #0b1410;
                border: 1px solid {_ACCENT};
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background: #7cd0e6; }}
        """)
        deploy_btn.clicked.connect(
            lambda: self.deploy_requested.emit(self._deployer.MOD_NAME)
        )
        action_row.addWidget(deploy_btn)

        action_row.addStretch(1)
        body_layout.addLayout(action_row)

        # Status line for per-mod deploy results
        self.status_label = QtWidgets.QLabel("")
        self.status_label.setStyleSheet(f"color: {_MUTED}; font-size: 11px;")
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        body_layout.addWidget(self.status_label)

        root.addWidget(self._body)
        self._body.setVisible(False)
        self._refresh_expand_label()

    # ------------------------------------------------------------------
    def _toggle_expanded(self) -> None:
        self._expanded = not self._expanded
        self._body.setVisible(self._expanded)
        self._refresh_expand_label()

    def _refresh_expand_label(self) -> None:
        # Unicode arrows kept alongside the text so users also get a
        # visual cue. When expanded, the body is visible so "Collapse ▲".
        # When collapsed, "Expand ▼".
        if self._expanded:
            self._expand_btn.setText("Collapse \u25B2")
        else:
            self._expand_btn.setText("Expand \u25BC")

    def set_expanded(self, value: bool) -> None:
        if value != self._expanded:
            self._toggle_expanded()

    # ------------------------------------------------------------------
    def _show_instructions(self) -> None:
        cfg = self.config()
        try:
            text = self._deployer.generate_readme(cfg)
        except Exception as e:
            text = f"(could not generate README: {e})"
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(f"{self._deployer.UI_TITLE} — Setup instructions")
        dlg.setMinimumSize(640, 520)
        lay = QtWidgets.QVBoxLayout(dlg)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(10)
        pt = QtWidgets.QPlainTextEdit()
        pt.setReadOnly(True)
        pt.setPlainText(text)
        pt.setStyleSheet(f"""
            QPlainTextEdit {{
                background: {_CARD}; color: {_TEXT};
                border: 1px solid {_BORDER}; border-radius: 4px;
                font-family: Consolas, 'Courier New', monospace;
                font-size: 12px;
            }}
        """)
        lay.addWidget(pt, 1)
        btn_row = QtWidgets.QHBoxLayout()
        ue4ss = QtWidgets.QPushButton("Open UE4SS releases page")
        ue4ss.clicked.connect(lambda: QtGui.QDesktopServices.openUrl(
            QtCore.QUrl("https://github.com/UE4SS-RE/RE-UE4SS/releases")
        ))
        btn_row.addWidget(ue4ss)
        btn_row.addStretch(1)
        close = QtWidgets.QPushButton("Close")
        close.clicked.connect(dlg.accept)
        close.setDefault(True)
        btn_row.addWidget(close)
        lay.addLayout(btn_row)
        dlg.exec()

    # ------------------------------------------------------------------
    def enabled(self) -> bool:
        return self._enable_cb.isChecked()

    def set_enabled(self, value: bool) -> None:
        self._enable_cb.setChecked(bool(value))

    def config(self) -> Dict[str, Any]:
        return {c.setting.key: c.get() for c in self._controls}

    def set_status(self, html: str) -> None:
        self.status_label.setText(html)


# ---------------------------------------------------------------------------
# LUA Scripts panel (the tab widget)
# ---------------------------------------------------------------------------
class LuaScriptsPanel(QtWidgets.QWidget):
    """Tab body — collapsible cards per mod + global Deploy."""

    mods_deployed = QtCore.Signal(dict)  # emits {MOD_NAME: result-dict}

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._cards: Dict[str, _ModCard] = {}
        self._last_output_paths: Dict[str, str] = {}
        self._build_ui()
        self._load_from_disk()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        # Header
        header_row = QtWidgets.QHBoxLayout()
        header_row.setSpacing(14)

        title = QtWidgets.QLabel("LUA Scripts")
        title.setStyleSheet(f"color: {_TEXT}; font-size: 20px; font-weight: 600;")
        header_row.addWidget(title)

        header_row.addStretch(1)

        self._deploy_all_btn = QtWidgets.QPushButton("Deploy enabled Lua mods")
        self._deploy_all_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_ACCENT};
                color: #0b1410;
                border: 1px solid {_ACCENT};
                border-radius: 4px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background: #7cd0e6; }}
            QPushButton:disabled {{
                background: {_BORDER}; color: {_MUTED};
                border-color: {_BORDER};
            }}
        """)
        self._deploy_all_btn.clicked.connect(self._on_deploy_all)
        header_row.addWidget(self._deploy_all_btn)

        root.addLayout(header_row)

        subtitle = QtWidgets.QLabel(
            "Each Lua mod here runs through UE4SS at runtime. Tick the checkbox "
            "on the mods you want, configure them in their cards, then hit "
            "Deploy \u2014 every enabled mod is written as a ready-to-drop folder "
            "under <code>source/data/lua_mod_output/</code>. Full install "
            "instructions (including UE4SS setup) are on each card's "
            "<i>Setup instructions</i> button."
        )
        subtitle.setWordWrap(True)
        subtitle.setTextFormat(QtCore.Qt.TextFormat.RichText)
        subtitle.setStyleSheet(f"color: {_MUTED}; font-size: 12px;")
        root.addWidget(subtitle)

        # Scroll area for cards
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)

        inner = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(inner)
        v.setContentsMargins(0, 0, 6, 0)
        v.setSpacing(10)

        for deployer in all_deployers():
            card = _ModCard(
                deployer=deployer,
                initial_enabled=False,
                initial_config=dict(deployer.DEFAULT_CONFIG),
            )
            card.deploy_requested.connect(self._on_deploy_single)
            self._cards[deployer.MOD_NAME] = card
            v.addWidget(card)

        v.addStretch(1)
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        # Global status strip
        self._global_status = QtWidgets.QLabel("")
        self._global_status.setWordWrap(True)
        self._global_status.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self._global_status.setStyleSheet(f"color: {_MUTED}; font-size: 12px;")
        self._global_status.linkActivated.connect(self._on_status_link)
        root.addWidget(self._global_status)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _load_from_disk(self) -> None:
        data = _load_persisted()
        for mod_name, card in self._cards.items():
            entry = data.get(mod_name, {})
            card.set_enabled(bool(entry.get('enabled', False)))
            cfg = entry.get('config', {})
            for ctrl in card._controls:
                if ctrl.setting.key in cfg:
                    try:
                        ctrl.set(cfg[ctrl.setting.key])
                    except Exception:
                        pass

    def _save_to_disk(self) -> None:
        data: Dict[str, Any] = {}
        for mod_name, card in self._cards.items():
            data[mod_name] = {
                'enabled': card.enabled(),
                'config': card.config(),
            }
        _save_persisted(data)

    # ------------------------------------------------------------------
    # Deploy flow
    # ------------------------------------------------------------------
    def _on_deploy_single(self, mod_name: str) -> None:
        card = self._cards.get(mod_name)
        if not card:
            return
        deployer = next((d for d in all_deployers() if d.MOD_NAME == mod_name), None)
        if not deployer:
            return
        result = deployer.deploy(card.config())
        self._apply_result_to_card(card, result)
        self._save_to_disk()
        self.mods_deployed.emit({mod_name: result})

    def _on_deploy_all(self) -> None:
        enabled = [(name, card) for name, card in self._cards.items() if card.enabled()]
        if not enabled:
            self._global_status.setText(
                f"<span style='color: {_DANGER};'>No mods are enabled — "
                "tick the checkbox on each mod you want to deploy.</span>"
            )
            return

        results: Dict[str, Any] = {}
        for mod_name, card in enabled:
            deployer = next(
                (d for d in all_deployers() if d.MOD_NAME == mod_name), None
            )
            if not deployer:
                continue
            try:
                r = deployer.deploy(card.config())
            except Exception as e:
                r = {'success': False, 'error': str(e)}
            results[mod_name] = r
            self._apply_result_to_card(card, r)

        # Summary
        ok = [n for n, r in results.items() if r.get('success')]
        bad = [n for n, r in results.items() if not r.get('success')]
        summary_parts = []
        if ok:
            summary_parts.append(
                f"<span style='color: {_SUCCESS};'>\u2713 Deployed {len(ok)} mod"
                f"{'s' if len(ok) != 1 else ''}: {', '.join(ok)}</span>"
            )
        if bad:
            summary_parts.append(
                f"<span style='color: {_DANGER};'>\u2717 {len(bad)} failed: "
                f"{', '.join(bad)}</span>"
            )
        summary_parts.append(
            f"<a href='open-output' style='color: {_ACCENT};'>"
            f"Open output folder</a>"
        )
        self._global_status.setText("  \u2014  ".join(summary_parts))
        self._save_to_disk()
        self.mods_deployed.emit(results)

    def _apply_result_to_card(self, card: _ModCard, result: Dict[str, Any]) -> None:
        if result.get('success'):
            path = result.get('path', '')
            self._last_output_paths[card._deployer.MOD_NAME] = path
            card.set_status(
                f"<span style='color: {_SUCCESS};'>\u2713 deployed to</span> "
                f"<a href='open:{card._deployer.MOD_NAME}' style='color: {_ACCENT};'>"
                f"{path.replace(chr(92), '/')}</a>"
            )
            # Make sure user can click the path to open
            try:
                card.status_label.linkActivated.disconnect()
            except TypeError:
                pass
            card.status_label.linkActivated.connect(self._on_status_link)
        else:
            err = result.get('error', 'unknown error')
            card.set_status(
                f"<span style='color: {_DANGER};'>\u2717 deploy failed: {err}</span>"
            )

    def _on_status_link(self, href: str) -> None:
        if href == 'open-output':
            _open_in_file_manager(DEFAULT_OUTPUT_DIR)
        elif href.startswith('open:'):
            mod_name = href.split(':', 1)[1]
            path = self._last_output_paths.get(mod_name)
            if path:
                _open_in_file_manager(path)
