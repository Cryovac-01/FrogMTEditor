"""
Economy Editor panel for the Frog Mod Editor Qt UI.

Provides:
  - Global economy multiplier selector (2x, 3x, 5x, 10x, Custom)
  - Separate Bus, Taxi, and Ambulance rate multipliers
  - Cargo payment breakdown table (editable in Custom mode)
  - INI settings preview table (editable in Custom mode)
  - Preview of modified values before applying
"""
from __future__ import annotations

import os
import subprocess
import sys

from PySide6 import QtCore, QtGui, QtWidgets

import economy_editor as eco
import cargo_scaling_deployer as cargo_lua


# ---------------------------------------------------------------------------
# Colour tokens (consistent with main app theme)
# ---------------------------------------------------------------------------
_BG = "#161c26"
_SURFACE = "#1c2533"
_CARD = "#212c3d"
_BORDER = "#2d3948"
_TEXT = "#edf2f7"
_MUTED = "#8b97a8"
_ACCENT = "#67bfd9"
_SUCCESS = "#6fcf97"
_WARNING = "#f2c94c"
_PILL_BG = "#21303a"
_EDITABLE_BG = "#2a3a4a"


def _label(text: str, kind: str = "body") -> QtWidgets.QLabel:
    lbl = QtWidgets.QLabel(text)
    lbl.setWordWrap(True)
    if kind == "title":
        lbl.setStyleSheet(f"color: {_TEXT}; font-size: 16px; font-weight: 600;")
    elif kind == "section":
        lbl.setStyleSheet(f"color: {_TEXT}; font-size: 13px; font-weight: 600;")
    elif kind == "muted":
        lbl.setStyleSheet(f"color: {_MUTED}; font-size: 12px;")
    elif kind == "eyebrow":
        lbl.setStyleSheet(f"color: {_MUTED}; font-size: 10px; font-weight: 700; letter-spacing: 1px;")
    elif kind == "accent":
        lbl.setStyleSheet(f"color: {_ACCENT}; font-size: 13px; font-weight: 600;")
    elif kind == "success":
        lbl.setStyleSheet(f"color: {_SUCCESS}; font-size: 12px; font-weight: 600;")
    elif kind == "warning":
        lbl.setStyleSheet(f"color: {_WARNING}; font-size: 12px;")
    else:
        lbl.setStyleSheet(f"color: {_TEXT}; font-size: 13px;")
    return lbl


def _combo(items: list, current: str = "") -> QtWidgets.QComboBox:
    cb = QtWidgets.QComboBox()
    cb.addItems(items)
    if current and current in items:
        cb.setCurrentText(current)
    cb.setStyleSheet(f"""
        QComboBox {{
            background: {_CARD};
            color: {_TEXT};
            border: 1px solid {_BORDER};
            border-radius: 4px;
            padding: 6px 12px;
            font-size: 13px;
            min-width: 140px;
        }}
        QComboBox::drop-down {{
            border: none;
        }}
        QComboBox QAbstractItemView {{
            background: {_CARD};
            color: {_TEXT};
            border: 1px solid {_BORDER};
            selection-background-color: {_ACCENT};
        }}
    """)
    return cb


def _action_button(text: str, role: str = "primary") -> QtWidgets.QPushButton:
    btn = QtWidgets.QPushButton(text)
    if role == "primary":
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {_ACCENT};
                color: #0b1410;
                border: none;
                border-radius: 4px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: #7dcce4;
            }}
        """)
    elif role == "danger":
        btn.setStyleSheet(f"""
            QPushButton {{
                background: #c0392b;
                color: {_TEXT};
                border: none;
                border-radius: 4px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: #e74c3c;
            }}
        """)
    else:
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {_CARD};
                color: {_TEXT};
                border: 1px solid {_BORDER};
                border-radius: 4px;
                padding: 8px 20px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: {_BORDER};
            }}
        """)
    return btn


_TABLE_STYLE = f"""
    QTableWidget {{
        background: {_CARD};
        color: {_TEXT};
        border: 1px solid {_BORDER};
        border-radius: 4px;
        gridline-color: {_BORDER};
        font-size: 12px;
    }}
    QTableWidget::item {{
        padding: 4px 8px;
    }}
    QTableWidget::item:selected {{
        background: {_EDITABLE_BG};
    }}
    QHeaderView::section {{
        background: {_SURFACE};
        color: {_MUTED};
        border: 1px solid {_BORDER};
        padding: 6px 8px;
        font-size: 11px;
        font-weight: 600;
    }}
"""


class EconomyEditorPanel(QtWidgets.QWidget):
    """Full economy editor panel with multiplier controls and cargo table."""

    economy_applied = QtCore.Signal(dict)  # emitted after successful apply

    def __init__(self, parent: QtWidgets.QWidget = None) -> None:
        super().__init__(parent)
        self._custom_cargo_values: dict = {}   # cargo_name -> float
        self._custom_ini_values: dict = {}     # field_name -> float
        self._build_ui()
        self._load_current_state()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.setStyleSheet(f"background: {_BG};")
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"background: {_BG};")

        scroll_widget = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(16)

        # -- Vanilla path warning banner (hidden if paths are ok) -----------
        self.vanilla_banner = QtWidgets.QFrame()
        self.vanilla_banner.setStyleSheet(f"""
            QFrame {{
                background: #2a1f1f;
                border: 1px solid #6b3030;
                border-radius: 8px;
            }}
        """)
        banner_layout = QtWidgets.QHBoxLayout(self.vanilla_banner)
        banner_layout.setContentsMargins(20, 12, 20, 12)
        banner_layout.setSpacing(12)
        banner_layout.addWidget(_label(
            "Unpacked game files not found. Select the folder containing the "
            "unpacked Motor Town files (with MotorTown/Config/ inside) to enable "
            "economy editing.",
            "warning",
        ), 1)
        self.browse_unpacked_btn = _action_button("Select Unpacked Folder", "primary")
        self.browse_unpacked_btn.clicked.connect(self._browse_unpacked_folder)
        banner_layout.addWidget(self.browse_unpacked_btn)
        self.vanilla_banner.setVisible(not eco.vanilla_paths_ok())
        scroll_layout.addWidget(self.vanilla_banner)

        # -- Header --------------------------------------------------------
        header_card = QtWidgets.QFrame()
        header_card.setStyleSheet(f"""
            QFrame {{
                background: {_SURFACE};
                border: 1px solid {_BORDER};
                border-radius: 8px;
            }}
        """)
        header_layout = QtWidgets.QVBoxLayout(header_card)
        header_layout.setContentsMargins(20, 16, 20, 16)
        header_layout.setSpacing(6)
        header_layout.addWidget(_label("ECONOMY EDITOR", "eyebrow"))
        header_layout.addWidget(_label("Game Economy & Payment Multipliers", "title"))
        header_layout.addWidget(_label(
            "Apply global multipliers to cargo payments, bus fares, taxi rates, fuel costs, "
            "and other economy settings. Select 'Custom' in any dropdown to edit individual "
            "values. Changes are written to Balance.json and DefaultMotorTownBalance.ini "
            "and packed into your mod automatically.",
            "muted",
        ))
        scroll_layout.addWidget(header_card)

        # -- Capacity Scaling Mode -----------------------------------------
        scaling_card = QtWidgets.QFrame()
        scaling_card.setStyleSheet(f"""
            QFrame {{
                background: {_SURFACE};
                border: 1px solid {_BORDER};
                border-radius: 8px;
            }}
        """)
        scaling_layout = QtWidgets.QVBoxLayout(scaling_card)
        scaling_layout.setContentsMargins(20, 16, 20, 16)
        scaling_layout.setSpacing(8)
        scaling_layout.addWidget(_label("CARGO BALANCE", "eyebrow"))
        scaling_layout.addWidget(_label("Vehicle Capacity Penalty (Lua mod)", "section"))
        scaling_layout.addWidget(_label(
            "Reshapes how per-unit cargo payment drops as vehicle capacity grows. "
            "Small-vehicle pay is identical under every mode \u2014 only the decay slope changes. "
            "Low: halves the penalty so big trucks catch up (~60% more per unit vs vanilla at the same capacity). "
            "High: 1.5\u00d7 steeper \u2014 big trucks earn even less. "
            "Off: no penalty at all \u2014 every vehicle size earns the small-truck rate for the same cargo.\n\n"
            "This is delivered as a runtime Lua mod (CryovacCargoScaling) that modifies "
            "FCargoRow.PaymentPer1KmMultiplierByMaxWeight in the live Cargos_01 DataTable at session start. "
            "Click Deploy below to generate the mod folder \u2014 requires UE4SS installed in Motor Town.",
            "muted",
        ))

        # Button group for the 4 modes
        _SCALING_BTN_STYLE = f"""
            QPushButton {{
                background: {_CARD};
                color: {_TEXT};
                border: 1px solid {_BORDER};
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {_BORDER};
            }}
            QPushButton:checked {{
                background: {_ACCENT};
                color: #0b1410;
                border-color: {_ACCENT};
            }}
        """
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(8)
        self._scaling_buttons = {}
        self._scaling_group = QtWidgets.QButtonGroup(self)
        self._scaling_group.setExclusive(True)
        for mode_key, label_text, tooltip in [
            ("Vanilla", "Vanilla", "No change. Weight penalty scalar = 1.0\u00d7. Default Motor Town behavior."),
            ("Low", "Low", "Half the weight penalty (scalar 0.5\u00d7). Small trucks unchanged; big trucks earn ~60% more per unit than vanilla at the same capacity."),
            ("High", "High", "1.5\u00d7 weight penalty. Small trucks unchanged; big trucks earn less than vanilla. Makes overly-sized loadouts more costly."),
            ("Off", "Off", "No weight penalty at all (scalar 0.0\u00d7). Every vehicle size earns the small-vehicle rate for the same cargo."),
        ]:
            btn = QtWidgets.QPushButton(label_text)
            btn.setCheckable(True)
            btn.setStyleSheet(_SCALING_BTN_STYLE)
            btn.setToolTip(tooltip)
            self._scaling_buttons[mode_key] = btn
            self._scaling_group.addButton(btn)
            btn_row.addWidget(btn)
        self._scaling_buttons["Vanilla"].setChecked(True)
        btn_row.addStretch(1)
        scaling_layout.addLayout(btn_row)

        self._scaling_group.buttonClicked.connect(lambda *_: self._on_preview())

        self.scaling_preview = _label("", "accent")
        scaling_layout.addWidget(self.scaling_preview)

        # -- Deploy row inside the card ------------------------------------
        deploy_row = QtWidgets.QHBoxLayout()
        deploy_row.setSpacing(10)
        deploy_row.setContentsMargins(0, 6, 0, 0)

        self.scaling_deploy_btn = QtWidgets.QPushButton("Deploy Lua mod")
        self.scaling_deploy_btn.setToolTip(
            "Generate the CryovacCargoScaling folder with the selected mode "
            "baked in. Requires UE4SS installed in Motor Town \u2014 click for "
            "full setup instructions."
        )
        self.scaling_deploy_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_ACCENT};
                color: #0b1410;
                border: 1px solid {_ACCENT};
                border-radius: 4px;
                padding: 7px 18px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: #7cd0e6;
            }}
            QPushButton:pressed {{
                background: #4ea8c2;
            }}
            QPushButton:disabled {{
                background: {_BORDER};
                color: {_MUTED};
                border-color: {_BORDER};
            }}
        """)
        self.scaling_deploy_btn.clicked.connect(self._on_deploy_scaling_lua)
        deploy_row.addWidget(self.scaling_deploy_btn)

        self.scaling_help_btn = QtWidgets.QPushButton("Setup instructions")
        self.scaling_help_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {_ACCENT};
                border: 1px solid {_BORDER};
                border-radius: 4px;
                padding: 7px 14px;
                font-size: 12px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: {_BORDER};
            }}
        """)
        self.scaling_help_btn.clicked.connect(self._on_show_scaling_help)
        deploy_row.addWidget(self.scaling_help_btn)

        deploy_row.addStretch(1)
        scaling_layout.addLayout(deploy_row)

        self.scaling_deploy_status = _label("", "muted")
        self.scaling_deploy_status.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextBrowserInteraction
        )
        self.scaling_deploy_status.setOpenExternalLinks(False)
        self.scaling_deploy_status.linkActivated.connect(self._on_scaling_status_link)
        scaling_layout.addWidget(self.scaling_deploy_status)

        scroll_layout.addWidget(scaling_card)

        # -- Company Drivers Card ------------------------------------------
        company_card = QtWidgets.QFrame()
        company_card.setStyleSheet(f"""
            QFrame {{
                background: {_SURFACE};
                border: 1px solid {_BORDER};
                border-radius: 8px;
            }}
        """)
        company_layout = QtWidgets.QVBoxLayout(company_card)
        company_layout.setContentsMargins(20, 16, 20, 16)
        company_layout.setSpacing(10)
        company_layout.addWidget(_label("COMPANY DRIVERS", "eyebrow"))

        # --- Profit Share ---
        company_layout.addWidget(_label("AI Driver Profit Share", "section"))
        company_layout.addWidget(_label(
            "Percentage of route earnings you receive from hired company drivers. "
            "Vanilla is ~5%. Higher values make company routes more profitable.",
            "muted",
        ))

        _PROFIT_BTN_STYLE = f"""
            QPushButton {{
                background: {_CARD};
                color: {_TEXT};
                border: 1px solid {_BORDER};
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {_BORDER};
            }}
            QPushButton:checked {{
                background: {_ACCENT};
                color: #0b1410;
                border-color: {_ACCENT};
            }}
        """
        profit_row = QtWidgets.QHBoxLayout()
        profit_row.setSpacing(8)
        self._profit_buttons = {}
        self._profit_group = QtWidgets.QButtonGroup(self)
        self._profit_group.setExclusive(True)
        for preset_label in eco.PROFIT_SHARE_LABELS:
            btn = QtWidgets.QPushButton(preset_label.replace(' (Vanilla)', ''))
            btn.setCheckable(True)
            btn.setStyleSheet(_PROFIT_BTN_STYLE)
            btn.setProperty('preset_label', preset_label)
            self._profit_buttons[preset_label] = btn
            self._profit_group.addButton(btn)
            profit_row.addWidget(btn)
        self._profit_buttons['5% (Vanilla)'].setChecked(True)
        profit_row.addStretch(1)
        company_layout.addLayout(profit_row)

        self._profit_group.buttonClicked.connect(lambda *_: self._on_preview())

        self.profit_preview = _label("", "accent")
        company_layout.addWidget(self.profit_preview)

        scroll_layout.addWidget(company_card)

        # -- Multiplier cards (all use sliders + custom checkbox) -----------
        for eyebrow, title, desc, key in [
            ("GLOBAL ECONOMY", "Cargo & Delivery Payment Multiplier",
             "Cargo delivery payments, tow/rescue rewards, box trailer payments, job income.",
             "economy"),
            ("BUS RATES", "Bus Payment Multiplier",
             "Bus base payment and per-100m payment rate.",
             "bus"),
            ("TAXI RATES", "Taxi Payment Multiplier",
             "Taxi payment per 100 meters.",
             "taxi"),
            ("AMBULANCE RATES", "Ambulance Payment Multiplier",
             "Ambulance payment per 100 meters.",
             "ambulance"),
            ("FUEL COSTS", "Fuel & Roadside Refueling Multiplier",
             "Fuel cost per liter and roadside refueling base cost.",
             "fuel"),
            ("VEHICLE COSTS", "Tow-to-Road Cost Multiplier",
             "Roadside tow-to-road cost per km.",
             "vehicle"),
        ]:
            card = self._build_slider_card(eyebrow, title, desc, key)
            scroll_layout.addWidget(card)

        # -- Cargo Payment Preview Table -----------------------------------
        cargo_card = QtWidgets.QFrame()
        cargo_card.setStyleSheet(f"""
            QFrame {{
                background: {_SURFACE};
                border: 1px solid {_BORDER};
                border-radius: 8px;
            }}
        """)
        cargo_layout = QtWidgets.QVBoxLayout(cargo_card)
        cargo_layout.setContentsMargins(20, 16, 20, 16)
        cargo_layout.setSpacing(8)
        cargo_layout.addWidget(_label("CARGO PAYMENT PREVIEW", "eyebrow"))
        cargo_layout.addWidget(_label("Payment Multipliers by Cargo Type", "section"))
        self.cargo_custom_hint = _label(
            "Economy is set to Custom — edit the 'Modified' column to set each cargo value independently.",
            "warning",
        )
        self.cargo_custom_hint.setVisible(False)
        cargo_layout.addWidget(self.cargo_custom_hint)
        cargo_layout.addWidget(_label(
            "Shows vanilla values and what they become after applying the economy multiplier.",
            "muted",
        ))

        self.cargo_table = QtWidgets.QTableWidget()
        self.cargo_table.setColumnCount(3)
        self.cargo_table.setHorizontalHeaderLabels(["Cargo Type", "Vanilla", "Modified"])
        self.cargo_table.horizontalHeader().setStretchLastSection(True)
        self.cargo_table.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeMode.Stretch
        )
        self.cargo_table.setAlternatingRowColors(True)
        self.cargo_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.cargo_table.verticalHeader().setVisible(False)
        self.cargo_table.setMinimumHeight(300)
        self.cargo_table.setStyleSheet(_TABLE_STYLE)
        self.cargo_table.cellChanged.connect(self._on_cargo_cell_edited)
        cargo_layout.addWidget(self.cargo_table, 1)
        scroll_layout.addWidget(cargo_card)

        # -- INI Settings Preview ------------------------------------------
        ini_card = QtWidgets.QFrame()
        ini_card.setStyleSheet(f"""
            QFrame {{
                background: {_SURFACE};
                border: 1px solid {_BORDER};
                border-radius: 8px;
            }}
        """)
        ini_layout = QtWidgets.QVBoxLayout(ini_card)
        ini_layout.setContentsMargins(20, 16, 20, 16)
        ini_layout.setSpacing(8)
        ini_layout.addWidget(_label("INI ECONOMY PREVIEW", "eyebrow"))
        ini_layout.addWidget(_label("DefaultMotorTownBalance.ini Values", "section"))
        self.ini_custom_hint = _label(
            "One or more categories set to Custom — edit the 'Modified' column for those rows.",
            "warning",
        )
        self.ini_custom_hint.setVisible(False)
        ini_layout.addWidget(self.ini_custom_hint)

        self.ini_table = QtWidgets.QTableWidget()
        self.ini_table.setColumnCount(4)
        self.ini_table.setHorizontalHeaderLabels(["Setting", "Category", "Vanilla", "Modified"])
        self.ini_table.horizontalHeader().setStretchLastSection(True)
        self.ini_table.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeMode.Stretch
        )
        self.ini_table.setAlternatingRowColors(True)
        self.ini_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.ini_table.verticalHeader().setVisible(False)
        self.ini_table.setMinimumHeight(250)
        self.ini_table.setStyleSheet(_TABLE_STYLE)
        self.ini_table.cellChanged.connect(self._on_ini_cell_edited)
        ini_layout.addWidget(self.ini_table, 1)
        scroll_layout.addWidget(ini_card)

        # -- Action Buttons ------------------------------------------------
        actions_card = QtWidgets.QFrame()
        actions_card.setStyleSheet(f"""
            QFrame {{
                background: {_SURFACE};
                border: 1px solid {_BORDER};
                border-radius: 8px;
            }}
        """)
        actions_layout = QtWidgets.QHBoxLayout(actions_card)
        actions_layout.setContentsMargins(20, 12, 20, 12)
        actions_layout.setSpacing(12)

        self.status_label = _label("No changes applied yet.", "muted")
        actions_layout.addWidget(self.status_label, 1)

        self.reset_button = _action_button("Reset to Vanilla", "danger")
        self.reset_button.clicked.connect(self._on_reset)
        actions_layout.addWidget(self.reset_button)

        self.preview_button = _action_button("Preview Changes", "secondary")
        self.preview_button.clicked.connect(self._on_preview)
        actions_layout.addWidget(self.preview_button)

        self.apply_button = _action_button("Apply Economy Settings", "primary")
        self.apply_button.clicked.connect(self._on_apply)
        actions_layout.addWidget(self.apply_button)

        scroll_layout.addWidget(actions_card)
        scroll_layout.addStretch(1)
        scroll.setWidget(scroll_widget)
        root.addWidget(scroll, 1)

    def _build_slider_card(
        self, eyebrow: str, title: str, description: str, key: str,
        min_val: float = 0.2, max_val: float = 10.0, step: float = 0.1,
        default: float = 1.0,
    ) -> QtWidgets.QFrame:
        """Build a multiplier card with a slider and a Custom checkbox.

        Stores per card:
          self.{key}_slider   – QSlider (int range mapped to floats)
          self.{key}_value    – QLabel showing current numeric value
          self.{key}_custom   – QCheckBox for custom mode
          self.{key}_preview  – preview text label
          self._{key}_slider_row – the widget holding the slider (hidden when Custom)
        """
        card = QtWidgets.QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {_SURFACE};
                border: 1px solid {_BORDER};
                border-radius: 8px;
            }}
        """)
        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)
        layout.addWidget(_label(eyebrow, "eyebrow"))

        # Title row: title on left, Custom checkbox on right
        title_row = QtWidgets.QHBoxLayout()
        title_row.setSpacing(16)
        title_col = QtWidgets.QVBoxLayout()
        title_col.setSpacing(4)
        title_col.addWidget(_label(title, "section"))
        title_col.addWidget(_label(description, "muted"))
        title_row.addLayout(title_col, 1)

        custom_cb = QtWidgets.QCheckBox("Custom")
        custom_cb.setStyleSheet(f"""
            QCheckBox {{
                color: {_MUTED};
                font-size: 12px;
                spacing: 6px;
            }}
            QCheckBox::indicator {{
                width: 16px; height: 16px;
                border: 1px solid {_BORDER};
                border-radius: 3px;
                background: {_CARD};
            }}
            QCheckBox::indicator:checked {{
                background: {_ACCENT};
                border-color: {_ACCENT};
            }}
        """)
        setattr(self, f'{key}_custom', custom_cb)
        title_row.addWidget(custom_cb, 0,
                            QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignTop)
        layout.addLayout(title_row)

        # Slider widget (hidden when Custom is checked)
        slider_widget = QtWidgets.QWidget()
        slider_layout = QtWidgets.QHBoxLayout(slider_widget)
        slider_layout.setContentsMargins(0, 0, 0, 0)
        slider_layout.setSpacing(12)

        min_lbl = _label(f"{min_val:.1f}x", "muted")
        min_lbl.setFixedWidth(36)
        slider_layout.addWidget(min_lbl)

        int_min = int(round(min_val / step))
        int_max = int(round(max_val / step))
        int_default = int(round(default / step))

        slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        slider.setRange(int_min, int_max)
        slider.setValue(int_default)
        slider.setTickPosition(QtWidgets.QSlider.TickPosition.TicksBelow)
        slider.setTickInterval(int(round(1.0 / step)))
        slider.setSingleStep(1)
        slider.setPageStep(int(round(1.0 / step)))
        slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background: {_CARD};
                border: 1px solid {_BORDER};
                height: 6px;
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {_ACCENT};
                border: none;
                width: 16px; height: 16px;
                margin: -6px 0;
                border-radius: 8px;
            }}
            QSlider::handle:horizontal:hover {{ background: #7dcce4; }}
            QSlider::sub-page:horizontal {{
                background: {_ACCENT};
                border-radius: 3px;
            }}
        """)
        slider_layout.addWidget(slider, 1)

        max_lbl = _label(f"{max_val:.0f}x", "muted")
        max_lbl.setFixedWidth(30)
        slider_layout.addWidget(max_lbl)

        value_label = _label(f"{default:.1f}x", "accent")
        value_label.setFixedWidth(50)
        value_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        value_label.setStyleSheet(f"color: {_ACCENT}; font-size: 15px; font-weight: 700;")
        slider_layout.addWidget(value_label)

        layout.addWidget(slider_widget)

        # Preview line
        preview_label = _label("", "accent")
        setattr(self, f'{key}_preview', preview_label)
        layout.addWidget(preview_label)

        # Store references
        setattr(self, f'{key}_slider', slider)
        setattr(self, f'{key}_value', value_label)
        setattr(self, f'_{key}_slider_widget', slider_widget)
        setattr(self, f'_{key}_step', step)

        # Slider value change → update label + preview
        def _on_slider_changed(int_pos, _key=key, _step=step, _vlabel=value_label):
            val = int_pos * _step
            _vlabel.setText(f"{val:.1f}x")
            style = (f"color: {_MUTED};" if abs(val - 1.0) < 0.01
                     else f"color: {_ACCENT};")
            _vlabel.setStyleSheet(style + " font-size: 15px; font-weight: 700;")
            self._on_preview()

        slider.valueChanged.connect(_on_slider_changed)

        # Custom checkbox toggle → show/hide slider, refresh preview
        def _on_custom_toggled(checked, _key=key, _sw=slider_widget):
            _sw.setVisible(not checked)
            self._on_preview()

        custom_cb.toggled.connect(_on_custom_toggled)

        return card

    def _get_profit_share_label(self) -> str:
        """Return the preset label for the currently selected profit share."""
        for btn in self._profit_group.buttons():
            if btn.isChecked():
                return btn.property('preset_label') or '5% (Vanilla)'
        return '5% (Vanilla)'

    def _set_profit_share_label(self, label: str) -> None:
        """Select a profit share preset button."""
        btn = self._profit_buttons.get(label)
        if btn:
            btn.setChecked(True)
        else:
            self._profit_buttons['5% (Vanilla)'].setChecked(True)

    def _get_capacity_scaling_mode(self) -> str:
        """Return the currently selected capacity scaling mode."""
        for mode_key, btn in self._scaling_buttons.items():
            if btn.isChecked():
                return mode_key
        return 'Vanilla'

    def _set_capacity_scaling_mode(self, mode: str) -> None:
        """Select a capacity scaling mode button."""
        btn = self._scaling_buttons.get(mode)
        if btn:
            btn.setChecked(True)
        else:
            self._scaling_buttons['Vanilla'].setChecked(True)

    # ------------------------------------------------------------------
    # CryovacCargoScaling Lua-mod deploy
    # ------------------------------------------------------------------
    def _on_deploy_scaling_lua(self) -> None:
        """Generate the CryovacCargoScaling Lua mod folder for the current mode."""
        mode = self._get_capacity_scaling_mode()
        result = cargo_lua.deploy(mode)
        if result.get('success'):
            path = result['path']
            self._last_scaling_deploy_path = path
            # Keep the inline status short — the big dialog carries the
            # long-form instructions.
            self.scaling_deploy_status.setText(
                f"<span style='color: {_SUCCESS};'>"
                f"\u2713 Deployed {mode} mode to </span>"
                f"<a href='open-folder' style='color: {_ACCENT};'>"
                f"{path.replace(chr(92), '/')}</a>"
                f"<br><span style='color: {_MUTED};'>"
                f"Click the path above to open the output folder. "
                f"See \"Setup instructions\" for how to install."
                f"</span>"
            )
            self._show_scaling_deploy_dialog(mode, path)
        else:
            err = result.get('error', 'unknown error')
            self.scaling_deploy_status.setText(
                f"<span style='color: #f07070;'>\u2717 Deploy failed: {err}</span>"
            )

    def _on_show_scaling_help(self) -> None:
        """Open the full setup-instructions dialog without deploying."""
        mode = self._get_capacity_scaling_mode()
        self._show_scaling_deploy_dialog(mode, path=None)

    def _show_scaling_deploy_dialog(self, mode: str, path) -> None:
        """Modal dialog with full UE4SS + install instructions."""
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(
            f"CryovacCargoScaling \u2014 {'Deployed' if path else 'Setup instructions'}"
        )
        dlg.setMinimumSize(640, 520)

        layout = QtWidgets.QVBoxLayout(dlg)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        header = _label(
            f"Mode: {mode}  \u2014  weight-penalty scalar "
            f"\u00d7{cargo_lua.MODE_WEIGHT_FACTOR[mode]}",
            "title",
        )
        layout.addWidget(header)

        if path:
            loc = _label(
                f"<span style='color: {_SUCCESS};'>Output folder:</span> "
                f"<code>{path}</code>",
                "muted",
            )
            loc.setTextInteractionFlags(
                QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
            )
            layout.addWidget(loc)

        text = QtWidgets.QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText(cargo_lua.get_install_instructions(mode))
        text.setStyleSheet(f"""
            QPlainTextEdit {{
                background: {_CARD};
                color: {_TEXT};
                border: 1px solid {_BORDER};
                border-radius: 4px;
                font-family: Consolas, 'Courier New', monospace;
                font-size: 12px;
            }}
        """)
        layout.addWidget(text, 1)

        btn_row = QtWidgets.QHBoxLayout()
        if path:
            open_btn = QtWidgets.QPushButton("Open output folder")
            open_btn.clicked.connect(lambda: self._open_in_file_manager(path))
            btn_row.addWidget(open_btn)

        ue4ss_btn = QtWidgets.QPushButton("Open UE4SS releases page")
        ue4ss_btn.clicked.connect(lambda: QtGui.QDesktopServices.openUrl(
            QtCore.QUrl("https://github.com/UE4SS-RE/RE-UE4SS/releases")
        ))
        btn_row.addWidget(ue4ss_btn)

        btn_row.addStretch(1)

        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        close_btn.setDefault(True)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)
        dlg.exec()

    def _on_scaling_status_link(self, href: str) -> None:
        """Handle the 'open-folder' link inside the deploy status label."""
        if href == 'open-folder' and getattr(self, '_last_scaling_deploy_path', None):
            self._open_in_file_manager(self._last_scaling_deploy_path)

    @staticmethod
    def _open_in_file_manager(path: str) -> None:
        """Best-effort cross-platform 'show folder in Explorer/Finder/xdg-open'."""
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
            # Opening is a convenience, not critical. Silent fail.
            pass

    def _get_slider_value(self, key: str) -> float:
        """Read the current float multiplier from a slider card."""
        slider = getattr(self, f'{key}_slider', None)
        step = getattr(self, f'_{key}_step', 0.1)
        if slider is not None:
            return round(slider.value() * step, 2)
        return 1.0

    def _set_slider_value(self, key: str, val: float) -> None:
        """Set a slider to a given float multiplier."""
        slider = getattr(self, f'{key}_slider', None)
        step = getattr(self, f'_{key}_step', 0.1)
        if slider is not None:
            slider.setValue(int(round(val / step)))

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------
    def _browse_unpacked_folder(self) -> None:
        """Let the user pick the Unpacked game folder."""
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Unpacked Motor Town Folder",
            "", QtWidgets.QFileDialog.Option.ShowDirsOnly,
        )
        if folder:
            if eco.set_vanilla_root(folder):
                self.vanilla_banner.setVisible(False)
                self.status_label.setText("Unpacked files found! Economy editor is ready.")
                self.status_label.setStyleSheet(f"color: {_SUCCESS}; font-size: 12px; font-weight: 600;")
                self._on_preview()
            else:
                self.status_label.setText(
                    "Could not find Balance.json or DefaultMotorTownBalance.ini in the selected folder."
                )
                self.status_label.setStyleSheet("color: #e74c3c; font-size: 12px;")

    def _load_current_state(self) -> None:
        """Load saved economy settings and populate sliders/checkboxes."""
        settings = eco.load_economy_settings()

        for key in ('economy', 'bus', 'taxi', 'ambulance', 'fuel', 'vehicle'):
            saved = settings.get(f'{key}_multiplier', 1.0)
            # Handle legacy preset labels (e.g. '2x', '1x (Vanilla)')
            if isinstance(saved, str):
                mult = eco.MULTIPLIER_PRESETS.get(saved, 1.0)
                if mult is None:
                    # Was "Custom" — set slider to 1.0 and check the Custom box
                    self._set_slider_value(key, 1.0)
                    getattr(self, f'{key}_custom').setChecked(True)
                    continue
                saved = mult
            self._set_slider_value(key, float(saved))
            is_custom = settings.get(f'{key}_custom', False)
            getattr(self, f'{key}_custom').setChecked(bool(is_custom))

        # Load capacity scaling mode
        saved_mode = settings.get('capacity_scaling_mode', 'Vanilla')
        # Migrate legacy boolean setting
        if isinstance(saved_mode, bool):
            saved_mode = 'Off' if saved_mode else 'Vanilla'
        self._set_capacity_scaling_mode(str(saved_mode))

        # Load profit share
        self._set_profit_share_label(settings.get('profit_share', '5% (Vanilla)'))

        # Load any saved custom overrides
        self._custom_cargo_values = dict(settings.get('custom_cargo_overrides', {}))
        self._custom_ini_values = dict(settings.get('custom_ini_overrides', {}))

        self._on_preview()

    # ------------------------------------------------------------------
    # Custom cell editing handlers
    # ------------------------------------------------------------------
    def _on_cargo_cell_edited(self, row: int, col: int) -> None:
        """Handle user editing a cargo value in Custom mode."""
        if col != 2:  # Only Modified column
            return
        if not self.economy_custom.isChecked():
            return  # Not in custom mode

        name_item = self.cargo_table.item(row, 0)
        val_item = self.cargo_table.item(row, 2)
        if not name_item or not val_item:
            return
        try:
            new_val = float(val_item.text())
            self._custom_cargo_values[name_item.text()] = new_val
            val_item.setForeground(QtGui.QColor(_ACCENT))
        except ValueError:
            val_item.setForeground(QtGui.QColor("#e74c3c"))

    def _on_ini_cell_edited(self, row: int, col: int) -> None:
        """Handle user editing an INI value in Custom mode."""
        if col != 3:  # Only Modified column
            return

        fields = eco.INI_ECONOMY_FIELDS
        if row >= len(fields):
            return
        field_name, _, category = fields[row]

        # Check if this row's category is in Custom mode
        cat_key_map = {
            'cargo': 'economy', 'tow': 'economy',
            'bus': 'bus', 'taxi': 'taxi', 'ambulance': 'ambulance',
            'fuel': 'fuel', 'vehicle': 'vehicle',
        }
        cb_key = cat_key_map.get(category)
        if cb_key:
            custom_cb = getattr(self, f'{cb_key}_custom', None)
            if custom_cb and not custom_cb.isChecked():
                return  # Not in custom mode for this category

        val_item = self.ini_table.item(row, 3)
        if not val_item:
            return
        try:
            new_val = float(val_item.text().replace(',', ''))
            self._custom_ini_values[field_name] = new_val
            val_item.setForeground(QtGui.QColor(_ACCENT))
        except ValueError:
            val_item.setForeground(QtGui.QColor("#e74c3c"))

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------
    def _on_preview(self) -> None:
        """Update preview tables with current slider/checkbox selections."""
        preview_labels = {
            'economy': 'Cargo payments',
            'bus': 'Bus fares',
            'taxi': 'Taxi rates',
            'ambulance': 'Ambulance rates',
            'fuel': 'Fuel costs',
            'vehicle': 'Tow-to-road costs',
        }
        mults = {}
        customs = {}
        for key in ('economy', 'bus', 'taxi', 'ambulance', 'fuel', 'vehicle'):
            mults[key] = self._get_slider_value(key)
            customs[key] = getattr(self, f'{key}_custom').isChecked()
            preview = getattr(self, f'{key}_preview')
            if customs[key]:
                preview.setText("Custom mode \u2014 edit values in the table below")
            elif abs(mults[key] - 1.0) > 0.01:
                preview.setText(f"{preview_labels[key]} \u00d7 {mults[key]:.1f}")
            else:
                preview.setText("No change (vanilla values)")

        cap_mode = self._get_capacity_scaling_mode()
        _mode_previews = {
            'Vanilla': "Weight penalty \u00d7 1.0 \u2014 default Motor Town behavior",
            'Low': "Weight penalty \u00d7 0.5 \u2014 big trucks earn ~60% more per unit vs vanilla",
            'High': "Weight penalty \u00d7 1.5 \u2014 big trucks earn less than vanilla, small trucks unchanged",
            'Off': "Weight penalty \u00d7 0 \u2014 every vehicle size earns the small-vehicle rate",
        }
        self.scaling_preview.setText(_mode_previews.get(cap_mode, ""))

        # Profit share preview
        profit_label = self._get_profit_share_label()
        profit_mult = eco.PROFIT_SHARE_PRESETS.get(profit_label, 1.0)
        if abs(profit_mult - 1.0) < 0.001:
            self.profit_preview.setText("")
        else:
            self.profit_preview.setText(
                f"Profit share \u00d7{profit_mult:.1f} from vanilla "
                f"({profit_label.replace(' (Vanilla)', '')})"
            )

        any_ini_custom = any(customs[k] for k in customs)
        self.cargo_custom_hint.setVisible(customs['economy'])
        self.ini_custom_hint.setVisible(any_ini_custom)

        self._update_cargo_table(mults['economy'], customs['economy'])
        self._update_ini_table(
            mults['economy'], mults['bus'], mults['taxi'], mults['ambulance'],
            mults['fuel'], mults['vehicle'],
            customs['economy'], customs['bus'], customs['taxi'],
            customs['ambulance'], customs['fuel'], customs['vehicle'],
        )

    def _update_cargo_table(self, eco_mult, eco_is_custom: bool) -> None:
        """Refresh cargo table. In Custom mode, Modified column is editable.

        Reflects Balance.json PaymentMultipliers only. The per-vehicle
        capacity penalty (Vanilla/Low/High/Off mode on this panel) is a
        separate axis delivered via the CryovacCargoScaling Lua mod and
        does not show up in this table.
        """
        self.cargo_table.blockSignals(True)
        vanilla_cargo = eco.get_cargo_payments(vanilla=True)
        self.cargo_table.setRowCount(len(vanilla_cargo))

        for i, (name, base_val) in enumerate(sorted(vanilla_cargo.items())):
            # Name column (never editable)
            name_item = QtWidgets.QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self.cargo_table.setItem(i, 0, name_item)

            # Vanilla column (never editable)
            van_item = QtWidgets.QTableWidgetItem(f"{base_val:.2f}")
            van_item.setFlags(van_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self.cargo_table.setItem(i, 1, van_item)

            # Modified column
            if eco_is_custom:
                # Use custom value if set, otherwise default to vanilla
                custom_val = self._custom_cargo_values.get(name, base_val)
                mod_item = QtWidgets.QTableWidgetItem(f"{custom_val:.2f}")
                mod_item.setFlags(mod_item.flags() | QtCore.Qt.ItemFlag.ItemIsEditable)
                if custom_val != base_val:
                    mod_item.setForeground(QtGui.QColor(_ACCENT))
                else:
                    mod_item.setForeground(QtGui.QColor(_TEXT))
                mod_item.setBackground(QtGui.QColor(_EDITABLE_BG))
            else:
                modified_val = round(base_val * (eco_mult or 1.0), 6)
                mod_item = QtWidgets.QTableWidgetItem(f"{modified_val:.2f}")
                mod_item.setFlags(mod_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                if modified_val != base_val:
                    mod_item.setForeground(QtGui.QColor(_ACCENT))
            self.cargo_table.setItem(i, 2, mod_item)

        self.cargo_table.blockSignals(False)

    def _update_ini_table(self, eco_mult, bus_mult, taxi_mult, amb_mult,
                          fuel_mult, veh_mult,
                          eco_custom, bus_custom, taxi_custom, amb_custom,
                          fuel_custom, veh_custom) -> None:
        """Refresh INI table. Rows with Custom categories are editable."""
        self.ini_table.blockSignals(True)
        vanilla_ini = eco.load_vanilla_balance_ini()
        fields = eco.INI_ECONOMY_FIELDS
        self.ini_table.setRowCount(len(fields))

        for i, (field_name, display_name, category) in enumerate(fields):
            base_val = vanilla_ini.get(field_name, 'N/A')

            # Determine multiplier and custom status for this row
            if category == 'bus':
                mult = bus_mult
                is_custom = bus_custom
            elif category == 'taxi':
                mult = taxi_mult
                is_custom = taxi_custom
            elif category == 'ambulance':
                mult = amb_mult
                is_custom = amb_custom
            elif category in ('cargo', 'tow'):
                mult = eco_mult
                is_custom = eco_custom
            elif category == 'fuel':
                mult = fuel_mult
                is_custom = fuel_custom
            elif category == 'vehicle':
                mult = veh_mult
                is_custom = veh_custom
            else:
                mult = 1.0
                is_custom = False

            # Name and Category columns (never editable)
            name_item = QtWidgets.QTableWidgetItem(display_name)
            name_item.setFlags(name_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self.ini_table.setItem(i, 0, name_item)

            cat_item = QtWidgets.QTableWidgetItem(category.title())
            cat_item.setFlags(cat_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self.ini_table.setItem(i, 1, cat_item)

            if isinstance(base_val, (int, float)):
                # Vanilla column
                van_item = QtWidgets.QTableWidgetItem(f"{base_val:,.2f}")
                van_item.setFlags(van_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                self.ini_table.setItem(i, 2, van_item)

                # Modified column
                if is_custom:
                    custom_val = self._custom_ini_values.get(field_name, base_val)
                    mod_item = QtWidgets.QTableWidgetItem(f"{custom_val:,.2f}")
                    mod_item.setFlags(mod_item.flags() | QtCore.Qt.ItemFlag.ItemIsEditable)
                    if custom_val != base_val:
                        mod_item.setForeground(QtGui.QColor(_ACCENT))
                    else:
                        mod_item.setForeground(QtGui.QColor(_TEXT))
                    mod_item.setBackground(QtGui.QColor(_EDITABLE_BG))
                else:
                    mod_val = base_val * (mult if mult is not None else 1.0)
                    mod_item = QtWidgets.QTableWidgetItem(f"{mod_val:,.2f}")
                    mod_item.setFlags(mod_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                    if mod_val != base_val:
                        mod_item.setForeground(QtGui.QColor(_ACCENT))
                self.ini_table.setItem(i, 3, mod_item)
            else:
                van_item = QtWidgets.QTableWidgetItem(str(base_val))
                van_item.setFlags(van_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                self.ini_table.setItem(i, 2, van_item)
                mod_item = QtWidgets.QTableWidgetItem(str(base_val))
                mod_item.setFlags(mod_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                self.ini_table.setItem(i, 3, mod_item)

        self.ini_table.blockSignals(False)

    # ------------------------------------------------------------------
    # Apply / Reset
    # ------------------------------------------------------------------
    def _on_apply(self) -> None:
        """Apply current multiplier settings."""
        # Gather custom values from tables before applying
        self._collect_custom_values_from_tables()

        settings = {}
        for key in ('economy', 'bus', 'taxi', 'ambulance', 'fuel', 'vehicle'):
            settings[f'{key}_multiplier'] = self._get_slider_value(key)
            settings[f'{key}_custom'] = getattr(self, f'{key}_custom').isChecked()
        settings['capacity_scaling_mode'] = self._get_capacity_scaling_mode()
        settings['profit_share'] = self._get_profit_share_label()
        settings['custom_cargo_overrides'] = self._custom_cargo_values
        settings['custom_ini_overrides'] = self._custom_ini_values

        # Check if vanilla paths are set before applying
        if not eco.vanilla_paths_ok():
            self.status_label.setText(
                "Cannot apply: unpacked game files not found. "
                "Click 'Select Unpacked Folder' above."
            )
            self.status_label.setStyleSheet("color: #e74c3c; font-size: 12px;")
            return

        result = eco.apply_all_economy_settings(settings)

        if result.get('success'):
            mults = result['multipliers']

            def _fmt(v):
                if v == 'custom':
                    return 'Custom'
                return f"\u00d7{v:.1f}"

            self.status_label.setText(
                f"Applied: Economy {_fmt(mults['economy'])}, "
                f"Bus {_fmt(mults['bus'])}, "
                f"Taxi {_fmt(mults['taxi'])}, "
                f"Amb {_fmt(mults['ambulance'])}, "
                f"Fuel {_fmt(mults['fuel'])}, "
                f"Veh {_fmt(mults['vehicle'])}"
            )
            self.status_label.setStyleSheet(f"color: {_SUCCESS}; font-size: 12px; font-weight: 600;")
            self.economy_applied.emit(result)
        else:
            self.status_label.setText(f"Error applying settings: {result}")
            self.status_label.setStyleSheet(f"color: #e74c3c; font-size: 12px;")

    def _collect_custom_values_from_tables(self) -> None:
        """Read current custom values from editable table cells."""
        if self.economy_custom.isChecked():
            # Economy is Custom — read all cargo table Modified values
            vanilla_cargo = eco.get_cargo_payments(vanilla=True)
            sorted_names = sorted(vanilla_cargo.keys())
            for i, name in enumerate(sorted_names):
                item = self.cargo_table.item(i, 2)
                if item:
                    try:
                        val = float(item.text().replace(',', ''))
                        self._custom_cargo_values[name] = val
                    except ValueError:
                        pass

        # Read INI custom values for any category that's in Custom mode
        fields = eco.INI_ECONOMY_FIELDS
        cat_key_map = {
            'cargo': 'economy', 'tow': 'economy',
            'bus': 'bus', 'taxi': 'taxi', 'ambulance': 'ambulance',
            'fuel': 'fuel', 'vehicle': 'vehicle',
        }
        for i, (field_name, _, category) in enumerate(fields):
            cb_key = cat_key_map.get(category)
            if not cb_key:
                continue
            custom_cb = getattr(self, f'{cb_key}_custom', None)
            if custom_cb and custom_cb.isChecked():
                item = self.ini_table.item(i, 3)
                if item:
                    try:
                        val = float(item.text().replace(',', ''))
                        self._custom_ini_values[field_name] = val
                    except ValueError:
                        pass

    def _on_reset(self) -> None:
        """Reset all multipliers to vanilla."""
        for key in ('economy', 'bus', 'taxi', 'ambulance', 'fuel', 'vehicle'):
            self._set_slider_value(key, 1.0)
            getattr(self, f'{key}_custom').setChecked(False)
        self._set_capacity_scaling_mode('Vanilla')
        self._set_profit_share_label('5% (Vanilla)')

        self._custom_cargo_values = {}
        self._custom_ini_values = {}

        eco.remove_economy_mod_files()
        reset_settings = {
            'capacity_scaling_mode': 'Vanilla',
            'profit_share': '5% (Vanilla)',
            'custom_cargo_overrides': {},
            'custom_ini_overrides': {},
        }
        for key in ('economy', 'bus', 'taxi', 'ambulance', 'fuel', 'vehicle'):
            reset_settings[f'{key}_multiplier'] = 1.0
            reset_settings[f'{key}_custom'] = False
        eco.save_economy_settings(reset_settings)
        self.status_label.setText("Reset to vanilla values. Economy mod files removed.")
        self.status_label.setStyleSheet(f"color: {_WARNING}; font-size: 12px;")
        self._on_preview()
