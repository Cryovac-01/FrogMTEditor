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
    # Peak Torque RPM and Peak HP RPM are bounded by MaxRPM, which
    # the editor caps at 14,000 hard / 10,000 typical. Their absolute
    # bounds match the same ceiling so a user can't request a peak
    # past the redline they're allowed to set. The cross-field
    # validator (validate_rpm_curve below) handles the *relative*
    # ratio check; these are the absolute floors and ceilings.
    'peak_torque_rpm': FieldBounds(
        # Heavy diesels can peak torque as low as ~1,100 rpm; that's
        # the floor we want to allow without warning. Hard floor 400
        # because anything quieter than that is implausible.
        typical_min=1000, typical_max=12500,
        hard_min=400, hard_max=14000,
        unit='rpm', kind='int',
    ),
    'max_hp': FieldBounds(
        typical_min=10, typical_max=2500,
        hard_min=1, hard_max=10000,
        unit='HP', kind='float',
    ),
    'peak_hp_rpm': FieldBounds(
        # Heavy diesels can peak HP near 2,200; sport bikes near
        # 12,000. Typical floor 1,800 covers HD diesels; ceiling
        # matches the MaxRPM hard cap so the user can't request a
        # peak past redline.
        typical_min=1800, typical_max=14000,
        hard_min=600, hard_max=14000,
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
        # Tightened bounds per Frog: hard floor 2000 rpm (most engines
        # break, freeze, or behave nonsensically below this); typical
        # floor 2800 (anything quieter than a heavy diesel at idle is
        # rare). Hard ceiling 14000 (above this the simulation gets
        # unstable in MT); typical ceiling 10000 (only F1-class race
        # engines and high-rev sport bikes legitimately exceed this).
        typical_min=2800, typical_max=10000,
        hard_min=2000, hard_max=14000,
        unit='rpm', kind='float', zero_ok=False,
    ),

    # Start and idle
    'StarterTorque': FieldBounds(
        # Widened typical_max to encompass vanilla heavy diesels
        # (3,000,000) so opening an HD donor doesn't warn on the
        # vanilla value the user hasn't even touched yet.
        typical_min=10_000, typical_max=3_500_000,
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
        # Heavy diesels reach 50,000 in vanilla — typical_max widened
        # so an HD donor doesn't false-warn on its stock value.
        typical_min=80, typical_max=60_000,
        hard_min=1, hard_max=100_000,
        kind='float', zero_ok=False,
    ),
    'FrictionCoulombCoeff': FieldBounds(
        # Heavy diesels reach 2,500,000 in vanilla.
        typical_min=50, typical_max=3_000_000,
        hard_min=0, hard_max=10_000_000,
        kind='float',
    ),
    'FrictionViscosityCoeff': FieldBounds(
        # Heavy diesels reach 6,000 in vanilla.
        typical_min=10, typical_max=6_500,
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


# ──────────────────────────────────────────────────────────────────────
# Cross-field RPM curve validation
# ──────────────────────────────────────────────────────────────────────
# Bounds derived from typical real-world engine torque/HP curves:
#
#   ICE engines (NA petrol, turbo petrol, NA diesel, HD turbo diesel,
#   sport bikes) span this range for peak-torque-RPM as a fraction of
#   redline:
#       Turbo HD diesel  : 25–40%
#       Turbo petrol     : 30–50%
#       NA diesel        : 40–60%
#       NA petrol        : 50–75%
#       Sport bike       : 60–80%
#
#   For peak-HP-RPM:
#       Turbo HD diesel  : 60–80%
#       Turbo petrol     : 75–90%
#       NA diesel        : 75–90%
#       NA petrol        : 80–95%
#       Sport bike       : 80–95%
#
#   Universal sanity rule: peak HP almost always occurs after peak
#   torque on ICE. The exception (peak HP RPM == peak torque RPM) is
#   rare but physically possible — we allow equality, only flag when
#   peak HP comes earlier than peak torque.
#
#   Electric motors are a different beast: peak torque is at 0 RPM
#   (constant-torque region) and peak HP comes mid-range during the
#   constant-power region. None of the ICE rules apply, so callers
#   should pass is_ev=True to skip these checks entirely.

# Soft (warning) range for peak-torque-RPM as a fraction of MaxRPM.
_PEAK_TORQUE_TYPICAL_PCT = (25, 90)
# Hard (error) floor — peak torque below 10% of redline is nonsensical
# for ICE; the engine couldn't even idle let alone make power there.
# Upper hard limit is the redline itself (100% — peak torque AT redline
# is unusual but possible).
_PEAK_TORQUE_HARD_PCT = (10, 100)

# Soft range for peak-HP-RPM as a fraction of MaxRPM.
_PEAK_HP_TYPICAL_PCT = (60, 100)
# Hard floor — peak HP at <30% of redline means almost no power band.
_PEAK_HP_HARD_PCT = (30, 100)


def _pct(numer: float, denom: float) -> Optional[float]:
    """Return numer/denom * 100, or None when denom is 0/negative."""
    if denom is None or denom <= 0:
        return None
    return (numer / denom) * 100.0


def validate_rpm_curve(peak_torque_rpm: Optional[float],
                       peak_hp_rpm: Optional[float],
                       max_rpm: Optional[float],
                       is_ev: bool = False) -> Tuple[ValidationResult, ValidationResult]:
    """Cross-field validation of the peak-torque-RPM and peak-HP-RPM
    inputs against MaxRPM. EV mode bypasses both checks (ICE curve
    conventions don't apply to constant-torque/constant-power motors).

    Returns ``(peak_torque_result, peak_hp_result)``. Either may be
    OK / warn / error. The most-severe issue per field wins.
    """
    if is_ev:
        return _OK, _OK
    if max_rpm is None or max_rpm <= 0:
        # MaxRPM hasn't been set yet (or is invalid); the per-field
        # validator already flags this. Skip the cross check rather
        # than emit a misleading "% of nothing" message.
        return _OK, _OK

    # ── Peak torque RPM as % of redline ──
    pt_result: ValidationResult = _OK
    if peak_torque_rpm is not None and peak_torque_rpm > 0:
        pct = _pct(peak_torque_rpm, max_rpm)
        if pct is not None:
            if pct < _PEAK_TORQUE_HARD_PCT[0] or pct > _PEAK_TORQUE_HARD_PCT[1]:
                pt_result = _err(
                    f'Peak torque at {pct:.0f}% of redline is outside '
                    f'the safe ICE range '
                    f'({_PEAK_TORQUE_HARD_PCT[0]}–{_PEAK_TORQUE_HARD_PCT[1]}%)'
                )
            elif pct < _PEAK_TORQUE_TYPICAL_PCT[0] or pct > _PEAK_TORQUE_TYPICAL_PCT[1]:
                pt_result = _warn(
                    f'Peak torque at {pct:.0f}% of redline is unusual — '
                    f'typical ICE engines peak between '
                    f'{_PEAK_TORQUE_TYPICAL_PCT[0]}–{_PEAK_TORQUE_TYPICAL_PCT[1]}%'
                )

    # ── Peak HP RPM as % of redline ──
    ph_result: ValidationResult = _OK
    if peak_hp_rpm is not None and peak_hp_rpm > 0:
        pct = _pct(peak_hp_rpm, max_rpm)
        if pct is not None:
            if pct < _PEAK_HP_HARD_PCT[0] or pct > _PEAK_HP_HARD_PCT[1]:
                ph_result = _err(
                    f'Peak HP at {pct:.0f}% of redline is outside '
                    f'the safe ICE range '
                    f'({_PEAK_HP_HARD_PCT[0]}–{_PEAK_HP_HARD_PCT[1]}%)'
                )
            elif pct < _PEAK_HP_TYPICAL_PCT[0] or pct > _PEAK_HP_TYPICAL_PCT[1]:
                ph_result = _warn(
                    f'Peak HP at {pct:.0f}% of redline is unusual — '
                    f'typical ICE engines peak between '
                    f'{_PEAK_HP_TYPICAL_PCT[0]}–{_PEAK_HP_TYPICAL_PCT[1]}%'
                )

    # ── Ordering rule: peak HP shouldn't be earlier than peak torque ──
    # Almost universal on ICE — the engine builds torque early then
    # HP rises with RPM as torque tapers. Flag the inversion as a
    # warning (not error — some pure-race engines technically can
    # have inverted curves due to cam tuning).
    if (peak_torque_rpm is not None and peak_hp_rpm is not None
            and peak_torque_rpm > 0 and peak_hp_rpm > 0
            and peak_hp_rpm < peak_torque_rpm):
        msg = (
            f'Peak HP ({int(peak_hp_rpm):,} rpm) occurs BEFORE peak '
            f'torque ({int(peak_torque_rpm):,} rpm) — inverted curve, '
            f'almost no real ICE behaves this way'
        )
        # Apply to whichever field is currently OK so we don't drop
        # an existing % error. If both fields are already errored,
        # leave them; the user has bigger issues to fix first.
        if not ph_result.is_error:
            ph_result = _warn(msg) if ph_result.status == 'ok' else ph_result
        if not pt_result.is_error and ph_result.status != 'warn':
            pt_result = _warn(msg) if pt_result.status == 'ok' else pt_result

    return pt_result, ph_result


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
