"""Shared editor forms for editing and creation workflows."""
from __future__ import annotations

from .theme import *

# Vehicle type choices for engine creation.
# Each entry: (display_label, donor_row_name).
# The donor_row_name is the FName of a vanilla DataTable row whose tail
# encodes compatibility with that vehicle class.  An empty string means
# "auto-detect from the template engine" (existing behaviour).
VEHICLE_TYPE_CHOICES = [
    ('Auto (from template)', ''),
    ('Heavy-Duty Truck', 'HeavyDuty_440HP'),
    ('Semi Tractor', 'HeavyDuty_540HP'),
    ('Medium-Duty Truck', 'MediumDuty_330HP'),
    ('Bus', 'Bus_400HP'),
    ('Light Truck', 'Truck_190HP'),
    ('Car (V8 / V12)', 'V12_400HP'),
    ('Car (Compact / I4)', 'I4_150HP'),
    ('Motorcycle (I4)', 'Bike_I4_100HP'),
    ('Motorcycle (I2)', 'Bike_I2_100HP'),
    ('Scooter', 'Scooter_15HP'),
    ('Electric Vehicle', 'Electric_300HP'),
]

# Engine fuel type choices. The three types Motor Town actually
# supports. Each entry: (display_label, internal_key).
# The form filters visible properties so EV-only fields are only
# shown when Electric is selected, and the underlying FuelType enum
# is auto-set from this combo at create time.
FUEL_TYPE_CHOICES = [
    ('Gasoline', 'gas'),
    ('Diesel',   'diesel'),
    ('Electric', 'electric'),
]

# Engine property keys that only make sense on EV engines. Shown on
# the form ONLY when Fuel Type = Electric, hidden for Gas / Diesel.
EV_ONLY_ENGINE_PROPERTIES = (
    "MaxRegenTorqueRatio",
    "MotorMaxPower",
    "MotorMaxVoltage",
)

# Engine property keys that only make sense on combustion engines
# (starter motor, idle throttle, rev-match blips, jake brake, etc.).
# Hidden when Fuel Type = Electric since EVs have no concept of any
# of these. Visible for Gas / Diesel.
ICE_ONLY_ENGINE_PROPERTIES = (
    "StarterTorque",
    "StarterRPM",
    "IdleThrottle",
    "BlipThrottle",
    "BlipDurationSeconds",
    "IntakeSpeedEfficiency",
    "MaxJakeBrakeStep",
)

# Maps the Fuel Type combo value to MT's FuelType enum integer
# (FuelType property on the engine row). 1=Gas, 2=Diesel, 3=Electric.
# 0=Gas (legacy alias) is intentionally not used here.
FUEL_TYPE_TO_ENUM = {
    'gas':      1,
    'diesel':   2,
    'electric': 3,
}

# Tire vehicle type choices.
# Each entry: (display_label, donor_row_name in VehicleParts0).
# The donor_row_name determines which vehicles can equip the tire.
# An empty string means "auto-detect from the donor template" (existing behaviour).
TIRE_VEHICLE_TYPE_CHOICES = [
    ('Auto (from template)', ''),
    ('Car (Standard)', 'BasicTire'),
    ('Car (Performance)', 'PerformanceTire'),
    ('Car (Drift)', 'Sideway'),
    ('Car (Offroad)', 'Offroad'),
    ('Motorcycle', 'MotorCycleTire_01'),
    ('Heavy-Duty Truck (Front)', 'BasicHeavyDutyFrontTire'),
    ('Heavy-Duty Truck (Rear)', 'BasicHeavyDutyRearTire'),
    ('Heavy Machine (Front)', 'HeavyMachineFrontTire'),
    ('Heavy Machine (Rear)', 'HeavyMachineRearTire'),
]

class PartEditorForm(QtWidgets.QWidget):
    changed = QtCore.Signal()
    # Emitted when the user changes Fuel Type to a value that requires
    # a different binary donor (e.g. Gas/Diesel <-> Electric).
    # Args: new_donor_part_path (e.g. "vanilla/Engine/Electric_300HP"),
    #       intended_fuel_type_key (e.g. "electric").
    # The owning workspace decides whether to confirm with the user
    # (when the form has unsaved property edits) and reload, or revert
    # the combo via revert_fuel_type_combo() if the user cancels.
    donor_change_requested = QtCore.Signal(str, str)

    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget] = None,
        *,
        creator_mode: bool = False,
        priority_sections: Optional[Iterable[str]] = None,
        hidden_properties: Optional[Iterable[str]] = None,
        section_title_overrides: Optional[Dict[str, str]] = None,
    ) -> None:
        super().__init__(parent)
        self.creator_mode = creator_mode
        self.priority_sections = {str(item) for item in (priority_sections or [])}
        self.hidden_properties = {str(item) for item in (hidden_properties or [])}
        self.section_title_overrides = {str(key): str(value) for key, value in (section_title_overrides or {}).items()}
        self.part: Optional[Dict[str, Any]] = None
        self.part_type = ""
        self.sound_options: List[Dict[str, str]] = []
        self.shop_widgets: Dict[str, QtWidgets.QWidget] = {}
        self.shop_kinds: Dict[str, str] = {}
        self.property_widgets: Dict[str, QtWidgets.QLineEdit] = {}
        self.prop_meta: Dict[str, Dict[str, Any]] = {}
        self.original_shop: Dict[str, str] = {}
        self.original_props: Dict[str, str] = {}
        self.peak_torque_rpm_input: Optional[QtWidgets.QLineEdit] = None
        self.max_hp_input: Optional[QtWidgets.QLineEdit] = None
        self.peak_hp_rpm_input: Optional[QtWidgets.QLineEdit] = None
        self.vehicle_type_combo: Optional[QtWidgets.QComboBox] = None
        self.fuel_type_combo: Optional[QtWidgets.QComboBox] = None
        # Row-wrapper widgets keyed by property name. Used to hide /
        # show whole rows (label + input + helper text) dynamically
        # in response to the Fuel Type combo, e.g. EV-only properties
        # show only when Electric is selected.
        self.property_row_widgets: Dict[str, QtWidgets.QWidget] = {}
        # Fuel-type swap support: remember the last successfully-applied
        # value so we can restore it if the user cancels a donor swap,
        # and a flag to suppress our handler during programmatic combo
        # updates (revert / set_fuel_type).
        self._previous_fuel_type: str = ""
        self._suppress_fuel_handler: bool = False

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10 if self.creator_mode else 0)

        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(self.scroll)

        self.content = QtWidgets.QWidget()
        self.content_layout = QtWidgets.QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0 if self.creator_mode else SPACING.sm, 0 if self.creator_mode else SPACING.sm, 0 if self.creator_mode else SPACING.sm, 0 if self.creator_mode else SPACING.sm)
        self.content_layout.setSpacing(SPACING.md if self.creator_mode else SPACING.lg)
        self.content_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.content)
        self.clear()

    def _clear_layout(self, layout: Optional[QtWidgets.QLayout]) -> None:
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            child_layout = item.layout()
            widget = item.widget()
            if child_layout is not None:
                self._clear_layout(child_layout)
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def _clear_content(self) -> None:
        self._clear_layout(self.content_layout)

    def clear(self, message: str = "Select or create a part to begin editing.") -> None:
        self.part = None
        self.part_type = ""
        self.shop_widgets = {}
        self.shop_kinds = {}
        self.property_widgets = {}
        self.prop_meta = {}
        self.original_shop = {}
        self.original_props = {}
        self.peak_torque_rpm_input = None
        self.max_hp_input = None
        self.peak_hp_rpm_input = None
        self.vehicle_type_combo = None
        self.fuel_type_combo = None
        self.property_row_widgets = {}
        self._previous_fuel_type = ""
        self._suppress_fuel_handler = False
        self._clear_content()

        frame = QtWidgets.QFrame()
        set_surface(frame, "panel")
        layout = QtWidgets.QVBoxLayout(frame)
        layout.setContentsMargins(SPACING.xl, SPACING.xl, SPACING.xl, SPACING.xl)
        layout.setSpacing(SPACING.sm)
        label = QtWidgets.QLabel(message)
        label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        set_label_kind(label, "muted")
        layout.addWidget(label)
        self.content_layout.addWidget(frame)
        if not self.creator_mode:
            self.content_layout.addStretch(1)

    def _connect_widget(self, widget: QtWidgets.QWidget) -> None:
        if isinstance(widget, QtWidgets.QLineEdit):
            widget.textChanged.connect(lambda *_: self.changed.emit())
        elif isinstance(widget, QtWidgets.QPlainTextEdit):
            widget.textChanged.connect(self.changed.emit)
        elif isinstance(widget, QtWidgets.QComboBox):
            widget.currentTextChanged.connect(lambda *_: self.changed.emit())
            widget.editTextChanged.connect(lambda *_: self.changed.emit())

    def _get_widget_value(self, key: str, mapping: Dict[str, QtWidgets.QWidget], kinds: Dict[str, str]) -> str:
        widget = mapping.get(key)
        kind = kinds.get(key, "")
        if widget is None:
            return ""
        if kind == "plain" and isinstance(widget, QtWidgets.QPlainTextEdit):
            return widget.toPlainText()
        if kind == "combo_data" and isinstance(widget, QtWidgets.QComboBox):
            return str(widget.currentData() or '')
        if kind == "combo" and isinstance(widget, QtWidgets.QComboBox):
            return widget.currentText()
        if isinstance(widget, QtWidgets.QLineEdit):
            return widget.text()
        return ""

    def _display_section_title(self, title: str) -> str:
        return self.section_title_overrides.get(title, title)

    def _make_group(self, title: str, compact: bool = False) -> tuple[QtWidgets.QGroupBox, QtWidgets.QVBoxLayout]:
        group = QtWidgets.QGroupBox(title)
        if compact:
            group.setProperty("compact", True)
        layout = QtWidgets.QVBoxLayout(group)
        if compact:
            layout.setContentsMargins(14, 14, 14, 12)
            layout.setSpacing(SPACING.sm)
        else:
            layout.setContentsMargins(16, 18, 16, 16)
            layout.setSpacing(10)
        return group, layout

    def _add_shop_entry(self, form: QtWidgets.QFormLayout, key: str, label: str, value: str, multiline: bool = False) -> None:
        field_label = QtWidgets.QLabel(label)
        set_label_kind(field_label, "fieldLabel" if self.creator_mode else "muted")
        if multiline:
            widget = QtWidgets.QPlainTextEdit()
            configure_field_control(widget, "editor")
            widget.setPlainText(value or "")
            widget.setMaximumHeight(76 if self.creator_mode else 88)
            kind = "plain"
        else:
            widget = QtWidgets.QLineEdit(value or "")
            configure_field_control(widget, "editor")
            kind = "line"
        self._connect_widget(widget)
        form.addRow(field_label, widget)
        self.shop_widgets[key] = widget
        self.shop_kinds[key] = kind

    def _add_sound_entry(self, form: QtWidgets.QFormLayout, value: str) -> None:
        label = QtWidgets.QLabel("Sound Pack")
        set_label_kind(label, "fieldLabel" if self.creator_mode else "muted")
        combo = QtWidgets.QComboBox()
        configure_field_control(combo, "editor")
        combo.setEditable(True)
        combo.addItems([item["dir"] for item in self.sound_options])
        combo.setCurrentText(value or "")
        self._connect_widget(combo)
        form.addRow(label, combo)
        self.shop_widgets["sound_dir"] = combo
        self.shop_kinds["sound_dir"] = "combo"

    def _add_vehicle_type_entry(self, form: QtWidgets.QFormLayout, current_value: str = '') -> None:
        """Add a Vehicle Type dropdown for engine creation."""
        label = QtWidgets.QLabel("Vehicle Type")
        set_label_kind(label, "fieldLabel" if self.creator_mode else "muted")
        combo = QtWidgets.QComboBox()
        configure_field_control(combo, "editor")
        for display_label, donor_name in VEHICLE_TYPE_CHOICES:
            combo.addItem(display_label, donor_name)
        # Restore previous selection if available
        if current_value:
            for i in range(combo.count()):
                if combo.itemData(i) == current_value:
                    combo.setCurrentIndex(i)
                    break
        self._connect_widget(combo)
        form.addRow(label, combo)
        self.vehicle_type_combo = combo
        self.shop_widgets["vehicle_type"] = combo
        self.shop_kinds["vehicle_type"] = "combo_data"

    def _add_fuel_type_entry(self, form: QtWidgets.QFormLayout,
                             current_value: str = '',
                             default_is_ev: bool = False) -> None:
        """Add a Fuel Type dropdown for engine creation. Sits right
        below Vehicle Type. Default selection is derived from the
        donor when available (EV donors -> Electric, otherwise
        Gasoline). User-entered value (saved on previous fork) wins
        over the donor-derived default. When the user changes the
        selection, EV-only property rows are shown / hidden so the
        form only exposes fields that apply to the chosen fuel type."""
        label = QtWidgets.QLabel("Fuel Type")
        set_label_kind(label, "fieldLabel" if self.creator_mode else "muted")
        combo = QtWidgets.QComboBox()
        configure_field_control(combo, "editor")
        for display_label, key in FUEL_TYPE_CHOICES:
            combo.addItem(display_label, key)
        # Pick the default: saved value > donor heuristic > Gasoline.
        target_key = current_value or ('electric' if default_is_ev else 'gas')
        for i in range(combo.count()):
            if combo.itemData(i) == target_key:
                combo.setCurrentIndex(i)
                break
        self._connect_widget(combo)
        # Hook our handler that decides whether to just toggle row
        # visibility (Gas <-> Diesel — same binary donor) or request
        # a donor swap (Gas/Diesel <-> Electric — different binary
        # layout). Hooked here (not via _connect_widget) so we run
        # our own logic in addition to the generic 'changed' signal.
        combo.currentIndexChanged.connect(self._handle_fuel_type_change)
        form.addRow(label, combo)
        self.fuel_type_combo = combo
        self.shop_widgets["fuel_type"] = combo
        self.shop_kinds["fuel_type"] = "combo_data"
        self._previous_fuel_type = target_key

    def _apply_fuel_type_visibility(self) -> None:
        """Toggle the rows that depend on Fuel Type:
          - EV-only properties visible only when Electric.
          - ICE-only properties (starter, idle, blip, jake brake,
            intake efficiency) visible only when Gas or Diesel.
        Safe to call before or after the property rows have been
        built — missing keys are simply skipped."""
        if self.fuel_type_combo is None:
            return
        is_electric = (self.fuel_type_combo.currentData() == 'electric')
        for prop_key in EV_ONLY_ENGINE_PROPERTIES:
            wrapper = self.property_row_widgets.get(prop_key)
            if wrapper is not None:
                wrapper.setVisible(is_electric)
        for prop_key in ICE_ONLY_ENGINE_PROPERTIES:
            wrapper = self.property_row_widgets.get(prop_key)
            if wrapper is not None:
                wrapper.setVisible(not is_electric)

    def _handle_fuel_type_change(self) -> None:
        """Called when the Fuel Type combo's selection changes. If the
        new fuel type is structurally compatible with the current
        engine binary (Gas <-> Diesel, both ICE), just retoggle row
        visibility. If the new fuel type needs a different binary
        donor (Gas/Diesel <-> Electric), emit donor_change_requested
        so the workspace can confirm with the user and reload."""
        if self.fuel_type_combo is None or self._suppress_fuel_handler:
            return
        new_fuel = str(self.fuel_type_combo.currentData() or '')
        # The current engine's nature comes from its loaded metadata.
        # is_ev=True means the binary has EV property slots; False
        # means ICE slots. A donor swap is required iff this differs
        # from the new fuel selection.
        metadata = (self.part or {}).get("metadata") or {}
        current_is_ev = bool(metadata.get("is_ev"))
        new_is_ev = (new_fuel == "electric")
        if current_is_ev == new_is_ev:
            # Same binary layout works — just retoggle visibility and
            # remember the new fuel type for any future cancel-revert.
            self._previous_fuel_type = new_fuel
            self._apply_fuel_type_visibility()
            return
        # Need a different binary donor. Pick a sensible default vanilla
        # engine for the new family and let the workspace handle the
        # confirm / fetch / reload dance.
        target_donor = "Electric_300HP" if new_is_ev else "HeavyDuty_440HP"
        self.donor_change_requested.emit(
            f"vanilla/Engine/{target_donor}", new_fuel
        )

    def has_property_edits(self) -> bool:
        """True iff the user has changed any editable property widget
        from its loaded original value. Ignores shop / vehicle-type /
        fuel-type combos so toggling them doesn't count as 'edits'.
        Used by the workspace to decide whether to confirm before
        clobbering values during a donor swap."""
        if not self.part:
            return False
        for key, widget in self.property_widgets.items():
            meta = self.prop_meta.get(key) or {}
            if not meta.get("editable"):
                continue
            if widget.text() != self.original_props.get(key, ""):
                return True
        return False

    def revert_fuel_type_combo(self) -> None:
        """Restore the Fuel Type combo to its previous successfully-
        applied value without re-triggering the change handler. Called
        by the workspace after the user cancels a donor swap."""
        if self.fuel_type_combo is None:
            return
        self._suppress_fuel_handler = True
        try:
            for i in range(self.fuel_type_combo.count()):
                if self.fuel_type_combo.itemData(i) == self._previous_fuel_type:
                    self.fuel_type_combo.setCurrentIndex(i)
                    break
        finally:
            self._suppress_fuel_handler = False

    def _add_tire_vehicle_type_entry(self, form: QtWidgets.QFormLayout, current_value: str = '') -> None:
        """Add a Vehicle Type dropdown for tire creation."""
        label = QtWidgets.QLabel("Vehicle Type")
        set_label_kind(label, "fieldLabel" if self.creator_mode else "muted")
        combo = QtWidgets.QComboBox()
        configure_field_control(combo, "editor")
        for display_label, donor_name in TIRE_VEHICLE_TYPE_CHOICES:
            combo.addItem(display_label, donor_name)
        if current_value:
            for i in range(combo.count()):
                if combo.itemData(i) == current_value:
                    combo.setCurrentIndex(i)
                    break
        self._connect_widget(combo)
        form.addRow(label, combo)
        self.vehicle_type_combo = combo
        self.shop_widgets["vehicle_type"] = combo
        self.shop_kinds["vehicle_type"] = "combo_data"

    def _add_property_row(self, parent_layout: QtWidgets.QLayout, key: str, prop: Dict[str, Any]) -> None:
        name_label = QtWidgets.QLabel(format_property_name(key))
        unit = str(prop.get("unit") or "").strip()
        readonly = bool(prop.get("editable") is False or is_readonly_property(key, self.part_type))
        value = get_edit_value(key, prop, self.part_type)
        line = QtWidgets.QLineEdit(value)
        configure_field_control(line, "editor")
        line.setReadOnly(readonly)
        if readonly and prop.get("missing"):
            line.setPlaceholderText("Not serialized on this layout")
        self._connect_widget(line)
        self.property_widgets[key] = line
        self.prop_meta[key] = {
            "editable": not readonly,
            "missing": bool(prop.get("missing")),
            "unit": unit,
        }

        desc = PROPERTY_DESCRIPTIONS.get(key) or ""
        missing_text = ""
        if readonly and prop.get("missing"):
            missing_text = "This field is part of the full known parameter surface, but this layout does not actually serialize it."

        if self.creator_mode:
            wrapper = QtWidgets.QFrame()
            set_surface(wrapper, "fieldRow")
            outer = QtWidgets.QVBoxLayout(wrapper)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.setSpacing(4)

            top = QtWidgets.QHBoxLayout()
            top.setContentsMargins(0, 0, 0, 0)
            top.setSpacing(12)
            set_label_kind(name_label, "fieldLabel")
            name_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)
            name_label.setFixedWidth(CREATOR_LABEL_WIDTH)
            top.addWidget(name_label, 0)

            # Engine creator: "Max Torque [value] N·m @ [RPM] RPM" combined row
            is_torque_row = self.creator_mode and self.part_type == "engine" and not readonly and key == "MaxTorque"
            field_wrap = QtWidgets.QWidget()
            field_layout = QtWidgets.QHBoxLayout(field_wrap)
            field_layout.setContentsMargins(0, 0, 0, 0)
            field_layout.setSpacing(8)
            if is_torque_row:
                name_label.setText("Max Torque")
                field_layout.addWidget(line, 1)
                if unit:
                    unit_label = QtWidgets.QLabel(unit)
                    set_label_kind(unit_label, "subtle")
                    unit_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
                    field_layout.addWidget(unit_label, 0)
                at_label = QtWidgets.QLabel("@")
                set_label_kind(at_label, "subtle")
                at_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                field_layout.addWidget(at_label, 0)
                self.peak_torque_rpm_input = QtWidgets.QLineEdit()
                configure_field_control(self.peak_torque_rpm_input, "editor")
                self.peak_torque_rpm_input.setPlaceholderText("RPM")
                self.peak_torque_rpm_input.setMaximumWidth(100)
                field_layout.addWidget(self.peak_torque_rpm_input, 0)
                ptr_unit = QtWidgets.QLabel("RPM")
                set_label_kind(ptr_unit, "subtle")
                ptr_unit.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
                field_layout.addWidget(ptr_unit, 0)
            else:
                field_layout.addWidget(line, 1)
                if unit:
                    unit_label = QtWidgets.QLabel(unit)
                    set_label_kind(unit_label, "subtle")
                    unit_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
                    field_layout.addWidget(unit_label, 0)

            top.addWidget(field_wrap, 1)
            outer.addLayout(top)

            helper_text = desc or missing_text
            if helper_text:
                helper_label = QtWidgets.QLabel(helper_text)
                helper_label.setWordWrap(True)
                set_label_kind(helper_label, "fieldDesc")
                helper_layout = QtWidgets.QHBoxLayout()
                helper_layout.setContentsMargins(CREATOR_LABEL_WIDTH + SPACING.md, 0, 0, 0)
                helper_layout.setSpacing(0)
                helper_layout.addWidget(helper_label, 1)
                outer.addLayout(helper_layout)
                name_label.setToolTip(helper_text)
                line.setToolTip(helper_text)

            parent_layout.addWidget(wrapper)
            # Track the row wrapper so the fuel-type visibility logic
            # can hide / show it later (label + input + helper move
            # as one unit when we toggle wrapper.visible).
            self.property_row_widgets[key] = wrapper

            # Engine creator: "Max HP [value] HP @ [RPM] RPM" row after MaxRPM
            if self.creator_mode and self.part_type == "engine" and key == "MaxRPM":
                hp_wrapper = QtWidgets.QFrame()
                set_surface(hp_wrapper, "fieldRow")
                hp_outer = QtWidgets.QVBoxLayout(hp_wrapper)
                hp_outer.setContentsMargins(0, 0, 0, 0)
                hp_outer.setSpacing(4)
                hp_top = QtWidgets.QHBoxLayout()
                hp_top.setContentsMargins(0, 0, 0, 0)
                hp_top.setSpacing(12)
                hp_name = QtWidgets.QLabel("Max HP")
                set_label_kind(hp_name, "fieldLabel")
                hp_name.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)
                hp_name.setFixedWidth(CREATOR_LABEL_WIDTH)
                hp_top.addWidget(hp_name, 0)
                hp_field = QtWidgets.QWidget()
                hp_field_layout = QtWidgets.QHBoxLayout(hp_field)
                hp_field_layout.setContentsMargins(0, 0, 0, 0)
                hp_field_layout.setSpacing(8)
                self.max_hp_input = QtWidgets.QLineEdit()
                configure_field_control(self.max_hp_input, "editor")
                self.max_hp_input.setPlaceholderText("HP")
                hp_field_layout.addWidget(self.max_hp_input, 1)
                hp_unit = QtWidgets.QLabel("HP")
                set_label_kind(hp_unit, "subtle")
                hp_unit.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
                hp_field_layout.addWidget(hp_unit, 0)
                at_label2 = QtWidgets.QLabel("@")
                set_label_kind(at_label2, "subtle")
                at_label2.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                hp_field_layout.addWidget(at_label2, 0)
                self.peak_hp_rpm_input = QtWidgets.QLineEdit()
                configure_field_control(self.peak_hp_rpm_input, "editor")
                self.peak_hp_rpm_input.setPlaceholderText("RPM")
                self.peak_hp_rpm_input.setMaximumWidth(100)
                hp_field_layout.addWidget(self.peak_hp_rpm_input, 0)
                hp_rpm_unit = QtWidgets.QLabel("RPM")
                set_label_kind(hp_rpm_unit, "subtle")
                hp_rpm_unit.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
                hp_field_layout.addWidget(hp_rpm_unit, 0)
                hp_top.addWidget(hp_field, 1)
                hp_outer.addLayout(hp_top)
                hp_desc = QtWidgets.QLabel(
                    "Peak horsepower and the RPM where it occurs. "
                    "Used together with Max Torque to shape the power curve."
                )
                hp_desc.setWordWrap(True)
                set_label_kind(hp_desc, "fieldDesc")
                hp_desc_layout = QtWidgets.QHBoxLayout()
                hp_desc_layout.setContentsMargins(CREATOR_LABEL_WIDTH + SPACING.md, 0, 0, 0)
                hp_desc_layout.setSpacing(0)
                hp_desc_layout.addWidget(hp_desc, 1)
                hp_outer.addLayout(hp_desc_layout)
                parent_layout.addWidget(hp_wrapper)

        else:
            wrapper = QtWidgets.QFrame()
            set_surface(wrapper, "fieldRow")
            layout = QtWidgets.QVBoxLayout(wrapper)
            layout.setContentsMargins(0, 0, 0, 6)
            layout.setSpacing(5)

            top = QtWidgets.QHBoxLayout()
            top.setContentsMargins(0, 0, 0, 0)
            set_label_kind(name_label, "section")
            top.addWidget(name_label)
            top.addStretch(1)
            if unit:
                unit_label = QtWidgets.QLabel(unit)
                set_label_kind(unit_label, "muted")
                top.addWidget(unit_label)
            layout.addLayout(top)
            layout.addWidget(line)

            if desc:
                desc_label = QtWidgets.QLabel(desc)
                desc_label.setWordWrap(True)
                set_label_kind(desc_label, "muted")
                layout.addWidget(desc_label)
            elif missing_text:
                missing_label = QtWidgets.QLabel(missing_text)
                missing_label.setWordWrap(True)
                set_label_kind(missing_label, "muted")
                layout.addWidget(missing_label)

            parent_layout.addWidget(wrapper)

    def load_part(self, part: Dict[str, Any], sound_options: Optional[List[Dict[str, str]]] = None) -> None:
        self.part = part
        self.part_type = str(part.get("type") or "")
        self.sound_options = list(sound_options or [])
        self.shop_widgets = {}
        self.shop_kinds = {}
        self.property_widgets = {}
        self.prop_meta = {}
        self.original_shop = {}
        self.original_props = {}
        self._clear_content()

        metadata = part.get("metadata") or {}
        shop = metadata.get("shop") or {}
        sound_meta = metadata.get("sound") or {}
        properties = part.get("properties") or {}
        grouped_sections = categorize_properties(self.part_type, properties)

        if self.creator_mode:
            identity_group, form = build_creator_form_card(self._display_section_title("Identity and Shop"))
        else:
            identity_group, identity_layout = self._make_group(self._display_section_title("Identity and Shop"))
            form = QtWidgets.QFormLayout()
            identity_layout.addLayout(form)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        label_alignment = QtCore.Qt.AlignmentFlag.AlignLeft | (QtCore.Qt.AlignmentFlag.AlignVCenter if self.creator_mode else QtCore.Qt.AlignmentFlag.AlignTop)
        form.setLabelAlignment(label_alignment)
        form.setFormAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(14 if self.creator_mode else 18)
        form.setVerticalSpacing(8 if self.creator_mode else 12)

        if self.part_type == "engine":
            self._add_shop_entry(form, "display_name", "Display Name", shop.get("display_name") or part.get("name") or "")
            self._add_shop_entry(form, "description", "Description", shop.get("description") or "", multiline=True)
            self._add_shop_entry(form, "price", "Price", format_number(shop.get("price")))
            self._add_shop_entry(form, "weight", "Weight (kg)", format_number(shop.get("weight")))
            self._add_sound_entry(form, sound_meta.get("dir") or "")
            if self.creator_mode:
                creation_inputs = (metadata.get('creation_inputs') or {})
                self._add_vehicle_type_entry(form, creation_inputs.get('vehicle_type', ''))
                self._add_fuel_type_entry(
                    form,
                    current_value=creation_inputs.get('fuel_type', ''),
                    default_is_ev=bool(metadata.get('is_ev')),
                )
        elif self.part_type == "tire":
            self._add_shop_entry(form, "display_name", "Display Name", shop.get("display_name") or part.get("name") or "")
            self._add_shop_entry(form, "code", "Code", shop.get("code") or "")
            self._add_shop_entry(form, "price", "Price", format_number(shop.get("price")))
            self._add_shop_entry(form, "weight", "Weight (kg)", format_number(shop.get("weight")))
            if self.creator_mode:
                creation_inputs = (metadata.get('creation_inputs') or {})
                self._add_tire_vehicle_type_entry(form, creation_inputs.get('vehicle_type', ''))

        self.content_layout.addWidget(identity_group)

        for section_title, rows in grouped_sections:
            visible_rows = [(key, prop) for key, prop in rows if key not in self.hidden_properties]
            if not visible_rows:
                continue
            if self.creator_mode:
                group, layout = build_creator_grid_card(self._display_section_title(section_title))
            else:
                group, layout = self._make_group(self._display_section_title(section_title), compact=False)
            for key, prop in visible_rows:
                self._add_property_row(layout, key, prop)
            self.content_layout.addWidget(group)

        if not self.creator_mode:
            self.content_layout.addStretch(1)

        # Populate creation-input fields from saved metadata (for fork persistence)
        if self.creator_mode:
            creation_inputs = metadata.get('creation_inputs') or {}
            if creation_inputs:
                if self.peak_torque_rpm_input and creation_inputs.get('peak_torque_rpm'):
                    self.peak_torque_rpm_input.setText(str(int(creation_inputs['peak_torque_rpm'])))
                if self.max_hp_input and creation_inputs.get('max_hp'):
                    _hp_val = creation_inputs['max_hp']
                    _hp_str = str(int(_hp_val)) if float(_hp_val) == int(float(_hp_val)) else str(_hp_val)
                    self.max_hp_input.setText(_hp_str)
                if self.peak_hp_rpm_input and creation_inputs.get('peak_hp_rpm'):
                    self.peak_hp_rpm_input.setText(str(int(creation_inputs['peak_hp_rpm'])))

        self.original_shop = {key: self._get_widget_value(key, self.shop_widgets, self.shop_kinds) for key in self.shop_widgets}
        self.original_props = {key: widget.text() for key, widget in self.property_widgets.items()}
        self.scroll.verticalScrollBar().setValue(0)
        # Apply EV-only / ICE field visibility based on the current Fuel
        # Type combo selection. Run after row widgets are built; safe
        # to call even if the form has no fuel combo (no-op then).
        self._apply_fuel_type_visibility()

    def has_changes(self) -> bool:
        return bool(self.get_changed_payload())

    def get_changed_payload(self) -> Dict[str, Any]:
        if not self.part:
            return {}
        properties: Dict[str, str] = {}
        for key, widget in self.property_widgets.items():
            meta = self.prop_meta.get(key) or {}
            if not meta.get("editable"):
                continue
            current = widget.text()
            if current != self.original_props.get(key, ""):
                properties[key] = current

        shop_changed = any(
            self._get_widget_value(key, self.shop_widgets, self.shop_kinds) != self.original_shop.get(key, "")
            for key in self.shop_widgets
        )

        payload: Dict[str, Any] = {}
        if properties:
            payload["properties"] = properties
        if self.part_type == "engine":
            sound_current = self.collect_sound_dir()
            if sound_current != self.original_shop.get("sound_dir", ""):
                payload["sound_dir"] = sound_current
        if shop_changed:
            payload["shop"] = self.collect_shop_values()
        return payload

    def collect_shop_values(self) -> Dict[str, Any]:
        values = {key: self._get_widget_value(key, self.shop_widgets, self.shop_kinds).strip() for key in self.shop_widgets}
        if self.part_type == "engine":
            return {
                "display_name": values.get("display_name", ""),
                "description": values.get("description", ""),
                "price": values.get("price", ""),
                "weight": values.get("weight", ""),
            }
        if self.part_type == "tire":
            return {
                "display_name": values.get("display_name", ""),
                "code": values.get("code", ""),
                "price": values.get("price", ""),
                "weight": values.get("weight", ""),
            }
        return values

    def collect_sound_dir(self) -> str:
        if self.part_type != "engine":
            return ""
        return self._get_widget_value("sound_dir", self.shop_widgets, self.shop_kinds).strip()

    def collect_property_payload_for_create(self) -> Dict[str, str]:
        payload: Dict[str, str] = {}
        for key, widget in self.property_widgets.items():
            if (self.prop_meta.get(key) or {}).get("editable"):
                payload[key] = widget.text()
        # Always include peak torque/HP RPM and Max HP (required for engine creation)
        if self.peak_torque_rpm_input:
            payload['_peak_torque_rpm'] = self.peak_torque_rpm_input.text().strip()
        if self.max_hp_input:
            payload['_max_hp'] = self.max_hp_input.text().strip()
        if self.peak_hp_rpm_input:
            payload['_peak_hp_rpm'] = self.peak_hp_rpm_input.text().strip()
        if self.vehicle_type_combo is not None:
            payload['_vehicle_type'] = str(self.vehicle_type_combo.currentData() or '')
        if self.fuel_type_combo is not None:
            fuel_key = str(self.fuel_type_combo.currentData() or '')
            payload['_fuel_type'] = fuel_key
            # Inject the FuelType property value derived from the
            # Fuel Type combo. The user-facing field is hidden in the
            # creator, but the underlying engine row still needs the
            # right enum (1=Gasoline, 2=Diesel, 3=Electric).
            enum_value = FUEL_TYPE_TO_ENUM.get(fuel_key)
            if enum_value is not None:
                payload['FuelType'] = str(enum_value)
        # Strip thousands-separator commas from every value so users
        # can write "12,000" naturally and the server parses it fine.
        payload = {k: v.replace(',', '') if isinstance(v, str) else v
                   for k, v in payload.items()}
        return payload

    def get_current_property_strings(self) -> Dict[str, str]:
        values = build_property_value_map(self.part or {})
        for key, widget in self.property_widgets.items():
            values[key] = widget.text()
        return values

    def get_engine_state(self) -> Dict[str, Any]:
        if not self.part or self.part_type != "engine":
            return {}
        return build_engine_state(
            self.part,
            property_values=self.get_current_property_strings(),
            shop_values=self.collect_shop_values(),
            sound_dir=self.collect_sound_dir(),
        )

    def get_tire_grip_g(self) -> Optional[float]:
        if not self.part or self.part_type != "tire":
            return None
        return estimate_tire_grip_g(self.part, self.get_current_property_strings())
