"""
Engine .uexp parser for Motor Town MHEngineDataAsset files.
Handles all 5 engine variants: ICE Standard, ICE Compact, Bike, Diesel HD, EV.

Binary format:
  [header bytes] [FEFFFFFF = TorqueCurve import -2] [property values] [import refs] [00000000] [C1832A9E]

The header bytes encode which properties are present. Different engine types
have different property subsets and different headers.
"""
import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum


class EngineVariant(Enum):
    ICE_STANDARD = "ice_standard"      # 86 bytes, 13 props (lexusV10)
    ICE_COMPACT = "ice_compact"        # 80 bytes, 12 props (2JZ320HP) - no HeatingPower
    BIKE = "bike"                      # 86 bytes, 14 props (999r_150HP) - has StarterRPM
    DIESEL_HD = "diesel_hd"            # 91 bytes, 16 props (59cummins)
    EV = "ev"                          # 63 bytes, ~11 props (EVAlpineA290)


class FuelType(Enum):
    GAS = 1
    DIESEL = 2
    ELECTRIC = 3

    @classmethod
    def from_byte(cls, b):
        # Game stores: 1=Gas, 2=Diesel, 3=Electric; 0 treated as Gas
        mapping = {0: cls.GAS, 1: cls.GAS, 2: cls.DIESEL, 3: cls.ELECTRIC}
        return mapping.get(b, cls.GAS)


# Header signatures for variant detection
VARIANT_HEADERS = {
    # (size, first 10 header bytes hex) -> variant
    (86, '00090006010a0102010201020105'): EngineVariant.ICE_STANDARD,
    (88, '000401050006010a0102010201020105'): EngineVariant.ICE_STANDARD,
    (82, '000401050006010a010203020105'): EngineVariant.ICE_STANDARD,
    (78, '000401050006010a010203020203'): EngineVariant.ICE_COMPACT,
    (80, '00020107000601080202010201020203'): EngineVariant.ICE_COMPACT,
    (72, '000401050006010a01020303'): EngineVariant.ICE_COMPACT,
    (76, '00040105000601040102020202040203'): EngineVariant.ICE_COMPACT,
    (80, '00090006010a010203020105'): EngineVariant.ICE_COMPACT,
    (86, '00090012010201060203'): EngineVariant.BIKE,
    (88, '000401050012010201060203'): EngineVariant.BIKE,
    (82, '0004010500060108020201060203'): EngineVariant.BIKE,
    (91, '00040205001802060103'): EngineVariant.DIESEL_HD,
    (91, '00040105001802060103'): EngineVariant.DIESEL_HD,
    (63, '00058016830205070c09'): EngineVariant.EV,
}


# Property definitions per variant: (name, type, size_bytes)
# 'f' = float (4 bytes), 'i' = int32 (4 bytes), 'e1' = enum 1 byte, 'e4' = enum 4 bytes, 'imp' = import ref (4 bytes)
VARIANT_SCHEMAS = {
    EngineVariant.ICE_STANDARD: [
        # 13 properties, header 14 bytes, TorqueCurve at offset 14
        ('TorqueCurve', 'imp', 4),
        ('Inertia', 'f', 4),
        ('StarterTorque', 'f', 4),
        ('MaxTorque', 'f', 4),
        ('MaxRPM', 'f', 4),
        ('FrictionCoulombCoeff', 'f', 4),
        ('FrictionViscosityCoeff', 'f', 4),
        ('IdleThrottle', 'f', 4),
        ('FuelConsumption', 'f', 4),
        ('HeatingPower', 'f', 4),
        ('BlipThrottle', 'f', 4),
        ('BlipDurationSeconds', 'f', 4),
        ('AfterFireProbability', 'f', 4),
    ],
    EngineVariant.ICE_COMPACT: [
        # Vanilla compact engines omit AfterFireProbability and keep 3 tail imports.
        ('TorqueCurve', 'imp', 4),
        ('Inertia', 'f', 4),
        ('StarterTorque', 'f', 4),
        ('MaxTorque', 'f', 4),
        ('MaxRPM', 'f', 4),
        ('FrictionCoulombCoeff', 'f', 4),
        ('FrictionViscosityCoeff', 'f', 4),
        ('IdleThrottle', 'f', 4),
        ('FuelConsumption', 'f', 4),
        ('BlipThrottle', 'f', 4),
        ('BlipDurationSeconds', 'f', 4),
    ],
    EngineVariant.BIKE: [
        # 14 properties, header 10 bytes, has StarterRPM like Diesel
        ('TorqueCurve', 'imp', 4),
        ('Inertia', 'f', 4),
        ('StarterTorque', 'f', 4),
        ('StarterRPM', 'f', 4),
        ('MaxTorque', 'f', 4),
        ('MaxRPM', 'f', 4),
        ('FrictionCoulombCoeff', 'f', 4),
        ('FrictionViscosityCoeff', 'f', 4),
        ('IdleThrottle', 'f', 4),
        ('FuelConsumption', 'f', 4),
        ('HeatingPower', 'f', 4),
        ('BlipThrottle', 'f', 4),
        ('BlipDurationSeconds', 'f', 4),
        ('AfterFireProbability', 'f', 4),
    ],
    EngineVariant.DIESEL_HD: [
        # 16 properties, header 10 bytes
        ('TorqueCurve', 'imp', 4),
        ('Inertia', 'f', 4),
        ('StarterTorque', 'f', 4),
        ('StarterRPM', 'f', 4),
        ('MaxTorque', 'f', 4),
        ('MaxRPM', 'f', 4),
        ('FrictionCoulombCoeff', 'f', 4),
        ('FrictionViscosityCoeff', 'f', 4),
        ('IdleThrottle', 'f', 4),
        ('FuelType', 'e1', 1),
        ('FuelConsumption', 'f', 4),
        ('EngineType', 'e4', 4),
        ('BlipThrottle', 'f', 4),
        ('IntakeSpeedEfficiency', 'f', 4),
        ('BlipDurationSeconds', 'f', 4),
        ('MaxJakeBrakeStep', 'i', 4),
    ],
    EngineVariant.EV: [
        # ~11 non-zero properties, header 10 bytes
        ('TorqueCurve', 'imp', 4),
        ('Inertia', 'f', 4),
        ('MaxTorque', 'f', 4),          # StarterTorque=0, StarterRPM=0 skipped
        ('MaxRPM', 'f', 4),
        ('FrictionCoulombCoeff', 'f', 4),
        ('FrictionViscosityCoeff', 'f', 4),
        ('FuelType', 'e1', 1),          # = Electric
        ('FuelConsumption', 'f', 4),
        ('MaxRegenTorqueRatio', 'f', 4),
        ('MotorMaxPower', 'f', 4),
        ('MotorMaxVoltage', 'f', 4),
    ],
}

ICE_COMPACT_LEGACY_SCHEMA = [
# Legacy compact engines stored an extra AfterFireProbability
    # float and only 2 tail imports. We still parse it so old templates load.
    ('TorqueCurve', 'imp', 4),
    ('Inertia', 'f', 4),
    ('StarterTorque', 'f', 4),
    ('MaxTorque', 'f', 4),
    ('MaxRPM', 'f', 4),
    ('FrictionCoulombCoeff', 'f', 4),
    ('FrictionViscosityCoeff', 'f', 4),
    ('IdleThrottle', 'f', 4),
    ('FuelConsumption', 'f', 4),
    ('BlipThrottle', 'f', 4),
    ('BlipDurationSeconds', 'f', 4),
    ('AfterFireProbability', 'f', 4),
]

ICE_STANDARD_LEGACY_V8_SCHEMA = [
    # Legacy vanilla V8 engines keep AfterFireProbability, omit HeatingPower,
    # and still carry 3 tail imports.
    ('TorqueCurve', 'imp', 4),
    ('Inertia', 'f', 4),
    ('StarterTorque', 'f', 4),
    ('MaxTorque', 'f', 4),
    ('MaxRPM', 'f', 4),
    ('FrictionCoulombCoeff', 'f', 4),
    ('FrictionViscosityCoeff', 'f', 4),
    ('IdleThrottle', 'f', 4),
    ('FuelConsumption', 'f', 4),
    ('BlipThrottle', 'f', 4),
    ('BlipDurationSeconds', 'f', 4),
    ('AfterFireProbability', 'f', 4),
]

BIKE_LEGACY_SCHEMA = [
    # Legacy vanilla small/twin bikes omit StarterRPM and IdleThrottle while
    # retaining HeatingPower and 3 tail imports.
    ('TorqueCurve', 'imp', 4),
    ('Inertia', 'f', 4),
    ('StarterTorque', 'f', 4),
    ('MaxTorque', 'f', 4),
    ('MaxRPM', 'f', 4),
    ('FrictionCoulombCoeff', 'f', 4),
    ('FrictionViscosityCoeff', 'f', 4),
    ('FuelConsumption', 'f', 4),
    ('HeatingPower', 'f', 4),
    ('BlipThrottle', 'f', 4),
    ('BlipDurationSeconds', 'f', 4),
    ('AfterFireProbability', 'f', 4),
]


def _schema_property_names(schema) -> tuple[str, ...]:
    return tuple(name for name, _prop_type, _prop_size in schema)


def _ordered_unique_property_names(*name_lists: tuple[str, ...]) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for names in name_lists:
        for name in names:
            if name in seen:
                continue
            seen.add(name)
            ordered.append(name)
    return tuple(ordered)


ENGINE_CANONICAL_PROPERTY_ORDER = _ordered_unique_property_names(
    _schema_property_names(VARIANT_SCHEMAS[EngineVariant.ICE_STANDARD]),
    _schema_property_names(VARIANT_SCHEMAS[EngineVariant.ICE_COMPACT]),
    _schema_property_names(VARIANT_SCHEMAS[EngineVariant.BIKE]),
    _schema_property_names(VARIANT_SCHEMAS[EngineVariant.DIESEL_HD]),
    _schema_property_names(VARIANT_SCHEMAS[EngineVariant.EV]),
    _schema_property_names(ICE_COMPACT_LEGACY_SCHEMA),
    _schema_property_names(ICE_STANDARD_LEGACY_V8_SCHEMA),
    _schema_property_names(BIKE_LEGACY_SCHEMA),
)

ENGINE_VARIANT_PROPERTY_ORDER = {
    EngineVariant.ICE_STANDARD.value: _ordered_unique_property_names(
        _schema_property_names(VARIANT_SCHEMAS[EngineVariant.ICE_STANDARD]),
        _schema_property_names(ICE_STANDARD_LEGACY_V8_SCHEMA),
    ),
    EngineVariant.ICE_COMPACT.value: _ordered_unique_property_names(
        _schema_property_names(VARIANT_SCHEMAS[EngineVariant.ICE_COMPACT]),
        _schema_property_names(ICE_COMPACT_LEGACY_SCHEMA),
    ),
    EngineVariant.BIKE.value: _ordered_unique_property_names(
        _schema_property_names(VARIANT_SCHEMAS[EngineVariant.BIKE]),
        _schema_property_names(BIKE_LEGACY_SCHEMA),
    ),
    EngineVariant.DIESEL_HD.value: _schema_property_names(VARIANT_SCHEMAS[EngineVariant.DIESEL_HD]),
    EngineVariant.EV.value: _schema_property_names(VARIANT_SCHEMAS[EngineVariant.EV]),
}

ENGINE_INTEGER_LIKE_PROPERTIES = frozenset({
    'TorqueCurve',
    'MaxRPM',
    'StarterRPM',
    'FuelType',
    'EngineType',
    'MaxJakeBrakeStep',
})

ENGINE_PROPERTY_UNITS = {
    'TorqueCurve': 'import ref',
    'MaxTorque': 'N-m',
    'MaxRPM': 'RPM',
    'StarterRPM': 'RPM',
    'BlipDurationSeconds': 's',
    'MaxJakeBrakeStep': 'steps',
    'MotorMaxPower': 'kW',
    'MotorMaxVoltage': 'V',
}

ENGINE_READONLY_PROPERTIES = frozenset({
    'TorqueCurve',
})


def engine_property_unit(name: str) -> str:
    return ENGINE_PROPERTY_UNITS.get(name, '')


def engine_property_type(name: str) -> str:
    return 'int' if name in ENGINE_INTEGER_LIKE_PROPERTIES else 'float'


def build_engine_display_entry(name: str, value: Optional[Any], *, editable: Optional[bool] = None) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        'unit': engine_property_unit(name),
        'type': engine_property_type(name),
    }
    if editable is not None:
        entry['editable'] = editable
    elif name in ENGINE_READONLY_PROPERTIES:
        entry['editable'] = False

    if value is None:
        entry.update({
            'raw': '',
            'display': '',
            'missing': True,
        })
        return entry

    entry['raw'] = value
    if name == 'MaxTorque':
        entry['display'] = f"{value / 10000:.4f}".rstrip('0').rstrip('.')
    elif name == 'MotorMaxPower':
        entry['display'] = f"{value / 10000:.4f}".rstrip('0').rstrip('.')
    elif name == 'MotorMaxVoltage':
        entry['display'] = f"{value / 10000:.4f}".rstrip('0').rstrip('.')
    elif name in ('MaxRPM', 'StarterRPM'):
        entry['display'] = f"{value:.0f}"
    elif name == 'BlipDurationSeconds':
        entry['display'] = f"{value:.2f}"
    elif name == 'FuelType':
        labels = {0: 'Gas', 1: 'Gas', 2: 'Diesel', 3: 'Electric'}
        entry['display'] = labels.get(value, str(value))
    elif name in ('EngineType', 'TorqueCurve', 'MaxJakeBrakeStep'):
        entry['display'] = str(value)
    else:
        entry['display'] = f"{value:.6g}"
    return entry

# Tail patterns: import refs and footer at end of each variant
# These are the negative int32 values after the property data
VARIANT_TAILS = {
    EngineVariant.ICE_STANDARD: 3,   # 3 import refs (sound cues)
    EngineVariant.ICE_COMPACT: 3,
    EngineVariant.BIKE: 3,
    EngineVariant.DIESEL_HD: 3,
    EngineVariant.EV: 1,             # 1 import ref
}

FOOTER = b'\x00\x00\x00\x00\xc1\x83\x2a\x9e'  # 8 bytes
LEGACY_STANDARD_V8_HEADER = bytes.fromhex('000401050006010a010203020105')
LEGACY_BIKE_HEADER = bytes.fromhex('0004010500060108020201060203')
GENERATOR_SAFE_LAYOUTS = {
    (EngineVariant.ICE_STANDARD, None, 86),
    (EngineVariant.ICE_STANDARD, None, 88),
    (EngineVariant.ICE_STANDARD, 'standard_v8_legacy', 82),
    (EngineVariant.ICE_COMPACT, 'compact_vanilla', 72),
    (EngineVariant.ICE_COMPACT, 'compact_vanilla', 76),
    (EngineVariant.ICE_COMPACT, 'compact_vanilla', 78),
    (EngineVariant.ICE_COMPACT, 'compact_vanilla', 80),
    (EngineVariant.BIKE, 'bike_legacy', 82),
    (EngineVariant.BIKE, None, 88),
    (EngineVariant.DIESEL_HD, None, 91),
    (EngineVariant.EV, None, 63),
}


@dataclass
class EngineData:
    """Parsed engine data with named properties."""
    variant: EngineVariant
    header_bytes: bytes          # Raw header preserved for round-trip
    properties: Dict[str, Any]   # Property name -> value
    tail_imports: List[int]      # Negative import ref indices
    raw_bytes: bytes             # Original complete file for round-trip verification
    format_hint: Optional[str] = None

    @property
    def max_torque_nm(self) -> float:
        """Get MaxTorque in N-m (display units)."""
        raw = self.properties.get('MaxTorque', 0)
        return raw / 10000.0

    @property
    def max_rpm(self) -> float:
        return self.properties.get('MaxRPM', 0)

    @property
    def is_ev(self) -> bool:
        return self.variant == EngineVariant.EV

    @property
    def motor_max_power_kw(self) -> float:
        """Get MotorMaxPower in kW (EV only)."""
        raw = self.properties.get('MotorMaxPower', 0)
        return raw / 10000.0

    def estimated_hp(self, curve_factor: float = 0.946) -> float:
        """Estimate HP using simplified formula."""
        if self.is_ev:
            kw = self.motor_max_power_kw
            return kw / 0.7457 if kw > 0 else 0
        else:
            return self.max_torque_nm * self.max_rpm * curve_factor / 9549.0

    def to_display_dict(self) -> Dict[str, Any]:
        """Convert to display-friendly dict with human-readable values."""
        return {
            name: build_engine_display_entry(name, value)
            for name, value in self.properties.items()
        }


def detect_variant(data: bytes) -> EngineVariant:
    """Detect engine variant from file size and header bytes."""
    size = len(data)
    header_hex = data[:20].hex()

    for (expected_size, expected_header), variant in VARIANT_HEADERS.items():
        if size == expected_size and header_hex.startswith(expected_header):
            return variant

    # Fallback: try matching by size alone
    size_map = {63: EngineVariant.EV, 91: EngineVariant.DIESEL_HD}
    if size in size_map:
        return size_map[size]

    # For 86-byte files, check header to distinguish ICE_STANDARD from BIKE
    if size == 86:
        if data[:4].hex() == '00090012':
            return EngineVariant.BIKE
        return EngineVariant.ICE_STANDARD

    raise ValueError(f"Unknown engine variant: size={size}, header={header_hex[:20]}")


def _get_header_size(variant: EngineVariant, data: bytes) -> int:
    """Get the header size (bytes before property data) for a variant."""
    # Find the TorqueCurve import ref (FEFFFFFF or similar negative value)
    # by scanning for the first int32 that's a small negative number
    for i in range(0, min(20, len(data) - 3), 1):
        val = struct.unpack_from('<i', data, i)[0]
        if val < 0 and val > -100:  # Small negative = import ref
            return i
    # Fallback based on variant
    defaults = {
        EngineVariant.ICE_STANDARD: 14,
        EngineVariant.ICE_COMPACT: 12,
        EngineVariant.BIKE: 10,
        EngineVariant.DIESEL_HD: 10,
        EngineVariant.EV: 10,
    }
    return defaults.get(variant, 10)


def _is_vanilla_compact_layout(data: bytes, header_size: int) -> bool:
    """Return True when a compact engine uses the vanilla 10-float + 3-tail layout."""
    first_tail_off = header_size + 44
    if first_tail_off + 4 > len(data) - 8:
        return False
    value = struct.unpack_from('<i', data, first_tail_off)[0]
    return -256 <= value < 0


def parse_engine(data: bytes) -> EngineData:
    """Parse an engine .uexp file into structured data."""
    variant = detect_variant(data)
    # Find header end (where TorqueCurve import ref starts)
    header_size = _get_header_size(variant, data)
    header_bytes = data[:header_size]
    schema = VARIANT_SCHEMAS[variant]
    num_tail_imports = VARIANT_TAILS[variant]
    format_hint = None

    if variant == EngineVariant.ICE_COMPACT:
        if _is_vanilla_compact_layout(data, header_size):
            num_tail_imports = 3
            format_hint = 'compact_vanilla'
        else:
            schema = ICE_COMPACT_LEGACY_SCHEMA
            num_tail_imports = 2
            format_hint = 'compact_legacy'
    elif variant == EngineVariant.ICE_STANDARD and data.startswith(LEGACY_STANDARD_V8_HEADER):
        schema = ICE_STANDARD_LEGACY_V8_SCHEMA
        num_tail_imports = 3
        format_hint = 'standard_v8_legacy'
    elif variant == EngineVariant.BIKE and data.startswith(LEGACY_BIKE_HEADER):
        schema = BIKE_LEGACY_SCHEMA
        num_tail_imports = 3
        format_hint = 'bike_legacy'

    # Parse properties
    offset = header_size
    properties = {}

    for prop_name, prop_type, prop_size in schema:
        if offset + prop_size > len(data) - 8:  # Leave room for footer
            break

        if prop_type == 'f':
            value = struct.unpack_from('<f', data, offset)[0]
        elif prop_type == 'i' or prop_type == 'imp':
            value = struct.unpack_from('<i', data, offset)[0]
        elif prop_type == 'e1':
            value = data[offset]
        elif prop_type == 'e4':
            value = struct.unpack_from('<i', data, offset)[0]
        else:
            value = struct.unpack_from('<i', data, offset)[0]

        properties[prop_name] = value
        offset += prop_size

    # Parse tail import refs
    tail_imports = []
    for _ in range(num_tail_imports):
        if offset + 4 <= len(data) - 8:
            imp_ref = struct.unpack_from('<i', data, offset)[0]
            tail_imports.append(imp_ref)
            offset += 4

    return EngineData(
        variant=variant,
        header_bytes=header_bytes,
        properties=properties,
        tail_imports=tail_imports,
        raw_bytes=data,
        format_hint=format_hint,
    )


def layout_signature(engine: EngineData) -> tuple[EngineVariant, Optional[str], int]:
    """Return a stable layout tag for validation and donor selection."""
    return (engine.variant, engine.format_hint, len(engine.raw_bytes))


def is_generator_safe_layout(engine: EngineData) -> bool:
    """Return True when an engine uses a layout the website generator guarantees."""
    return layout_signature(engine) in GENERATOR_SAFE_LAYOUTS


def serialize_engine(engine: EngineData) -> bytes:
    """Serialize engine data back to binary .uexp format."""
    schema = VARIANT_SCHEMAS[engine.variant]
    if engine.variant == EngineVariant.ICE_COMPACT:
        if engine.format_hint == 'compact_legacy' or (
            engine.format_hint is None
            and 'AfterFireProbability' in engine.properties
            and len(engine.tail_imports) <= 2
        ):
            schema = ICE_COMPACT_LEGACY_SCHEMA
    elif engine.variant == EngineVariant.ICE_STANDARD and engine.format_hint == 'standard_v8_legacy':
        schema = ICE_STANDARD_LEGACY_V8_SCHEMA
    elif engine.variant == EngineVariant.BIKE and engine.format_hint == 'bike_legacy':
        schema = BIKE_LEGACY_SCHEMA

    parts = [engine.header_bytes]

    for prop_name, prop_type, prop_size in schema:
        value = engine.properties.get(prop_name, 0)

        if prop_type == 'f':
            parts.append(struct.pack('<f', value))
        elif prop_type == 'i' or prop_type == 'imp':
            parts.append(struct.pack('<i', int(value)))
        elif prop_type == 'e1':
            parts.append(bytes([int(value) & 0xFF]))
        elif prop_type == 'e4':
            parts.append(struct.pack('<i', int(value)))
        else:
            parts.append(struct.pack('<i', int(value)))

    # Tail imports
    for imp_ref in engine.tail_imports:
        parts.append(struct.pack('<i', imp_ref))

    # Footer
    parts.append(FOOTER)

    return b''.join(parts)


def round_trip_test(data: bytes) -> bool:
    """Parse and re-serialize, verify identical bytes."""
    try:
        engine = parse_engine(data)
        rebuilt = serialize_engine(engine)
        return rebuilt == data
    except Exception as e:
        return False

