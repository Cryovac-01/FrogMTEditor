"""Shared editor forms for editing and creation workflows."""
from __future__ import annotations

from .theme import *
from typing import Tuple  # not re-exported by `from .theme import *`
from . import field_bounds as _fb
from . import field_validator as _fv
from .curve_preview import InlineCurvePreview as _InlineCurvePreview

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
# (starter motor, idle throttle, rev-match blips). Visible for Gas
# AND Diesel; hidden when Fuel Type = Electric.
ICE_ONLY_ENGINE_PROPERTIES = (
    "StarterTorque",
    "StarterRPM",
    "IdleThrottle",
    "BlipThrottle",
    "BlipDurationSeconds",
)

# Engine property keys that only make sense on diesel engines
# (heavy-duty airflow efficiency, jake-brake / engine brake).
# Visible only when Fuel Type = Diesel; hidden for Gas / Electric.
DIESEL_ONLY_ENGINE_PROPERTIES = (
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

# Character-level categories used by Engine Unlock Requirements.
# Internal keys match MT's EMTCharacterLevelType enum names so the
# server can map straight to the underlying integer (CL_Driver=0,
# CL_Taxi=1, CL_Bus=2, CL_Truck=3, CL_Racer=4, CL_Wrecker=5,
# CL_Police=6).
CHARACTER_LEVEL_CHOICES = [
    ('Driver',  'Driver'),
    ('Taxi',    'Taxi'),
    ('Bus',     'Bus'),
    ('Truck',   'Truck'),
    ('Racer',   'Racer'),
    ('Tow',     'Wrecker'),
    ('Police',  'Police'),
]

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

class ArrowComboBox(QtWidgets.QComboBox):
    """QComboBox that paints a triangular ▼ arrow on the right edge
    after rendering. Works around the dark-theme drop-down arrow
    rendering as a small light rectangle on Windows. Drawn via
    QPainter so it never depends on a font glyph or a Qt image asset."""

    _ARROW_HALF_WIDTH = 5    # half-width of the triangle base
    _ARROW_HEIGHT     = 5    # vertical depth of the triangle
    _ARROW_RIGHT_PAD  = 11   # px from the right edge to the triangle's center

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        rect = self.rect()
        cx = rect.right() - self._ARROW_RIGHT_PAD
        cy = rect.center().y()
        poly = QtGui.QPolygonF([
            QtCore.QPointF(cx - self._ARROW_HALF_WIDTH, cy - self._ARROW_HEIGHT // 2),
            QtCore.QPointF(cx + self._ARROW_HALF_WIDTH, cy - self._ARROW_HEIGHT // 2),
            QtCore.QPointF(cx, cy + self._ARROW_HEIGHT),
        ])
        painter.setBrush(TEXT_COLOR)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.drawPolygon(poly)


class LevelRequirementsWidget(QtWidgets.QWidget):
    """Compact UI for the engine's LevelRequirementToBuy TMap.

    Layout:
      [ ] Unlock by default
          (checkbox; when checked, hides + ignores the rows below.
           Engine ships with NO level requirements -> unlocked at
           Driver level 1 by vanilla MT default.)
      [ Category ▼ ]  Level [ N ]  [ × ]
      [ Category ▼ ]  Level [ N ]  [ × ]
      [ + Add condition ]

    Emits `changed` whenever any visible state mutates so the parent
    PartEditorForm can mark itself dirty. Round-trips through
    to_payload() / from_payload() for sidecar persistence.
    """
    changed = QtCore.Signal()

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._rows: List[Dict[str, QtWidgets.QWidget]] = []

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        self.unlock_default_checkbox = QtWidgets.QCheckBox("Unlock by default")
        self.unlock_default_checkbox.setToolTip(
            "When checked, the engine has no level requirements and is "
            "available to the player from Driver level 1."
        )
        self.unlock_default_checkbox.toggled.connect(self._on_unlock_toggled)
        outer.addWidget(self.unlock_default_checkbox)

        # Container for the per-condition rows. Nested in a frame so
        # the show/hide behaviour also tucks any spacing nicely.
        self._rows_container = QtWidgets.QWidget()
        self._rows_layout = QtWidgets.QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(6)
        outer.addWidget(self._rows_container)

        self.add_condition_button = QtWidgets.QPushButton("+ Add condition")
        self.add_condition_button.setToolTip(
            "Add another (Category, Level) requirement. Engine unlocks "
            "only when ALL listed requirements are met."
        )
        self.add_condition_button.clicked.connect(lambda: self._add_row())
        outer.addWidget(self.add_condition_button, 0, QtCore.Qt.AlignmentFlag.AlignLeft)

    # ------------------------------------------------------------------
    # Icon rendering — keep both glyphs font-independent so the
    # delete X and the combo down-arrow always show, even on Windows
    # builds where Qt sometimes can't find a fallback glyph for the
    # multiplication sign or the BLACK DOWN-POINTING TRIANGLE.
    # ------------------------------------------------------------------
    @staticmethod
    def _render_remove_icon(size: int = 14) -> QtGui.QIcon:
        """Vector-draw an X (two diagonal strokes) for the delete
        button. No font dependency — always renders identically."""
        pix = QtGui.QPixmap(size, size)
        pix.fill(QtCore.Qt.GlobalColor.transparent)
        p = QtGui.QPainter(pix)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        pen = QtGui.QPen(TEXT_COLOR)
        pen.setWidthF(2.0)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        m = size * 0.25
        p.drawLine(QtCore.QPointF(m, m),
                   QtCore.QPointF(size - m, size - m))
        p.drawLine(QtCore.QPointF(size - m, m),
                   QtCore.QPointF(m, size - m))
        p.end()
        return QtGui.QIcon(pix)

    # ------------------------------------------------------------------
    # Row management
    # ------------------------------------------------------------------
    def _add_row(self, category_key: str = 'Driver', level: int = 1) -> None:
        row_widget = QtWidgets.QWidget()
        row_h = QtWidgets.QHBoxLayout(row_widget)
        row_h.setContentsMargins(0, 0, 0, 0)
        row_h.setSpacing(8)

        category_combo = ArrowComboBox()
        configure_field_control(category_combo, "editor")
        for label, key in CHARACTER_LEVEL_CHOICES:
            category_combo.addItem(label, key)
        for i in range(category_combo.count()):
            if category_combo.itemData(i) == category_key:
                category_combo.setCurrentIndex(i)
                break
        category_combo.setMinimumWidth(140)
        category_combo.currentIndexChanged.connect(self.changed.emit)

        level_label = QtWidgets.QLabel("Level")
        set_label_kind(level_label, "subtle")

        level_input = QtWidgets.QLineEdit(str(int(level)))
        configure_field_control(level_input, "editor")
        level_input.setValidator(QtGui.QIntValidator(1, 999, self))
        level_input.setMaximumWidth(80)
        level_input.textChanged.connect(self.changed.emit)

        remove_button = QtWidgets.QPushButton()
        remove_button.setIcon(self._render_remove_icon(14))
        remove_button.setIconSize(QtCore.QSize(14, 14))
        remove_button.setToolTip("Remove this requirement")
        remove_button.setFixedSize(28, 28)
        remove_button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        remove_button.clicked.connect(lambda _checked=False, w=row_widget: self._remove_row(w))

        row_h.addWidget(category_combo, 0)
        row_h.addWidget(level_label, 0)
        row_h.addWidget(level_input, 0)
        row_h.addWidget(remove_button, 0)
        row_h.addStretch(1)

        self._rows_layout.addWidget(row_widget)
        self._rows.append({
            'widget':   row_widget,
            'category': category_combo,
            'level':    level_input,
            'remove':   remove_button,
        })
        self._update_remove_button_visibility()
        self.changed.emit()

    def _remove_row(self, widget: QtWidgets.QWidget) -> None:
        # Refuse to remove the only remaining row — there must always
        # be at least one editable row so the user can switch back from
        # "Unlock by default" cleanly. The first row's remove button is
        # hidden anyway, so this is mostly defence-in-depth.
        if len(self._rows) <= 1:
            return
        for i, row in enumerate(self._rows):
            if row['widget'] is widget:
                row['widget'].setParent(None)
                row['widget'].deleteLater()
                self._rows.pop(i)
                break
        self._update_remove_button_visibility()
        self.changed.emit()

    def _update_remove_button_visibility(self) -> None:
        """Hide the remove button on row 0 (the primary requirement
        should always exist; if the user wants no requirements they
        check 'Unlock by default'). All other rows show the button."""
        for i, row in enumerate(self._rows):
            btn = row.get('remove')
            if btn is not None:
                btn.setVisible(i > 0)

    # ------------------------------------------------------------------
    # Unlock-by-default toggle
    # ------------------------------------------------------------------
    def _on_unlock_toggled(self, checked: bool) -> None:
        # When unlock-by-default is on, the user can't edit the rows.
        # Hide the container + add button entirely so there's no
        # ambiguity about what's active.
        self._rows_container.setVisible(not checked)
        self.add_condition_button.setVisible(not checked)
        self.changed.emit()

    # ------------------------------------------------------------------
    # Public payload + restore API
    # ------------------------------------------------------------------
    def to_payload(self) -> Dict[str, int]:
        """Return {category_key: level} for every active requirement,
        or empty dict if 'Unlock by default' is checked."""
        if self.unlock_default_checkbox.isChecked():
            return {}
        out: Dict[str, int] = {}
        for row in self._rows:
            key = str(row['category'].currentData() or '')
            try:
                level = int(row['level'].text().strip() or '1')
            except ValueError:
                level = 1
            if key and level >= 1:
                # Last write wins if the user picks the same category
                # twice — the underlying TMap can't hold duplicate keys.
                out[key] = level
        return out

    def from_payload(self, payload: Optional[Dict[str, int]]) -> None:
        """Restore widget state from a saved payload (typically from
        creation_inputs.level_requirements)."""
        # Clear any existing rows
        for row in self._rows:
            row['widget'].setParent(None)
            row['widget'].deleteLater()
        self._rows = []

        if payload is None or not payload:
            # No saved data OR explicitly empty -> default to unlocked
            self.unlock_default_checkbox.setChecked(True)
            # Still seed one (hidden) row so the user can untick and edit
            self._add_row('Driver', 1)
            return

        self.unlock_default_checkbox.setChecked(False)
        for category_key, level in payload.items():
            try:
                level_int = int(level)
            except (TypeError, ValueError):
                level_int = 1
            self._add_row(str(category_key), max(1, level_int))


class VolumeOffsetWidget(QtWidgets.QWidget):
    """Per-engine volume adjustment slider.

    Range:   -25 .. +25 (integer steps).
    Mapping: each step shifts the engine's audio output by 4%, so the
             effective multiplier is ``1.0 + (slider_value * 0.04)``.
             -25 -> 0% (silent), 0 -> 100% (vanilla), +25 -> 200%.

    Designed for the case where a user picks a sound pack tuned for a
    different vehicle class (e.g. truck sound on a sports car) and
    needs to compensate for the resulting volume mismatch.

    The widget round-trips through ``to_payload()`` / ``from_payload()``
    for sidecar persistence.  Emits ``changed`` whenever the slider
    moves so the parent form can mark itself dirty.
    """
    changed = QtCore.Signal()

    MIN_OFFSET = -25
    MAX_OFFSET = 25
    PERCENT_PER_STEP = 4  # whole-number percent shift per slider tick

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        outer = QtWidgets.QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        # Slider with tick marks at the min, 0, and max anchors.
        self._slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self._slider.setRange(self.MIN_OFFSET, self.MAX_OFFSET)
        self._slider.setValue(0)
        self._slider.setSingleStep(1)
        self._slider.setPageStep(5)
        self._slider.setTickPosition(QtWidgets.QSlider.TickPosition.TicksBelow)
        self._slider.setTickInterval(5)
        self._slider.setMinimumWidth(180)
        outer.addWidget(self._slider, 1)

        # Live numeric readout: "+12 (1.48×)" — both the offset and the
        # resulting multiplier so the user can see what they're picking
        # without doing the 4%-per-tick math in their head.
        self._value_label = QtWidgets.QLabel()
        set_label_kind(self._value_label, "fieldLabel")
        self._value_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignVCenter
                                      | QtCore.Qt.AlignmentFlag.AlignRight)
        self._value_label.setMinimumWidth(95)
        self._value_label.setToolTip(
            "Per-engine volume adjustment. Each step shifts the audio "
            "by 4%. Use to compensate when a sound pack is tuned for "
            "a different vehicle class than this engine."
        )
        outer.addWidget(self._value_label, 0)

        self._slider.valueChanged.connect(self._on_slider_changed)
        self._refresh_label(0)

    def _refresh_label(self, offset: int) -> None:
        multiplier = 1.0 + (offset * self.PERCENT_PER_STEP / 100.0)
        sign = '+' if offset > 0 else ''
        self._value_label.setText(f"{sign}{offset}  ({multiplier:.2f}×)")

    def _on_slider_changed(self, value: int) -> None:
        self._refresh_label(int(value))
        self.changed.emit()

    # ------------------------------------------------------------------
    # Round-trip API
    # ------------------------------------------------------------------
    def to_payload(self) -> int:
        """Return the current offset as an int (always whole numbers)."""
        return int(self._slider.value())

    def from_payload(self, value: Optional[int]) -> None:
        """Restore from a saved sidecar value.  None / missing -> 0."""
        try:
            v = int(value) if value is not None else 0
        except (TypeError, ValueError):
            v = 0
        v = max(self.MIN_OFFSET, min(self.MAX_OFFSET, v))
        # Block the signal so initial population doesn't dirty the form.
        was_blocked = self._slider.blockSignals(True)
        try:
            self._slider.setValue(v)
        finally:
            self._slider.blockSignals(was_blocked)
        self._refresh_label(v)


class TireVehicleClassesWidget(QtWidgets.QWidget):
    """Multi-select for the vehicle classes a tire should appear in.

    Each ticked box maps to a donor row from ``TIRE_VEHICLE_TYPE_CHOICES``
    in the VehicleParts0 DataTable. The server registers one row per
    selected class (same FName, distinct fname_number), so the modded
    tire appears in the modification list of every chosen vehicle
    class.

    Why this replaces the old single-pick combo:
    Vanilla MT stores multiple VehicleParts0 rows per tire asset (one
    per vehicle class the tire is compatible with). The previous
    "Vehicle Type" combo cloned only ONE donor row, so the resulting
    tire only appeared on that one class — giving the impression
    that "modded tires don't show up."

    Round-trips through ``to_payload()`` (returns a list of donor
    names) and ``from_payload()`` so the saved selection restores
    on fork/edit.
    """
    changed = QtCore.Signal()

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._checkboxes: List[Tuple[str, QtWidgets.QCheckBox]] = []

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        hint = QtWidgets.QLabel(
            "Pick every vehicle class the tire should show up on. "
            "One row is added to the VehicleParts0 DataTable per tick."
        )
        hint.setWordWrap(True)
        set_label_kind(hint, "fieldDesc")
        layout.addWidget(hint)

        # Skip the first 'Auto' entry — it doesn't make sense in a
        # multi-select context (the server can't auto-detect when
        # the user has explicitly selected a list).
        # Stylesheet for the indicator: Qt's default dark-theme
        # checkbox draws a 1px platform-default border that's nearly
        # invisible against the editor's near-black surface. Override
        # with an explicit 14×14 outlined box plus an accent fill on
        # check so the tick state is unambiguous at a glance.
        _indicator_qss = """
            QCheckBox {
                color: #cdd6e0;
                spacing: 8px;
                padding: 2px 0;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border-radius: 3px;
                border: 1px solid #6b7c8e;
                background: #1a2532;
            }
            QCheckBox::indicator:hover {
                border: 1px solid #9aacbd;
            }
            QCheckBox::indicator:checked {
                background: #73c686;
                border: 1px solid #73c686;
                image: url();
            }
            QCheckBox::indicator:checked:hover {
                background: #8bd599;
                border: 1px solid #8bd599;
            }
        """
        for display_label, donor_name in TIRE_VEHICLE_TYPE_CHOICES:
            if not donor_name:
                continue  # 'Auto (from template)'
            cb = QtWidgets.QCheckBox(display_label)
            cb.setStyleSheet(_indicator_qss)
            cb.toggled.connect(lambda _checked=False, s=self: s.changed.emit())
            layout.addWidget(cb)
            self._checkboxes.append((donor_name, cb))

    # ------------------------------------------------------------------
    def to_payload(self) -> List[str]:
        """Return the list of donor names corresponding to ticked boxes."""
        return [donor for donor, cb in self._checkboxes if cb.isChecked()]

    def from_payload(self, value: Optional[List[str]]) -> None:
        """Restore tick state from a saved list. None / empty / a
        legacy string value (single donor) are all handled."""
        if value is None:
            checked: set = set()
        elif isinstance(value, str):
            checked = {value} if value else set()
        else:
            checked = set(value)
        for donor, cb in self._checkboxes:
            was_blocked = cb.blockSignals(True)
            try:
                cb.setChecked(donor in checked)
            finally:
                cb.blockSignals(was_blocked)

    def has_any_checked(self) -> bool:
        return any(cb.isChecked() for _d, cb in self._checkboxes)


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
        self.level_requirements_widget: Optional[LevelRequirementsWidget] = None
        self.volume_offset_widget: Optional[VolumeOffsetWidget] = None
        self.original_volume_offset: Optional[int] = None
        self.curve_preview: Optional[_InlineCurvePreview] = None
        self.tire_vehicle_classes_widget: Optional[TireVehicleClassesWidget] = None
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
        self.level_requirements_widget = None
        self.volume_offset_widget = None
        self.original_volume_offset = None
        self.curve_preview = None
        self.tire_vehicle_classes_widget = None
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

        # If this shop key has bounds (currently 'price' and 'weight'),
        # wrap the input in a column layout so we can place an inline
        # hint label directly below it. Other shop fields (display_name,
        # description, code, sound_dir) skip the hint and go in raw.
        bounds = _fb.lookup(key, 'shop') if kind == 'line' else None
        if bounds is not None:
            container = QtWidgets.QWidget()
            container_layout = QtWidgets.QVBoxLayout(container)
            container_layout.setContentsMargins(0, 0, 0, 0)
            container_layout.setSpacing(2)
            container_layout.addWidget(widget)
            hint = _fv.make_hint_label(container)
            container_layout.addWidget(hint)
            _fv.attach(widget, bounds, hint)
            form.addRow(field_label, container)
        else:
            form.addRow(field_label, widget)

        self.shop_widgets[key] = widget
        self.shop_kinds[key] = kind

    def _add_sound_entry(self, form: QtWidgets.QFormLayout, value: str) -> None:
        label = QtWidgets.QLabel("Sound Pack")
        set_label_kind(label, "fieldLabel" if self.creator_mode else "muted")
        combo = ArrowComboBox()
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
        combo = ArrowComboBox()
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

    def _add_level_requirements_entry(self, form: QtWidgets.QFormLayout,
                                       saved: Optional[Dict[str, int]] = None) -> None:
        """Add the Engine Unlock Requirements section to the engine
        creator form. The widget exposes a checkbox for "unlock by
        default" plus a dynamic list of (Category, Level) pairs."""
        label = QtWidgets.QLabel("Engine Unlock Requirements")
        set_label_kind(label, "fieldLabel" if self.creator_mode else "muted")
        widget = LevelRequirementsWidget(self)
        widget.from_payload(saved or None)
        widget.changed.connect(self.changed.emit)
        form.addRow(label, widget)
        self.level_requirements_widget = widget

    def _add_volume_offset_entry(self, form: QtWidgets.QFormLayout,
                                  saved: Optional[int] = None) -> None:
        """Add the per-engine Volume Adjustment slider to the engine
        creator form. Value is an integer offset in [-25, +25]; each
        step shifts the engine's audio output by 4% (so the resulting
        multiplier is ``1.0 + offset * 0.04``).

        The slider is for compensating sound-pack/engine class
        mismatches — e.g. a truck sound pack on a sports car engine
        plays too quietly, so the user nudges this slider up."""
        label = QtWidgets.QLabel("Volume Adjustment")
        set_label_kind(label, "fieldLabel" if self.creator_mode else "muted")
        widget = VolumeOffsetWidget(self)
        widget.from_payload(saved)
        widget.changed.connect(self.changed.emit)
        form.addRow(label, widget)
        self.volume_offset_widget = widget

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
        combo = ArrowComboBox()
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
          - EV-only props (regen, motor power/voltage):  visible only
            when Electric.
          - ICE-only props (starter, idle, blip throttle):  visible
            only when Gas OR Diesel (anything that combusts).
          - Diesel-only props (intake efficiency, jake brake):  visible
            only when Diesel.
        Safe to call before or after the property rows have been
        built — missing keys are simply skipped."""
        if self.fuel_type_combo is None:
            return
        fuel = str(self.fuel_type_combo.currentData() or '')
        is_electric = (fuel == 'electric')
        is_diesel   = (fuel == 'diesel')
        for prop_key in EV_ONLY_ENGINE_PROPERTIES:
            wrapper = self.property_row_widgets.get(prop_key)
            if wrapper is not None:
                wrapper.setVisible(is_electric)
        for prop_key in ICE_ONLY_ENGINE_PROPERTIES:
            wrapper = self.property_row_widgets.get(prop_key)
            if wrapper is not None:
                wrapper.setVisible(not is_electric)
        for prop_key in DIESEL_ONLY_ENGINE_PROPERTIES:
            wrapper = self.property_row_widgets.get(prop_key)
            if wrapper is not None:
                wrapper.setVisible(is_diesel)

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

    def _add_tire_vehicle_type_entry(self, form: QtWidgets.QFormLayout,
                                       current_value: Any = None) -> None:
        """Multi-select for the vehicle classes a tire should appear in.

        Replaces the legacy single-pick combo. Vanilla MT uses one
        VehicleParts0 row per (tire, vehicle_class) pair — the
        previous one-row design only matched the single class of the
        chosen donor, so modded tires "didn't appear" on most
        vehicles. The multi-select lets the user tick every class
        the tire should show up on; the server creates one
        VehicleParts0 row per tick, all pointing at the same tire
        asset.

        ``current_value`` accepts both the new list-of-donors format
        AND the legacy single-string ``vehicle_type`` so old
        ``.creation.json`` sidecars round-trip cleanly.
        """
        label = QtWidgets.QLabel("Vehicle Compatibility")
        set_label_kind(label, "fieldLabel" if self.creator_mode else "muted")
        widget = TireVehicleClassesWidget(self)
        widget.from_payload(current_value)
        widget.changed.connect(self.changed.emit)
        form.addRow(label, widget)
        self.tire_vehicle_classes_widget = widget

    def _add_property_row(self, parent_layout: QtWidgets.QLayout, key: str, prop: Dict[str, Any]) -> None:
        # Hide fields that aren't actually present in this part's
        # binary layout. Showing "Not serialized on this layout" as
        # a placeholder + helper text just clutters the form with
        # rows the user can't interact with. Skip them entirely so
        # the visible form only contains editable fields.
        if prop.get("missing"):
            return
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

        # Lookup bounds for this property key. Read-only fields skip
        # validation entirely (the user can't modify them, and the
        # warning border on a disabled input would just be confusing).
        bounds = None if readonly else _fb.lookup(key, 'property')

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
                # Bounds for the synthetic peak-torque-RPM input. The
                # hint label is the row's `helper_layout` below, but
                # since this input is inline within the MaxTorque row
                # we surface bounds via tooltip only — no separate
                # hint label (would be visually noisy in this row).
                _ptrb = _fb.lookup('peak_torque_rpm', 'creator_input')
                if _ptrb is not None:
                    self.peak_torque_rpm_input.setToolTip(_ptrb.format_tooltip())
                    _hidden_hint = QtWidgets.QLabel()
                    _hidden_hint.setVisible(False)
                    _fv.attach(self.peak_torque_rpm_input, _ptrb, _hidden_hint)
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

            # Inline range hint / validation message — sits directly
            # below the input row, indented to align with the field
            # column. Only added when the field has bounds; the
            # validator handles the visibility transitions internally.
            if bounds is not None:
                hint_label = _fv.make_hint_label(wrapper)
                hint_layout = QtWidgets.QHBoxLayout()
                hint_layout.setContentsMargins(CREATOR_LABEL_WIDTH + SPACING.md, 0, 0, 0)
                hint_layout.setSpacing(0)
                hint_layout.addWidget(hint_label, 1)
                outer.addLayout(hint_layout)
                _fv.attach(line, bounds, hint_label)

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
                # Only set the line's tooltip from the helper text if
                # the validator hasn't already set its own (more
                # specific) tooltip showing the typical/hard ranges.
                if bounds is None:
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
                _hpb = _fb.lookup('max_hp', 'creator_input')
                if _hpb is not None:
                    self.max_hp_input.setToolTip(_hpb.format_tooltip())
                    _hidden_hp_hint = QtWidgets.QLabel()
                    _hidden_hp_hint.setVisible(False)
                    _fv.attach(self.max_hp_input, _hpb, _hidden_hp_hint)
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
                _phrb = _fb.lookup('peak_hp_rpm', 'creator_input')
                if _phrb is not None:
                    self.peak_hp_rpm_input.setToolTip(_phrb.format_tooltip())
                    _hidden_phr_hint = QtWidgets.QLabel()
                    _hidden_phr_hint.setVisible(False)
                    _fv.attach(self.peak_hp_rpm_input, _phrb, _hidden_phr_hint)
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

            # Inline range hint / validation message between the input
            # and the description. Same hookup as the creator branch
            # so behaviour matches in both modes.
            if bounds is not None:
                hint_label = _fv.make_hint_label(wrapper)
                layout.addWidget(hint_label)
                _fv.attach(line, bounds, hint_label)

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
            # Volume Adjustment slider belongs near the sound dropdown
            # because they're conceptually paired — picking a sound
            # pack tuned for a different vehicle class is the main
            # reason a user would touch this slider. We surface it in
            # BOTH modes (creator + regular editor) so the user can
            # re-tune an existing engine's volume without having to
            # fork it.
            creation_inputs = (metadata.get('creation_inputs') or {})
            self._add_volume_offset_entry(
                form,
                saved=creation_inputs.get('volume_offset'),
            )
            if self.creator_mode:
                self._add_vehicle_type_entry(form, creation_inputs.get('vehicle_type', ''))
                self._add_fuel_type_entry(
                    form,
                    current_value=creation_inputs.get('fuel_type', ''),
                    default_is_ev=bool(metadata.get('is_ev')),
                )
                self._add_level_requirements_entry(
                    form,
                    saved=creation_inputs.get('level_requirements'),
                )
        elif self.part_type == "tire":
            self._add_shop_entry(form, "display_name", "Display Name", shop.get("display_name") or part.get("name") or "")
            self._add_shop_entry(form, "code", "Code", shop.get("code") or "")
            self._add_shop_entry(form, "price", "Price", format_number(shop.get("price")))
            self._add_shop_entry(form, "weight", "Weight (kg)", format_number(shop.get("weight")))
            if self.creator_mode:
                creation_inputs = (metadata.get('creation_inputs') or {})
                # Prefer the new multi-select payload key
                # (vehicle_classes); fall back to the legacy single
                # vehicle_type so old sidecars round-trip cleanly.
                _saved_classes = (creation_inputs.get('vehicle_classes')
                                  or creation_inputs.get('vehicle_type')
                                  or [])
                self._add_tire_vehicle_type_entry(form, _saved_classes)

        self.content_layout.addWidget(identity_group)

        for section_title, rows in grouped_sections:
            # Drop hidden_properties (variant-driven hiding) AND any
            # field not actually serialized in this binary layout.
            # The latter prevents an empty section card when every
            # row in the group is "missing" — e.g. the tire Wear
            # and Thermal section on a layout that doesn't store
            # any of those fields.
            visible_rows = [
                (key, prop) for key, prop in rows
                if key not in self.hidden_properties
                and not prop.get('missing')
            ]
            if not visible_rows:
                continue
            if self.creator_mode:
                group, layout = build_creator_grid_card(self._display_section_title(section_title))
            else:
                group, layout = self._make_group(self._display_section_title(section_title), compact=False)
            for key, prop in visible_rows:
                self._add_property_row(layout, key, prop)
            self.content_layout.addWidget(group)

        # Inline live torque/HP preview — only in creator mode for
        # engines, since the synthetic peak_torque_rpm / max_hp /
        # peak_hp_rpm inputs that drive it only exist there. Placed
        # after the property cards so it sits below the MaxTorque /
        # MaxRPM / MaxHP rows it depends on.
        if self.creator_mode and self.part_type == "engine":
            curve_card, curve_card_layout = build_creator_grid_card(
                self._display_section_title("Curve Preview")
            )
            self.curve_preview = _InlineCurvePreview(curve_card)
            curve_card_layout.addWidget(self.curve_preview)
            self.content_layout.addWidget(curve_card)

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
        # Snapshot the volume slider's loaded value so get_changed_payload
        # can detect "user moved the slider" in non-creator mode. None
        # means the field isn't present (e.g. tire editor) — change
        # detection then short-circuits.
        self.original_volume_offset = (
            int(self.volume_offset_widget.to_payload())
            if self.volume_offset_widget is not None else None
        )
        self.scroll.verticalScrollBar().setValue(0)
        # Apply EV-only / ICE field visibility based on the current Fuel
        # Type combo selection. Run after row widgets are built; safe
        # to call even if the form has no fuel combo (no-op then).
        self._apply_fuel_type_visibility()
        # Wire live cross-field RPM curve checks (no-op when synthetic
        # peak_torque_rpm / peak_hp_rpm inputs aren't present).
        self._wire_rpm_curve_listeners()
        # Initial render so a freshly-loaded engine already shows any
        # curve issues + the inline torque/HP preview without waiting
        # for the user to type.
        self._refresh_rpm_curve_visuals()
        self._refresh_curve_preview()

    def has_changes(self) -> bool:
        return bool(self.get_changed_payload())

    # ------------------------------------------------------------------
    # Cross-field RPM curve validation
    # ------------------------------------------------------------------
    # Peak torque RPM and peak HP RPM each have their own raw bounds
    # (handled by the per-field validator), but they must also make
    # sense relative to MaxRPM. A 4000-rpm peak torque on a 5000-rpm
    # redline is reasonable; a 400-rpm peak torque on the same redline
    # is nonsense. The cross-check below runs whenever any of the
    # three fields changes, stashes the result on the affected
    # widgets via a `crossFieldResult` property, and refreshes their
    # border colour. Save-time validation_summary() folds the same
    # results into its errors/warnings list.

    _CROSS_FIELD_KEY = "crossFieldResult"

    def _read_int_field(self, widget: Optional[QtWidgets.QWidget]) -> Optional[float]:
        """Pull a numeric value out of a QLineEdit, tolerating commas
        and returning None for blank / unparseable input."""
        if widget is None:
            return None
        text = widget.text() if hasattr(widget, 'text') else ''
        return _fb.parse_value(text, 'float')

    def _is_engine_ev(self) -> bool:
        """Determine whether the current engine is an EV — used to
        skip the ICE-shaped curve checks. Prefers the live Fuel Type
        combo, falls back to the loaded metadata."""
        if self.fuel_type_combo is not None:
            try:
                fuel = str(self.fuel_type_combo.currentData() or '').lower()
                if fuel:
                    return fuel == 'electric'
            except Exception:
                pass
        meta = (self.part or {}).get('metadata') or {}
        return bool(meta.get('is_ev'))

    def _refresh_rpm_curve_visuals(self) -> None:
        """Recompute the cross-field RPM curve check and update the
        widgets' border colours + stash the result for save-time
        querying. Safe to call when the relevant fields don't exist
        (no-op in that case)."""
        max_rpm_widget = self.property_widgets.get('MaxRPM')
        pt_widget = self.peak_torque_rpm_input
        ph_widget = self.peak_hp_rpm_input
        if pt_widget is None and ph_widget is None:
            return  # No creator-mode synthetic inputs to update.

        max_rpm = self._read_int_field(max_rpm_widget)
        peak_torque = self._read_int_field(pt_widget)
        peak_hp = self._read_int_field(ph_widget)

        pt_result, ph_result = _fb.validate_rpm_curve(
            peak_torque_rpm=peak_torque,
            peak_hp_rpm=peak_hp,
            max_rpm=max_rpm,
            is_ev=self._is_engine_ev(),
        )

        for widget, result in ((pt_widget, pt_result), (ph_widget, ph_result)):
            if widget is None:
                continue
            # Stash the cross-field result so validation_summary can
            # pick it up alongside the per-field result.
            widget.setProperty(self._CROSS_FIELD_KEY,
                               {'status': result.status, 'message': result.message})
            self._apply_cross_field_border(widget, result)

    def _apply_cross_field_border(self, widget: QtWidgets.QWidget,
                                   result: _fb.ValidationResult) -> None:
        """Overlay a border colour on the widget reflecting the
        worst of (per-field result, cross-field result). Per-field
        errors win; cross-field warnings appear when per-field is OK."""
        per_field_status = _fv.current_status(widget) or 'ok'
        # Severity ordering: error > warn > ok
        order = {'ok': 0, 'warn': 1, 'error': 2}
        worst = max((per_field_status, result.status), key=lambda s: order.get(s, 0))

        # Capture the base stylesheet exactly once via a sentinel
        # property — see the matching note in field_validator._render
        # for why a falsy check on the value is wrong.
        if not widget.property('baseStyleSheetCaptured'):
            widget.setProperty('baseStyleSheet', widget.styleSheet())
            widget.setProperty('baseStyleSheetCaptured', True)
        base = widget.property('baseStyleSheet') or ''
        override = _fv._BORDER_STYLES.get(worst, '')
        widget.setStyleSheet(base + ('\n' + override if override else ''))

        # Augment the tooltip so hover surfaces the cross-field
        # message even though there's no inline label for the
        # synthetic inputs (they're inline within other rows).
        if result.status != 'ok':
            tip = widget.toolTip() or ''
            sep = '\n\n' if tip and not tip.endswith(result.message) else ''
            if result.message and result.message not in tip:
                widget.setToolTip(f'{tip}{sep}{result.message}')

    def _wire_rpm_curve_listeners(self) -> None:
        """Connect textChanged handlers on the three RPM-curve fields
        so any edit refreshes the cross-check. Also hooks the Fuel
        Type combo because EV mode toggles whether the rules apply.
        Additionally refreshes the inline curve preview (which depends
        on MaxTorque too, so MaxTorque is included in the listener
        set)."""
        widgets = [
            self.property_widgets.get('MaxRPM'),
            self.property_widgets.get('MaxTorque'),
            self.peak_torque_rpm_input,
            self.peak_hp_rpm_input,
            self.max_hp_input,
        ]

        def _refresh_all(_text=''):
            self._refresh_rpm_curve_visuals()
            self._refresh_curve_preview()

        for w in widgets:
            if w is None:
                continue
            try:
                w.textChanged.connect(_refresh_all)
            except Exception:
                pass
        if self.fuel_type_combo is not None:
            try:
                self.fuel_type_combo.currentIndexChanged.connect(
                    lambda _i=0, s=self: s._refresh_rpm_curve_visuals()
                )
            except Exception:
                pass

    def _refresh_curve_preview(self) -> None:
        """Pull the five live values out of their widgets and re-render
        the inline torque/HP preview. Safe no-op when the widget
        doesn't exist (non-creator mode, non-engine part)."""
        if self.curve_preview is None:
            return
        max_rpm     = self._read_int_field(self.property_widgets.get('MaxRPM'))
        max_torque  = self._read_int_field(self.property_widgets.get('MaxTorque'))
        peak_torque = self._read_int_field(self.peak_torque_rpm_input)
        max_hp      = self._read_int_field(self.max_hp_input)
        peak_hp     = self._read_int_field(self.peak_hp_rpm_input)
        try:
            self.curve_preview.refresh(
                max_rpm=max_rpm,
                max_torque_nm=max_torque,
                peak_torque_rpm=peak_torque,
                max_hp=max_hp,
                peak_hp_rpm=peak_hp,
            )
        except Exception:
            # Preview is non-critical — silent on failure rather than
            # blowing up the form for a chart issue.
            pass

    def validation_summary(self) -> Dict[str, List[Tuple[str, str]]]:
        """Walk every validator-attached widget on this form and
        collect its current state. Returns a dict::

            {'errors': [(field_label, message), ...],
             'warnings': [(field_label, message), ...]}

        Save flows call this before submitting so they can:
          - block the save when ``errors`` is non-empty,
          - prompt the user with a confirm dialog when only
            ``warnings`` are present.

        The label used here prefers the property's display name (via
        :func:`format_property_name`) for property fields and falls
        back to the dict key for shop fields. Skips widgets that
        have no validator attached.
        """
        errors: List[Tuple[str, str]] = []
        warnings: List[Tuple[str, str]] = []

        def _check(label: str, widget: Optional[QtWidgets.QWidget]) -> None:
            if widget is None:
                return
            status = _fv.current_status(widget)
            if status == 'error':
                errors.append((label, _fv.current_message(widget)))
            elif status == 'warn':
                warnings.append((label, _fv.current_message(widget)))

        # Property fields (MaxTorque, MaxRPM, etc.)
        for key, widget in self.property_widgets.items():
            _check(format_property_name(key), widget)

        # Shop fields (price, weight) — labels match the column titles
        # the user sees in the form.
        shop_labels = {
            'price': 'Price',
            'weight': 'Weight',
        }
        for key, widget in self.shop_widgets.items():
            label = shop_labels.get(key)
            if label is None:
                continue  # unbounded shop field (display_name etc.)
            _check(label, widget)

        # Synthetic creator inputs (only present in creator mode).
        _check('Peak Torque RPM', self.peak_torque_rpm_input)
        _check('Max HP',          self.max_hp_input)
        _check('Peak HP RPM',     self.peak_hp_rpm_input)

        # Cross-field RPM curve checks. Read the property each
        # widget stashed during the last live refresh; if a widget
        # has no cross-field result yet (form just loaded), recompute
        # one shot synchronously so save-time doesn't miss it.
        if (self.peak_torque_rpm_input is not None
                or self.peak_hp_rpm_input is not None):
            self._refresh_rpm_curve_visuals()

        def _check_cross(label: str, widget: Optional[QtWidgets.QWidget]) -> None:
            if widget is None:
                return
            raw = widget.property(self._CROSS_FIELD_KEY)
            if not raw:
                return
            status = raw.get('status')
            msg = str(raw.get('message') or '')
            if status == 'error':
                errors.append((label, msg))
            elif status == 'warn':
                warnings.append((label, msg))

        _check_cross('Peak Torque RPM (curve)', self.peak_torque_rpm_input)
        _check_cross('Peak HP RPM (curve)',     self.peak_hp_rpm_input)

        return {'errors': errors, 'warnings': warnings}

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
            # Volume slider — included whenever the user has moved it
            # off its loaded value, regardless of creator/edit mode.
            # Server side updates the .creation.json sidecar and
            # regenerates the per-engine MasterVolume Lua mod.
            if self.volume_offset_widget is not None and self.original_volume_offset is not None:
                current_vol = int(self.volume_offset_widget.to_payload())
                if current_vol != self.original_volume_offset:
                    payload["volume_offset"] = current_vol
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
        if self.level_requirements_widget is not None:
            # Serialise as JSON string so it round-trips through the
            # property dict (which expects str values) without losing
            # the dict structure. Server side decodes it back.
            import json as _json
            payload['_level_requirements'] = _json.dumps(
                self.level_requirements_widget.to_payload()
            )
        if self.volume_offset_widget is not None:
            # Per-engine audio volume adjustment, integer in [-25,+25].
            # Server saves it to .creation.json and applies as a
            # MasterVolume override on the engine's sound data asset
            # (1.0 + offset * 0.04).
            payload['_volume_offset'] = str(int(self.volume_offset_widget.to_payload()))
        if self.tire_vehicle_classes_widget is not None:
            # Multi-select replacement for the legacy `_vehicle_type`
            # tire field. JSON-encoded list of donor names so the
            # server can iterate and register one VehicleParts0 row
            # per checked class.
            import json as _json
            payload['_vehicle_classes'] = _json.dumps(
                self.tire_vehicle_classes_widget.to_payload()
            )
        # Strip thousands-separator commas from every value so users
        # can write "12,000" naturally and the server parses it fine.
        # Skip _level_requirements + _vehicle_classes: both are JSON,
        # commas are syntax there.
        _no_strip_keys = {'_level_requirements', '_vehicle_classes'}
        payload = {
            k: (v.replace(',', '') if (isinstance(v, str) and k not in _no_strip_keys) else v)
            for k, v in payload.items()
        }
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
