"""Tire-creator analysis utilities — pure Python, no Qt.

Splits the modeling decisions out of the UI layer so the formulas
are testable in isolation. Everything here is "best-effort estimate
based on documented field semantics" — Motor Town's actual physics
are baked into native C++ that we can't read. The numbers are
plausible directional movement, not exact in-game values.

Modules that build on this:
  - native_qt/creator.py            : text output in the details panel
  - native_qt/tire_charts.py        : Qt chart widgets

Layer of trust per function:
  estimate_grip            grounded — uses the existing editor formula
  classify_archetype       heuristic — scores tunable archetypes
  thermal_curve            approximated — Gaussian around TireTemperature
  load_curve               approximated — flat -> linear decline -> falloff
  slip_curve               math-grounded — simplified Pacejka magic formula
  wear_curve               math-grounded but unit-uncertain — linear
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from native_services import parse_optional_number


# ──────────────────────────────────────────────────────────────────────
# Field-reading helper. Tire properties live nested in part['properties']
# as dicts with 'raw' and 'display'. Values may also have been overridden
# in the editor (passed as a flat str -> str dict). We honour overrides.
# ──────────────────────────────────────────────────────────────────────
def _read(part: Dict[str, Any],
          overrides: Optional[Dict[str, Any]],
          key: str,
          default: Optional[float] = None) -> Optional[float]:
    if overrides and key in overrides:
        v = parse_optional_number(overrides.get(key))
        if v is not None:
            return v
    prop = (part.get('properties') or {}).get(key)
    if not isinstance(prop, dict):
        return default
    raw = prop.get('raw')
    if isinstance(raw, (int, float)):
        return float(raw)
    parsed = parse_optional_number(prop.get('display'))
    return parsed if parsed is not None else default


# ──────────────────────────────────────────────────────────────────────
# Grip estimates
# ──────────────────────────────────────────────────────────────────────
def estimate_grip(part: Dict[str, Any],
                  overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Return both the street and offroad grip estimates plus the
    formula explanation so the caller can show its work to the user.

    Street formula (matches the existing editor estimate):
        street = CorneringStiffness + CamberStiffness/2

    Offroad formula:
        offroad = street * (1 + GripMultiplier/100)

    GripMultiplier is the documented offroad-percentage field (-50..+100
    per the description), so the offroad calculation is grounded; the
    street estimate is grounded against `estimate_tire_grip_g` which has
    been the editor's primary indicator since launch.

    Returns:
        {
          'street_g': float | None,
          'offroad_g': float | None,
          'cornering': float | None,   # raw CorneringStiffness used
          'camber':    float | None,   # raw CamberStiffness used
          'offroad_pct': float,        # GripMultiplier (defaults to 0)
          'formula': str,              # human-readable explanation
        }
    """
    cornering = _read(part, overrides, 'CorneringStiffness')
    camber    = _read(part, overrides, 'CamberStiffness')
    grip_mult = _read(part, overrides, 'GripMultiplier', default=0.0)
    if cornering is None and camber is None:
        return {'street_g': None, 'offroad_g': None,
                'cornering': cornering, 'camber': camber,
                'offroad_pct': float(grip_mult or 0.0), 'formula': ''}

    street = (cornering or 0.0) + ((camber or 0.0) / 2.0)
    offroad_factor = 1.0 + (float(grip_mult or 0.0) / 100.0)
    offroad = max(0.0, street * offroad_factor)
    return {
        'street_g':  round(street, 2),
        'offroad_g': round(offroad, 2),
        'cornering': cornering,
        'camber':    camber,
        'offroad_pct': float(grip_mult or 0.0),
        'formula': (
            f'Street  = Cornering ({cornering or 0:.2f}) + '
            f'Camber/2 ({(camber or 0)/2:.2f})  =  {street:.2f} G\n'
            f'Offroad = Street × (1 + GripMultiplier/100)  '
            f'=  {street:.2f} × {offroad_factor:.2f}  =  {offroad:.2f} G'
        ),
    }


# ──────────────────────────────────────────────────────────────────────
# Use-case archetype classifier
# ──────────────────────────────────────────────────────────────────────
# Each archetype scores against a set of weighted indicators. The
# classifier picks the highest scorer; ties or near-ties surface a
# "secondary" archetype too. Scores are 0–100. Confidence is the
# margin between the winner and runner-up, normalised.
#
# These weights are heuristic, derived from how vanilla MT tires are
# tuned: race tires have high CorneringStiffness + low GripMultiplier,
# heavy-duty tires have high LoadRating, drift tires have lower
# CorneringStiffness + high LongSlipStiffness, etc. They're not from
# any documented MT spec — just a sensible reading of the field
# semantics + observed vanilla patterns.

_ARCHETYPES = ('race', 'comfort', 'drift', 'haul', 'offroad')

_ARCHETYPE_LABELS = {
    'race':    'Racing / Performance',
    'comfort': 'Comfort / Daily',
    'drift':   'Drifting',
    'haul':    'Hauling / Heavy-Duty',
    'offroad': 'Off-road',
}


def _score_race(t: Dict[str, Any]) -> Tuple[float, List[str]]:
    score, reasons = 0.0, []
    cornering = t.get('cornering') or 0
    if cornering >= 1.05:
        score += 30; reasons.append('high CorneringStiffness (mid-corner bite)')
    elif cornering >= 0.95:
        score += 15
    if (t.get('lateral') or 0) > 800_000:
        score += 20; reasons.append('stiff sidewall (sharp response)')
    if (t.get('longitudinal') or 0) > 700_000:
        score += 15; reasons.append('stiff tread under traction')
    if (t.get('camber') or 0) >= 0.4:
        score += 15; reasons.append('camber-aware (race alignment)')
    if (t.get('grip_mult') or 0) <= 0:
        score += 10; reasons.append('off-road grip de-emphasized')
    if (t.get('tread_depth') is not None and t['tread_depth'] < 0.005):
        score += 10; reasons.append('shallow tread (race slick territory)')
    return score, reasons


def _score_comfort(t: Dict[str, Any]) -> Tuple[float, List[str]]:
    score, reasons = 0.0, []
    if (t.get('thermal') is not None and t['thermal'] < 0.5):
        score += 25; reasons.append('low thermal sensitivity (consistent grip)')
    cornering = t.get('cornering') or 0
    if 0.85 <= cornering <= 1.05:
        score += 20; reasons.append('moderate cornering (predictable handling)')
    lateral = t.get('lateral') or 0
    if 600_000 <= lateral <= 800_000:
        score += 20; reasons.append('moderate sidewall (compliant ride)')
    wear = t.get('wear') or 0
    if 0 < wear < 0.01:
        score += 15; reasons.append('low wear rate (long tire life)')
    if (t.get('rolling') or 0) > 0.012:
        score += 10
    return score, reasons


def _score_drift(t: Dict[str, Any]) -> Tuple[float, List[str]]:
    score, reasons = 0.0, []
    cornering = t.get('cornering') or 0
    if cornering and cornering < 0.85:
        score += 30; reasons.append('low cornering (slide-friendly)')
    long_slip = t.get('long_slip') or 0
    if long_slip > 250_000:
        score += 25; reasons.append('high LongSlipStiffness (predictable slides)')
    lateral = t.get('lateral') or 0
    if lateral and lateral < 700_000:
        score += 15; reasons.append('softer sidewall (forgiving breakaway)')
    wear = t.get('wear') or 0
    if wear > 0.5:
        score += 20; reasons.append('high wear (consumable drift tire)')
    return score, reasons


def _score_haul(t: Dict[str, Any]) -> Tuple[float, List[str]]:
    score, reasons = 0.0, []
    load_rating = t.get('load_rating') or 0
    if load_rating >= 600:
        score += 30; reasons.append('heavy-duty load rating')
    if (t.get('max_load') or 0) > 200:
        score += 20; reasons.append('high max load capacity')
    cornering = t.get('cornering') or 0
    if cornering and cornering < 0.95:
        score += 15; reasons.append('lower cornering (load over agility)')
    if (t.get('lateral') or 0) > 700_000:
        score += 15; reasons.append('reinforced sidewall')
    if (t.get('tread_depth') or 0) > 0.005:
        score += 10
    return score, reasons


def _score_offroad(t: Dict[str, Any]) -> Tuple[float, List[str]]:
    score, reasons = 0.0, []
    grip_mult = t.get('grip_mult') or 0
    if grip_mult >= 30:
        score += 40; reasons.append('large positive offroad bonus')
    elif grip_mult > 0:
        score += 20; reasons.append('positive offroad bonus')
    if (t.get('tread_depth') or 0) > 0.008:
        score += 15; reasons.append('deep tread (loose-surface bite)')
    cornering = t.get('cornering') or 0
    if cornering and cornering < 0.95:
        score += 15; reasons.append('softer cornering (compliant on bumps)')
    if (t.get('lateral') or 0) > 600_000:
        score += 10
    return score, reasons


_SCORERS = {
    'race':    _score_race,
    'comfort': _score_comfort,
    'drift':   _score_drift,
    'haul':    _score_haul,
    'offroad': _score_offroad,
}


def classify_archetype(part: Dict[str, Any],
                       overrides: Optional[Dict[str, Any]] = None
                       ) -> Dict[str, Any]:
    """Score every archetype + return the best fit + a confidence.

    Returns:
        {
          'primary': 'race' | 'comfort' | ...,
          'primary_label': 'Racing / Performance',
          'secondary': str | None,
          'confidence': float in [0, 1],
          'scores': {key: (score, [reasons])},
        }
    """
    t = {
        'cornering':   _read(part, overrides, 'CorneringStiffness'),
        'camber':      _read(part, overrides, 'CamberStiffness'),
        'lateral':     _read(part, overrides, 'LateralStiffness'),
        'longitudinal':_read(part, overrides, 'LongStiffness'),
        'long_slip':   _read(part, overrides, 'LongSlipStiffness'),
        'load_rating': _read(part, overrides, 'LoadRating'),
        'max_load':    _read(part, overrides, 'MaxLoad'),
        'grip_mult':   _read(part, overrides, 'GripMultiplier', default=0.0),
        'tread_depth': _read(part, overrides, 'TreadDepth'),
        'thermal':     _read(part, overrides, 'ThermalSensitivity'),
        'wear':        _read(part, overrides, 'WearRate'),
        'rolling':     _read(part, overrides, 'RollingResistance'),
    }

    scores = {key: scorer(t) for key, scorer in _SCORERS.items()}
    sorted_keys = sorted(scores.keys(), key=lambda k: scores[k][0], reverse=True)
    primary = sorted_keys[0]
    primary_score, primary_reasons = scores[primary]
    runner = sorted_keys[1]
    runner_score, _ = scores[runner]

    # Confidence: how much the winner outscored the runner-up,
    # normalised to a 0-1 range. A 30-point margin out of a 100-point
    # max is treated as full confidence.
    margin = max(0.0, primary_score - runner_score)
    confidence = max(0.0, min(1.0, margin / 30.0))
    if primary_score < 20:
        # No archetype scored convincingly — low confidence regardless
        confidence = min(confidence, 0.2)

    secondary = runner if (primary_score - runner_score) < 12 and runner_score >= 20 else None

    return {
        'primary': primary,
        'primary_label': _ARCHETYPE_LABELS[primary],
        'primary_reasons': primary_reasons,
        'secondary': secondary,
        'secondary_label': _ARCHETYPE_LABELS[secondary] if secondary else None,
        'confidence': round(confidence, 2),
        'scores': {k: round(v[0], 1) for k, v in scores.items()},
    }


# ──────────────────────────────────────────────────────────────────────
# Curves — each returns a list of (x, y, ...) tuples ready to plot.
# ──────────────────────────────────────────────────────────────────────
def thermal_curve(part: Dict[str, Any],
                  overrides: Optional[Dict[str, Any]] = None,
                  num_samples: int = 80) -> List[Tuple[float, float, float]]:
    """Approximate grip vs temperature curve. APPROXIMATED — MT's
    thermal grip formula isn't documented. We use a Gaussian centred
    on the tire's configured TireTemperature with a width inversely
    proportional to ThermalSensitivity:

        grip(T) = peak_grip * exp( -((T - peak_temp) / width)^2 )
        width  = 70 / (1 + ThermalSensitivity)

    Higher ThermalSensitivity narrows the window (race-tire behaviour);
    low sensitivity flattens it out (street-tire behaviour). Two
    series: street (base grip) and offroad (street * GripMultiplier).
    """
    grip = estimate_grip(part, overrides)
    if grip['street_g'] is None or grip['street_g'] <= 0:
        return []
    peak_temp = _read(part, overrides, 'TireTemperature', default=80.0) or 80.0
    sensitivity = _read(part, overrides, 'ThermalSensitivity', default=1.0) or 1.0
    sensitivity = max(0.0, sensitivity)
    width = 70.0 / (1.0 + sensitivity)
    out = []
    for i in range(num_samples + 1):
        t = 20.0 + (140.0 - 20.0) * (i / num_samples)
        falloff = math.exp(-((t - peak_temp) / width) ** 2) if width > 0 else 0.0
        street = grip['street_g'] * falloff
        offroad = grip['offroad_g'] * falloff if grip['offroad_g'] else street
        out.append((t, round(street, 3), round(offroad, 3)))
    return out


def load_curve(part: Dict[str, Any],
               overrides: Optional[Dict[str, Any]] = None,
               num_samples: int = 12) -> List[Tuple[float, float]]:
    """Approximate grip-factor vs load curve. APPROXIMATED — MT's
    load sensitivity isn't documented and the LoadRating/MaxLoad
    fields don't carry meaningful real-world units (see note in
    PROPERTY_DESCRIPTIONS).

    Vanilla data inverts the conventional rated-load < max-load
    relationship — sometimes LoadRating > MaxLoad (HeavyDutyRearTire
    has 800 / 400; DriftTire has 200 / 100). We treat the smaller
    of the two as a "comfortable" threshold and the larger as the
    "operating limit", regardless of which field happens to hold
    which value:

        load <= low                : factor = 1.0 (flat)
        low < load <= high         : linear decline 1.0 -> 0.7
        load > high                : steep decline past 0.7

    Sample points span 0 to 2x the high anchor at num_samples + 1
    increments per Frog's request.
    """
    load_rating = _read(part, overrides, 'LoadRating')
    max_load = _read(part, overrides, 'MaxLoad')
    candidates = [v for v in (load_rating, max_load) if v and v > 0]
    if not candidates:
        return []
    if len(candidates) == 1:
        # Only one value present — treat the lone field as the high
        # anchor and put the soft threshold at half of it.
        high = candidates[0]
        low = high * 0.5
    else:
        low = min(candidates)
        high = max(candidates)
        if high == low:
            # Both equal: synthesise a small soft-zone above so the
            # curve actually moves on the chart.
            high = low * 1.5

    out = []
    end_load = max(2.0 * high, low + 1e-3)
    for i in range(num_samples + 1):
        load = end_load * (i / num_samples)
        if load <= low:
            factor = 1.0
        elif load <= high:
            span = max(1e-6, high - low)
            factor = 1.0 - 0.30 * (load - low) / span
        else:
            extra = load - high
            factor = max(0.0, 0.70 - 0.50 * extra / high)
        out.append((round(load, 2), round(factor, 3)))
    return out


def slip_curve(part: Dict[str, Any],
               overrides: Optional[Dict[str, Any]] = None,
               num_samples: int = 80,
               max_slip_deg: float = 15.0) -> List[Tuple[float, float]]:
    """Lateral force vs slip-angle curve. MATH-GROUNDED — uses a
    rational Pacejka-style shape that captures the rise-peak-fall
    behaviour of real tires:

        F_y(α) = D * (α/α_peak) / (1 + (α/α_peak)²)

    where α is in radians, α_peak ≈ 0.10 rad (5.7°) for typical tires
    (shifts with CorneringStiffness — higher cornering -> earlier
    peak), and D is scaled from LateralStiffness so the y axis ends
    up in a readable range. Peak occurs at α = α_peak; force then
    declines past the peak (the post-peak region is where a real
    car loses grip if the driver oversteers).

    The shape is well-defined tire engineering math; the absolute
    magnitude won't match MT's internal values exactly because the
    units differ, but the relative shape across edits is right.
    Output: (slip_degrees, lateral_force_kN_relative).
    """
    lateral = _read(part, overrides, 'LateralStiffness')
    cornering = _read(part, overrides, 'CorneringStiffness') or 1.0
    if not lateral or lateral <= 0:
        return []
    # Higher cornering = earlier (sharper) peak. 0.06–0.14 rad covers
    # race tires through soft street tires.
    alpha_peak = max(0.06, min(0.14, 0.12 / max(0.5, cornering)))
    # Scale so the peak force is roughly 0.5 * LateralStiffness * alpha_peak,
    # then divide by a constant to keep "kN-ish" magnitudes readable.
    D = lateral * alpha_peak
    out = []
    for i in range(num_samples + 1):
        deg = max_slip_deg * (i / num_samples)
        alpha = math.radians(deg)
        ratio = alpha / alpha_peak
        force = D * ratio / (1.0 + ratio * ratio)
        out.append((round(deg, 2), round(force / 1000.0, 2)))
    return out


def wear_curve(part: Dict[str, Any],
               overrides: Optional[Dict[str, Any]] = None,
               num_samples: int = 80,
               max_distance_km: float = 5000.0) -> List[Tuple[float, float]]:
    """Tread remaining (%) vs distance driven. WearRate's units aren't
    documented and vanilla values span 4 orders of magnitude (0.005 to
    700.0), so this curve is plotted RELATIVE: a baseline tire with
    WearRate=0.01 wears down 100% over max_distance_km. Tires with
    WearRate=0.005 last twice as long; WearRate=0.02 lasts half.

        tread_pct(km) = max(0, 100 - 100 * (WearRate / 0.01) * (km / max_distance_km))

    Honest disclaimer: this is a relative comparison, not an absolute
    mileage prediction.
    """
    wear = _read(part, overrides, 'WearRate')
    if wear is None or wear <= 0:
        return []
    BASELINE = 0.01  # WearRate that maps to "wears 100% over max_distance"
    rate_factor = wear / BASELINE
    out = []
    for i in range(num_samples + 1):
        km = max_distance_km * (i / num_samples)
        pct = max(0.0, 100.0 - 100.0 * rate_factor * (km / max_distance_km))
        out.append((round(km, 1), round(pct, 2)))
    return out


def stiffness_radar(part: Dict[str, Any],
                    overrides: Optional[Dict[str, Any]] = None
                    ) -> List[Tuple[str, float, float]]:
    """Five stiffness fields normalised to a 0–1 scale for a radar /
    bar chart. Reference-max picked from observed vanilla ranges so
    'race-tire stiff' fields land near the outer ring.

    Returns a list of (field_label, raw_value, normalised_0_to_1).
    """
    fields = (
        ('Lateral',     'LateralStiffness',    1_500_000.0),
        ('Long',        'LongStiffness',       1_200_000.0),
        ('Cornering',   'CorneringStiffness',  1.5),
        ('Camber',      'CamberStiffness',     1.0),
        ('Long Slip',   'LongSlipStiffness',   400_000.0),
    )
    out = []
    for label, key, ref_max in fields:
        raw = _read(part, overrides, key)
        if raw is None:
            out.append((label, 0.0, 0.0))
            continue
        out.append((label, raw, max(0.0, min(1.0, raw / ref_max))))
    return out
