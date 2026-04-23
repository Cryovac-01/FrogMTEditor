"""
Tire .uexp parser for Motor Town MTTirePhysicsDataAsset files.
Handles all tire size variants (44-72 bytes).

Binary format:
  [variable header] [float properties] [00000000 C1832A9E footer]
"""
import struct
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional


FOOTER = b'\x00\x00\x00\x00\xc1\x83\x2a\x9e'

# Property names by float count (reverse-engineered from game behavior)
# These are positional - the Nth float maps to the Nth property name
TIRE_PROPERTY_NAMES = {
    6: ('LateralStiffness', 'CorneringStiffness',
        'LongStiffness', 'LongSlipStiffness',
        'LoadRating', 'MaxLoad'),
    8: ('LateralStiffness', 'CorneringStiffness', 'LoadRating',
        'MaxLoad', 'LongStiffness', 'LongSlipStiffness',
        'RollingResistance', 'MaxSpeed'),
    9: ('LateralStiffness', 'CorneringStiffness',
        'LongStiffness', 'LongSlipStiffness',
        'LoadRating', 'MaxLoad', 'MaxSpeed',
        'RollingResistance', 'WearRate'),
    10: ('LateralStiffness', 'CorneringStiffness', 'GripMultiplier',
         'LongStiffness', 'LongSlipStiffness',
         'LoadRating', 'MaxLoad', 'MaxSpeed',
         'RollingResistance', 'WearRate'),
    11: ('LateralStiffness', 'CamberStiffness', 'CorneringStiffness',
         'LongStiffness', 'LongSlipStiffness',
         'LoadRating', 'MaxLoad', 'GripMultiplier',
         'MaxSpeed', 'RollingResistance', 'WearRate'),
    12: ('LateralStiffness', 'CamberStiffness', 'CorneringStiffness',
         'LongStiffness', 'LongSlipStiffness',
         'LoadRating', 'MaxLoad', 'GripMultiplier',
         'MaxSpeed', 'RollingResistance', 'WearRate', 'WearRate2'),
    14: ('LateralStiffness', 'CorneringStiffness', 'CamberStiffness',
         'LongStiffness', 'LongSlipStiffness',
         'LoadRating', 'MaxLoad', 'TreadDepth',
         'TireTemperature', 'ThermalSensitivity',
         'MaxSpeed', 'GripMultiplier',
         'RollingResistance', 'WearRate'),
}
TIRE_CANONICAL_PROPERTY_ORDER = (
    'LateralStiffness',
    'CorneringStiffness',
    'CamberStiffness',
    'LongStiffness',
    'LongSlipStiffness',
    'LoadRating',
    'MaxLoad',
    'TreadDepth',
    'TireTemperature',
    'ThermalSensitivity',
    'MaxSpeed',
    'GripMultiplier',
    'RollingResistance',
    'WearRate',
    'WearRate2',
)
TIRE_INTEGER_LIKE_PROPERTIES = frozenset({
    'LateralStiffness',
    'LongStiffness',
    'LongSlipStiffness',
    'LoadRating',
    'MaxLoad',
    'MaxSpeed',
})
TIRE_PROPERTY_UNITS = {
    'LoadRating': 'N',
    'MaxLoad': 'N',
    'GripMultiplier': '%',
}


def tire_property_unit(name: str) -> str:
    return TIRE_PROPERTY_UNITS.get(name, '')


def tire_property_type(name: str) -> str:
    return 'int' if name in TIRE_INTEGER_LIKE_PROPERTIES else 'float'


def grip_multiplier_to_offroad_percent(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return (float(value) - 1.0) * 100.0


def offroad_percent_to_grip_multiplier(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return 1.0 + (float(value) / 100.0)


def build_tire_display_entry(name: str, value: Optional[float]) -> Dict[str, Any]:
    if value is None:
        return {
            'raw': '',
            'display': '',
            'unit': tire_property_unit(name),
            'type': tire_property_type(name),
            'missing': True,
        }

    if 'Stiffness' in name or name in ('LateralStiffness', 'LongStiffness', 'LongSlipStiffness'):
        display = f"{value:.0f}"
    elif name in ('LoadRating', 'MaxLoad'):
        display = f"{value:.0f}"
    elif name == 'MaxSpeed':
        display = f"{value:.0f}"
    elif name == 'GripMultiplier':
        offroad_percent = grip_multiplier_to_offroad_percent(value) or 0.0
        display = f"{offroad_percent:.1f}".rstrip('0').rstrip('.')
    else:
        display = f"{value:.6g}"

    return {
        'raw': value,
        'display': display,
        'unit': tire_property_unit(name),
        'type': tire_property_type(name),
    }


def choose_tire_layout(required_properties: set[str], preferred_order: Optional[List[str]] = None) -> Optional[tuple[str, ...]]:
    """Return the smallest known layout that can represent the requested fields."""
    if not required_properties:
        return tuple(preferred_order or ())

    preferred = tuple(preferred_order or ())
    candidates = [
        layout
        for _count, layout in sorted(TIRE_PROPERTY_NAMES.items())
        if required_properties.issubset(set(layout))
    ]
    if not candidates:
        return None

    candidates.sort(key=lambda layout: (len(layout), 0 if tuple(layout) == preferred else 1))
    return tuple(candidates[0])


@dataclass
class TireData:
    """Parsed tire data with named properties."""
    header_bytes: bytes
    properties: Dict[str, float]
    property_order: List[str]  # Preserve order for serialization
    raw_bytes: bytes

    def to_display_dict(self) -> Dict[str, Any]:
        result = {}
        for name, value in self.properties.items():
            result[name] = build_tire_display_entry(name, value)
        return result


def _find_header_size(data: bytes) -> int:
    """Find where float property data starts by testing alignment."""
    file_size = len(data)
    footer_size = 8

    for hdr_sz in range(4, 16):
        remaining = file_size - footer_size - hdr_sz
        if remaining > 0 and remaining % 4 == 0:
            # Check if first value looks like a reasonable float
            first_f = struct.unpack_from('<f', data, hdr_sz)[0]
            if 0.01 < abs(first_f) < 1e7 and first_f == first_f:  # not NaN
                return hdr_sz
    # Fallback: try common sizes
    for hdr_sz in [10, 8, 6, 12]:
        remaining = file_size - footer_size - hdr_sz
        if remaining > 0 and remaining % 4 == 0:
            return hdr_sz
    raise ValueError(f"Cannot determine tire header size for {file_size}B file")


def parse_tire(data: bytes) -> TireData:
    """Parse a tire .uexp file into structured data."""
    header_size = _find_header_size(data)
    header_bytes = data[:header_size]

    num_floats = (len(data) - 8 - header_size) // 4
    prop_names = TIRE_PROPERTY_NAMES.get(num_floats)
    if not prop_names:
        prop_names = [f'Property_{i}' for i in range(num_floats)]

    properties = {}
    property_order = []
    offset = header_size
    for i in range(num_floats):
        name = prop_names[i] if i < len(prop_names) else f'Property_{i}'
        value = struct.unpack_from('<f', data, offset)[0]
        properties[name] = value
        property_order.append(name)
        offset += 4

    return TireData(
        header_bytes=header_bytes,
        properties=properties,
        property_order=property_order,
        raw_bytes=data,
    )


def serialize_tire(tire: TireData) -> bytes:
    """Serialize tire data back to binary .uexp format."""
    parts = [tire.header_bytes]
    for name in tire.property_order:
        value = tire.properties.get(name, 0.0)
        parts.append(struct.pack('<f', value))
    parts.append(FOOTER)
    return b''.join(parts)


def round_trip_test(data: bytes) -> bool:
    try:
        tire = parse_tire(data)
        rebuilt = serialize_tire(tire)
        return rebuilt == data
    except Exception:
        return False
