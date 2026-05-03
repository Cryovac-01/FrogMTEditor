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

from PySide6 import QtCore, QtGui, QtWidgets

from i18n import _ as _t

import economy_editor as eco


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
            _t("Unpacked game files not found. Select the folder containing the "
            "unpacked Motor Town files (with MotorTown/Config/ inside) to enable "
            "economy editing."),
            "warning",
        ), 1)
        self.browse_unpacked_btn = _action_button(_t("Select Unpacked Folder"), "primary")
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
        header_layout.addWidget(_label(_t("ECONOMY EDITOR"), "eyebrow"))
        header_layout.addWidget(_label(_t("Game Economy & Payment Multipliers"), "title"))
        header_layout.addWidget(_label(
            _t("Apply global multipliers to cargo payments, bus fares, taxi rates, fuel costs, "
            "and other economy settings. Select 'Custom' in any dropdown to edit individual "
            "values. Changes are written to Balance.json and DefaultMotorTownBalance.ini "
            "and packed into your mod automatically."),
            "muted",
        ))
        scroll_layout.addWidget(header_card)

        # -- Capacity Scaling Mode -----------------------------------------
        # ── Vehicle Capacity Penalty moved to LUA Scripts tab ──────────
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
        scaling_layout.addWidget(_label(_t("CARGO BALANCE"), "eyebrow"))
        scaling_layout.addWidget(_label(_t("Vehicle Capacity Penalty moved"), "section"))
        scaling_layout.addWidget(_label(
            _t("The Low / High / Off pickup-vs-truck payment reshaping lives on the "
            "<b>LUA Scripts</b> tab now, alongside the rest of the Cryovac Lua "
            "mods. Open that panel to configure and deploy "
            "<code>CryovacCargoScaling</code>."),
            "muted",
        ))
        scroll_layout.addWidget(scaling_card)

        # -- Company Drivers Card (profit-share preset removed) ----------
        # The old AI-Driver-Profit-Share preset scaled the INI's
        # VehicleOwnerProfitShare field, but that value applies to every
        # vehicle of a class globally — including AI-company and rental
        # vehicles the player does not own. A player boosting it to 20%
        # also saw 20% "owner cut" taken by non-company vehicles they
        # temporarily drove, which is unfixable via INI alone. The card
        # is retained as a stub so the section still exists in the panel
        # layout, with a note explaining where to go for per-company
        # profit share if we ever build it (runtime Lua hook).
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
        company_layout.setSpacing(8)
        company_layout.addWidget(_label(_t("COMPANY DRIVERS"), "eyebrow"))
        company_layout.addWidget(_label(_t("AI Driver Profit Share removed"), "section"))
        company_layout.addWidget(_label(
            _t("The profit-share preset was scaling "
            "<code>VehicleOwnerProfitShare</code> in the balance INI, but "
            "that field is global per vehicle class \u2014 it changed the "
            "profit share on every matching vehicle in the world, including "
            "AI-company and rental vehicles you don\u2019t own. A proper "
            "\u201conly my company\u201d profit share requires a runtime "
            "Lua hook; ask if you want one built. For now, the generated "
            "mod INI keeps vanilla profit-share values (\u2248 5% in-game)."),
            "muted",
        ))
        scroll_layout.addWidget(company_card)

        # -- Multiplier cards (all use sliders + custom checkbox) -----------
        for eyebrow, title, desc, key in [
            (_t("GLOBAL ECONOMY"), _t("Cargo & Delivery Payment Multiplier"),
             _t("Cargo delivery payments, tow/rescue rewards, box trailer payments, job income."),
             "economy"),
            (_t("BUS RATES"), _t("Bus Payment Multiplier"),
             _t("Bus base payment and per-100m payment rate."),
             "bus"),
            (_t("TAXI RATES"), _t("Taxi Payment Multiplier"),
             _t("Taxi payment per 100 meters."),
             "taxi"),
            (_t("AMBULANCE RATES"), _t("Ambulance Payment Multiplier"),
             _t("Ambulance payment per 100 meters."),
             "ambulance"),
            (_t("FUEL COSTS"), _t("Fuel & Roadside Refueling Multiplier"),
             _t("Fuel cost per liter and roadside refueling base cost."),
             "fuel"),
            (_t("VEHICLE COSTS"), _t("Tow-to-Road Cost Multiplier"),
             _t("Roadside tow-to-road cost per km."),
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
        cargo_layout.addWidget(_label(_t("CARGO PAYMENT PREVIEW"), "eyebrow"))
        cargo_layout.addWidget(_label(_t("Payment Multipliers by Cargo Type"), "section"))
        self.cargo_custom_hint = _label(
            _t("Economy is set to Custom — edit the 'Modified' column to set each cargo value independently."),
            "warning",
        )
        self.cargo_custom_hint.setVisible(False)
        cargo_layout.addWidget(self.cargo_custom_hint)
        cargo_layout.addWidget(_label(
            _t("Shows vanilla values and what they become after applying the economy multiplier."),
            "muted",
        ))

        self.cargo_table = QtWidgets.QTableWidget()
        self.cargo_table.setColumnCount(3)
        self.cargo_table.setHorizontalHeaderLabels([_t("Cargo Type"), _t("Vanilla"), _t("Modified")])
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
        ini_layout.addWidget(_label(_t("INI ECONOMY PREVIEW"), "eyebrow"))
        ini_layout.addWidget(_label(_t("DefaultMotorTownBalance.ini Values"), "section"))
        self.ini_custom_hint = _label(
            _t("One or more categories set to Custom — edit the 'Modified' column for those rows."),
            "warning",
        )
        self.ini_custom_hint.setVisible(False)
        ini_layout.addWidget(self.ini_custom_hint)

        self.ini_table = QtWidgets.QTableWidget()
        self.ini_table.setColumnCount(4)
        self.ini_table.setHorizontalHeaderLabels([_t("Setting"), _t("Category"), _t("Vanilla"), _t("Modified")])
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

        self.status_label = _label(_t("No changes applied yet."), "muted")
        actions_layout.addWidget(self.status_label, 1)

        self.reset_button = _action_button(_t("Reset to Vanilla"), "danger")
        self.reset_button.clicked.connect(self._on_reset)
        actions_layout.addWidget(self.reset_button)

        self.preview_button = _action_button(_t("Preview Changes"), "secondary")
        self.preview_button.clicked.connect(self._on_preview)
        actions_layout.addWidget(self.preview_button)

        self.apply_button = _action_button(_t("Apply Economy Settings"), "primary")
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

        custom_cb = QtWidgets.QCheckBox(_t("Custom"))
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
            self, _t("Select Unpacked Motor Town Folder"),
            "", QtWidgets.QFileDialog.Option.ShowDirsOnly,
        )
        if folder:
            if eco.set_vanilla_root(folder):
                self.vanilla_banner.setVisible(False)
                self.status_label.setText(_t("Unpacked files found! Economy editor is ready."))
                self.status_label.setStyleSheet(f"color: {_SUCCESS}; font-size: 12px; font-weight: 600;")
                self._on_preview()
            else:
                self.status_label.setText(
                    _t("Could not find Balance.json or DefaultMotorTownBalance.ini in the selected folder.")
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

        # Note: capacity_scaling_mode is managed by the LUA Scripts tab
        # now (see lua_mods/cargo_scaling.py). Legacy values here are
        # ignored on load.

        # profit_share was removed from the panel — the preset was
        # global per vehicle class, affecting non-owned vehicles too.
        # Legacy values saved here are ignored on load.

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
            'economy': _t('Cargo payments'),
            'bus': _t('Bus fares'),
            'taxi': _t('Taxi rates'),
            'ambulance': _t('Ambulance rates'),
            'fuel': _t('Fuel costs'),
            'vehicle': _t('Tow-to-road costs'),
        }
        mults = {}
        customs = {}
        for key in ('economy', 'bus', 'taxi', 'ambulance', 'fuel', 'vehicle'):
            mults[key] = self._get_slider_value(key)
            customs[key] = getattr(self, f'{key}_custom').isChecked()
            preview = getattr(self, f'{key}_preview')
            if customs[key]:
                preview.setText(_t("Custom mode \u2014 edit values in the table below"))
            elif abs(mults[key] - 1.0) > 0.01:
                preview.setText(f"{preview_labels[key]} \u00d7 {mults[key]:.1f}")
            else:
                preview.setText(_t("No change (vanilla values)"))

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
        settings['custom_cargo_overrides'] = self._custom_cargo_values
        settings['custom_ini_overrides'] = self._custom_ini_values

        # Check if vanilla paths are set before applying
        if not eco.vanilla_paths_ok():
            self.status_label.setText(
                _t("Cannot apply: unpacked game files not found. "
                "Click 'Select Unpacked Folder' above.")
            )
            self.status_label.setStyleSheet("color: #e74c3c; font-size: 12px;")
            return

        result = eco.apply_all_economy_settings(settings)

        if result.get('success'):
            mults = result['multipliers']

            def _fmt(v):
                if v == 'custom':
                    return _t('Custom')
                return f"\u00d7{v:.1f}"

            self.status_label.setText(
                _t("Applied: Economy {economy}, Bus {bus}, Taxi {taxi}, Amb {amb}, Fuel {fuel}, Veh {veh}").format(
                    economy=_fmt(mults['economy']),
                    bus=_fmt(mults['bus']),
                    taxi=_fmt(mults['taxi']),
                    amb=_fmt(mults['ambulance']),
                    fuel=_fmt(mults['fuel']),
                    veh=_fmt(mults['vehicle'])
                )
            )
            self.status_label.setStyleSheet(f"color: {_SUCCESS}; font-size: 12px; font-weight: 600;")
            self.economy_applied.emit(result)
        else:
            error_msg = _t("Error applying settings: {error}").format(error=result)
            self.status_label.setText(error_msg)
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

        self._custom_cargo_values = {}
        self._custom_ini_values = {}

        eco.remove_economy_mod_files()
        reset_settings = {
            'custom_cargo_overrides': {},
            'custom_ini_overrides': {},
        }
        for key in ('economy', 'bus', 'taxi', 'ambulance', 'fuel', 'vehicle'):
            reset_settings[f'{key}_multiplier'] = 1.0
            reset_settings[f'{key}_custom'] = False
        eco.save_economy_settings(reset_settings)
        self.status_label.setText(_t("Reset to vanilla values. Economy mod files removed."))
        self.status_label.setStyleSheet(f"color: {_WARNING}; font-size: 12px;")
        self._on_preview()
