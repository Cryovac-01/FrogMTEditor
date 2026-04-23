"""
LSD .uexp parser for Motor Town MTLSDDataAsset files.
Handles all LSD variants (10-19 bytes).

Binary format:
  [header bytes] [float properties] [00000000 C1832A9E footer]

Known variants:
  OpenDifferential:     10B = 2B header + 0 floats + 8B footer
  LockedDifferential:   11B = 3B header + 0 floats + 8B footer
  1WayClutchPack:       15B = 3B header + 1 float + 8B footer
  1-5WayClutchPack:     19B = 3B header + 2 floats + 8B footer
  2WayClutchPack (100): 19B = 3B header + 2 floats + 8B footer
  2WayClutchPack:       19B = 3B header + 2 floats + 8B footer
"""
import struct
from dataclasses import dataclass, field
from typing import Dict, List, Any


FOOTER = b'\x00\x00\x00\x00\xc1\x83\x2a\x9e'

# LSD property names by float count
LSD_PROPERTY_NAMES = {
    0: [],
    1: ['LockingTorque'],
    2: ['AccelLockPercent', 'DecelLockPercent'],
}


@dataclass
class LSDData:
    """Parsed LSD data."""
    header_bytes: bytes
    properties: Dict[str, float]
    property_order: List[str]
    raw_bytes: bytes

    def to_display_dict(self) -> Dict[str, Any]:
        result = {}
        for name, value in self.properties.items():
            if 'Percent' in name or 'Lock' in name:
                result[name] = {'raw': value, 'display': f"{value:.1f}", 'unit': '%'}
            else:
                result[name] = {'raw': value, 'display': f"{value:.6g}", 'unit': ''}
        return result


def parse_lsd(data: bytes) -> LSDData:
    """Parse an LSD .uexp file into structured data."""
    # Footer is always last 8 bytes
    # Header is everything before the float data
    file_size = len(data)
    footer_size = 8

    # Try to find the header size (remaining bytes must be divisible by 4 for floats)
    data_bytes = file_size - footer_size
    header_size = None
    for hdr in range(2, min(8, data_bytes + 1)):
        remaining = data_bytes - hdr
        if remaining >= 0 and remaining % 4 == 0:
            header_size = hdr
            break

    if header_size is None:
        raise ValueError(f"Cannot determine LSD header for {file_size}B file")

    header_bytes = data[:header_size]
    num_floats = (data_bytes - header_size) // 4

    prop_names = LSD_PROPERTY_NAMES.get(num_floats,
                                         [f'Property_{i}' for i in range(num_floats)])

    properties = {}
    property_order = []
    offset = header_size
    for i in range(num_floats):
        name = prop_names[i] if i < len(prop_names) else f'Property_{i}'
        value = struct.unpack_from('<f', data, offset)[0]
        properties[name] = value
        property_order.append(name)
        offset += 4

    return LSDData(
        header_bytes=header_bytes,
        properties=properties,
        property_order=property_order,
        raw_bytes=data,
    )


def serialize_lsd(lsd: LSDData) -> bytes:
    """Serialize LSD data back to binary .uexp format."""
    parts = [lsd.header_bytes]
    for name in lsd.property_order:
        value = lsd.properties.get(name, 0.0)
        parts.append(struct.pack('<f', value))
    parts.append(FOOTER)
    return b''.join(parts)


def round_trip_test(data: bytes) -> bool:
    try:
        lsd = parse_lsd(data)
        rebuilt = serialize_lsd(lsd)
        return rebuilt == data
    except Exception:
        return False
