"""Single source of truth for field input bounds in the Engine Creator
and the regular editor.

Each field has TWO ranges:

  ``typical_*``   The safe, sensible range based on vanilla MT engines
                  + community modding experience. Going outside this
                  range is allowed but the UI shows a warning.

  ``hard_*``      The absolute limit. Going outside this range is
                  blocked at save time — values here cause crashes,
                  freezes, broken physics, or game refusal-to-load.

The ranges are derived from the in-codebase ``PROPERTY_DESCRIPTIONS``
in ``native_services.py`` (which already documents vanilla ranges and
known dangers per field) plus pak-data sweeps. When in doubt the
typical bounds err on the wide side — the goal is "catch obvious
typos and prevent crashes," not "police the user's tuning."

Validation never coerces or clamps — it only classifies a value as
``ok | warn | error``. The widget layer decides what to do (warning
border, error message, save blocked, etc.)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class FieldBounds:
    """Soft + hard range for one editable field.

    Attributes:
        typical_min, typical_max: Soft warning range. Values outside
            this range are allowed but flagged as unusual.
        hard_min, hard_max: Save-blocking range. Values outside this
            range are rejected on save.
        unit: Display unit for the inline hint ('Nm', 'rpm', 'kg').
        kind: 'int' or 'float' — controls parsing + format.
        zero_ok: When False, exactly zero is treated as an error
            (some fields like MaxRPM crash the game at zero even
            though our hard_min is technically 0).
    """
    typical_min: float
    typical_max: float
    hard_min: float
    hard_max: float
    unit: str = ''
    kind: str = 'float'  # 'int' | 'float'
    zero_ok: bool = True

    def format_hint(self) -> str:
        """Tiny inline-hint text shown under the input. Picks the
        shortest representation that's still informative."""
        unit = f' {self.unit}' if self.unit else ''
        return f'typical: {self._fmt(self.typical_min)}–{self._fmt(self.typical_max)}{unit}'

    def format_tooltip(self) -> str:
        """Hover tooltip showing both ranges."""
        unit = f' {self.unit}' if self.unit else ''
        lines = [
            f'Typical range: {self._fmt(self.typical_min)} – {self._fmt(self.typical_max)}{unit}',
            f'Hard limit:    {self._fmt(self.hard_min)} – {self._fmt(self.hard_max)}{unit}',
        ]
        if not self.zero_ok:
            lines.append('(Zero is not allowed)')
        return '\n'.join(lines)

    def _fmt(self, val: float) -> str:
        if self.kind == 'int':
            return f'{int(val):,}'
        # Trim trailing zeros for float display.
        if val == int(val) and abs(val) < 100000:
            return f'{int(val):,}'
        if abs(val) < 1:
            return f'{val:.3f}'.rstrip('0').rstrip('.')
        return f'{val:,g}'


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of validating one field's text value."""
    status: str         # 'ok' | 'warn' | 'error'
    message: str = ''   # User-facing reason; empty for 'ok'.

    @property
    def is_error(self) -> bool:
        return self.status == 'error'

    @property
    def is_warn(self) -> bool:
        return self.status == 'warn'


_OK = ValidationResult('ok', '')


def _err(msg: str) -> ValidationResult:
    return ValidationResult('error', msg)


def _warn(msg: str) -> ValidationResult:
    return ValidationResult('warn', msg)


# ──────────────────────────────────────────────────────────────────────
# Bounds catalog
# ──────────────────────────────────────────────────────────────────────
# Numeric values derived from PROPERTY_DESCRIPTIONS and vanilla ranges.
# When the description says "vanilla range X–Y" we widen typical to ~3×
# Y on the high side and Y/3 on the low side, keeping hard limits at
# documented danger thresholds.
#
# Field keys here MUST match the keys used in:
#   - PartEditorForm.shop_widgets (e.g. 'price', 'weight')
#   - engine_property_widgets (raw property names like 'MaxTorque')
#   - the synthetic creator inputs (peak_torque_rpm, max_hp, etc.)

# ── Shop fields (used in both Creator and Editor) ──
SHOP_BOUNDS: Dict[str, FieldBounds] = {
    'price': FieldBounds(
        typical_min=100, typical_max=300_000,
        hard_min=0, hard_max=10_000_000,
        unit='$', kind='int',
    ),
    'weight': FieldBounds(
        typical_min=5, typical_max=2000,
        hard_min=0.1, hard_max=20_000,
        unit='kg', kind='float', zero_ok=False,
    ),
}

# ── Engine creator's synthetic inputs (computed, then baked into the
#    torque curve / DT row when the engine is generated) ──
CREATOR_INPUT_BOUNDS: Dict[str, FieldBounds] = {
    'peak_torque_rpm': FieldBounds(
        typical_min=1500, typical_max=12000,
        hard_min=400, hard_max=30000,
        unit='rpm', kind='int',
    ),
    'max_hp': FieldBounds(
        typical_min=10, typical_max=2500,
        hard_min=1, hard_max=10000,
        unit='HP', kind='float',
    ),
    'peak_hp_rpm': FieldBounds(
        typical_min=3000, typical_max=20000,
        hard_min=400, hard_max=30000,
        unit='rpm', kind='int',
    ),
    # volume_offset is already constrained at the widget layer
    # (-25..+25 slider with integer steps) so doesn't need bounds here.
}

# ── Engine property fields (variant-dependent visibility) ──
# Numeric ranges come from PROPERTY_DESCRIPTIONS in native_services.py.
# Where the description warns about specific dangers (e.g. "below 600
# RPM the engine may break"), the hard_min/max enforce that.
PROPERTY_BOUNDS: Dict[str, FieldBounds] = {
    # Core performance
    'MaxTorque': FieldBounds(
        typical_min=10, typical_max=2000,
        hard_min=1, hard_max=50000,
        unit='Nm', kind='float', zero_ok=False,
    ),
    'MaxRPM': FieldBounds(
        typical_min=2500, typical_max=15000,
        # PROPERTY_DESCRIPTIONS warns below 600 RPM may break the
        # engine; heavy diesels below 1500 freeze. We pick 600 as a
        # universal floor — anything below is dangerous regardless
        # of variant.
        hard_min=600, hard_max=30000,
        unit='rpm', kind='float', zero_ok=False,
    ),

    # Start and idle
    'StarterTorque': FieldBounds(
        typical_min=10_000, typical_max=600_000,
        hard_min=0, hard_max=10_000_000,
        kind='float',
    ),
    'StarterRPM': FieldBounds(
        typical_min=500, typical_max=3000,
        hard_min=100, hard_max=20000,
        unit='rpm', kind='float',
    ),
    'IdleThrottle': FieldBounds(
        # Spans wildly across variants (compact 0.002, diesel 0.017,
        # standard 0.05–0.3). We keep typical wide; the danger note
        # is values >1.0 on compact layouts, so hard cap at 1.0.
        typical_min=0.0001, typical_max=0.5,
        hard_min=0.0, hard_max=1.0,
        kind='float',
    ),
    'BlipThrottle': FieldBounds(
        typical_min=0.5, typical_max=10.0,
        hard_min=0.0, hard_max=50.0,
        kind='float',
    ),
    'BlipDurationSeconds': FieldBounds(
        typical_min=0.1, typical_max=3.0,
        hard_min=0.0, hard_max=10.0,
        unit='s', kind='float',
    ),

    # Friction & fuel
    'Inertia': FieldBounds(
        typical_min=80, typical_max=10_000,
        hard_min=1, hard_max=100_000,
        kind='float', zero_ok=False,
    ),
    'FrictionCoulombCoeff': FieldBounds(
        typical_min=50, typical_max=500_000,
        hard_min=0, hard_max=10_000_000,
        kind='float',
    ),
    'FrictionViscosityCoeff': FieldBounds(
        typical_min=10, typical_max=1500,
        hard_min=0, hard_max=20_000,
        kind='float',
    ),
    'FuelConsumption': FieldBounds(
        typical_min=3, typical_max=700,
        hard_min=0, hard_max=10_000,
        kind='float',
    ),

    # Thermal and effects
    'HeatingPower': FieldBounds(
        typical_min=0.0, typical_max=5.0,
        hard_min=0.0, hard_max=100.0,
        kind='float',
    ),
    'AfterFireProbability': FieldBounds(
        typical_min=0.0, typical_max=1.0,
        hard_min=0.0, hard_max=10.0,
        kind='float',
    ),

    # Diesel-only
    'IntakeSpeedEfficiency': FieldBounds(
        typical_min=0.5, typical_max=2.0,
        hard_min=0.0, hard_max=20.0,
        kind='float',
    ),
    'MaxJakeBrakeStep': FieldBounds(
        typical_min=0, typical_max=5,
        hard_min=0, hard_max=50,
        kind='int',
    ),

    # EV-only
    'MotorMaxPower': FieldBounds(
        typical_min=50, typical_max=1000,
        hard_min=1, hard_max=10000,
        unit='kW', kind='float', zero_ok=False,
    ),
    'MotorMaxVoltage': FieldBounds(
        typical_min=100, typical_max=1000,
        hard_min=12, hard_max=10000,
        unit='V', kind='float',
    ),
    'MotorMaxRPM': FieldBounds(
        typical_min=2500, typical_max=25000,
        hard_min=600, hard_max=50000,
        unit='rpm', kind='float',
    ),
    'MaxRegenTorqueRatio': FieldBounds(
        typical_min=0.0, typical_max=1.0,
        hard_min=0.0, hard_max=5.0,
        kind='float',
    ),
}


# Combined lookup. ``shop`` and ``creator_input`` keys are namespaced
# at the widget layer so they don't collide with property keys here.
def lookup(key: str, group: str) -> Optional[FieldBounds]:
    """Find bounds for ``key`` in the named ``group``.

    ``group`` is one of: 'shop', 'creator_input', 'property'.
    Returns None when the field isn't bounded (validation skipped).
    """
    if group == 'shop':
        return SHOP_BOUNDS.get(key)
    if group == 'creator_input':
        return CREATOR_INPUT_BOUNDS.get(key)
    if group == 'property':
        return PROPERTY_BOUNDS.get(key)
    return None


# ──────────────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────────────
def _strip_commas(text: str) -> str:
    """Tolerate '12,000' the same way the rest of the codebase does."""
    return text.replace(',', '').strip() if isinstance(text, str) else str(text)


def parse_value(text: str, kind: str) -> Optional[float]:
    """Parse a user-entered string into a number, or return None if
    parsing fails (caller decides whether that's an error)."""
    cleaned = _strip_commas(text)
    if cleaned == '':
        return None
    try:
        if kind == 'int':
            # Accept '1500.0' as 1500 too — strip a trailing '.0' and
            # coerce to int. Any other decimal is rejected.
            num = float(cleaned)
            if num != int(num):
                return None
            return float(int(num))
        return float(cleaned)
    except (TypeError, ValueError):
        return None


def validate(text: str, bounds: Optional[FieldBounds],
             allow_blank: bool = False) -> ValidationResult:
    """Evaluate ``text`` against ``bounds``.

    Args:
        text: Raw text from the QLineEdit / widget.
        bounds: The FieldBounds for this field, or None if no bounds
            apply (returns OK).
        allow_blank: When True, an empty input is OK. When False,
            empty -> error ("required").

    Returns a ValidationResult. The widget layer uses the status to
    pick a border color and the message for the inline error label.
    """
    if bounds is None:
        return _OK
    cleaned = _strip_commas(text)
    if cleaned == '':
        return _OK if allow_blank else _err('Required')
    val = parse_value(cleaned, bounds.kind)
    if val is None:
        if bounds.kind == 'int':
            return _err('Must be a whole number')
        return _err('Must be a number')
    if math.isnan(val) or math.isinf(val):
        return _err('Must be a finite number')
    if not bounds.zero_ok and val == 0:
        return _err('Must be greater than zero')
    if val < bounds.hard_min or val > bounds.hard_max:
        unit = f' {bounds.unit}' if bounds.unit else ''
        return _err(
            f'Out of safe range '
            f'({bounds._fmt(bounds.hard_min)}–{bounds._fmt(bounds.hard_max)}{unit})'
        )
    if val < bounds.typical_min or val > bounds.typical_max:
        unit = f' {bounds.unit}' if bounds.unit else ''
        return _warn(
            f'Unusual — typical {bounds._fmt(bounds.typical_min)}–'
            f'{bounds._fmt(bounds.typical_max)}{unit}'
        )
    return _OK
