"""
Transmission .uexp parser for Motor Town MTTransmissionDataAsset files.

Binary format (vanilla & modded):
  [header] [00000000] [gear records] [tail properties] [import ref] [description] [footer]

Header structure (variable length, 9-12 bytes):
  Bytes 0-1: always 00 05 (or 00 03 for some)
  Middle bytes: transmission subtype markers
  hdr[-3]: ClutchType enum
  hdr[-2]: TransmissionCategory (1=manual/truck, 2=heavy, 3=automatic/CVT)
  hdr[-1]: GearCount (total gears including R and N)

Gear record format:
  Normal gear: 07 [ratio:f32] [efficiency:f32] [type:i32] [label:type_bytes]
  Neutral gear: 80 07 01 [efficiency:f32] [type:i32] [label:type_bytes]
  type = byte count of label INCLUDING null terminator (2='R\\0', 3='R4\\0')
  Between gears: single 00 separator byte

Post-gear properties:
  [DefaultGearIndex:i32]
  [tail floats...]        - ShiftTimeSeconds + additional properties (count varies)
  [GearGrindingSound:i32] - negative import ref (always -5 = SC_Grinding)
  [description_length:i32]
  [description string + \\x00]
  [footer: 8 bytes]

Tail float counts by transmission type:
  5 floats: most manuals, trucks, buses (ShiftTime, StallSpeed, DownshiftRPM, TQMult, MaxTQ)
  4 floats: electric, karts
  3 floats: some TQ autos, Formula (first float may be StallSpeed not ShiftTime)
  2 floats: TQ4SpeedSports
  1 float:  DCT/some autos
  14 floats: CVT (ScooterCVT)

Known ClutchType values:
  1 = HeavyDutyClutch (18-speed)
  2 = HeavyDutyClutch2 (13-speed)
  3 = MultiPlateClutch (manuals, trucks, bikes)
  4 = AutoClutch (karts, MiniBus, some TQ)
  6 = TorqueConverter (TQ autos)
  7 = CVTBelt (CVTs)
"""
import struct
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple


FOOTER = b'\x00\x00\x00\x00\xc1\x83\x2a\x9e'

# ClutchType enum values
CLUTCH_TYPES = {
    1: 'HeavyDutyClutch',
    2: 'HeavyDutyClutch2',
    3: 'MultiPlateClutch',
    4: 'AutoClutch',
    6: 'TorqueConverter',
    7: 'CVTBelt',
}

TRANS_CATEGORIES = {
    1: 'Manual/Truck',
    2: 'Heavy',
    3: 'Automatic/CVT',
}

# Property names for tail floats (best-effort naming)
PROPERTY_NAMES_LONG = [
    ('ShiftTimeSeconds', 's'),
    ('TorqueConverterStallSpeed', 'RPM'),
    ('DownshiftRPM', 'RPM'),
    ('TorqueConverterMultiplier', 'x'),
    ('MaxTorqueCapacity', ''),
]


def _get_property_names(count: int, first_is_shift: bool = True) -> List[tuple]:
    """Get property names for a given number of tail floats."""
    if first_is_shift:
        names = list(PROPERTY_NAMES_LONG[:count])
        for i in range(len(names), count):
            names.append((f'Property_{i}', ''))
        return names
    else:
        # First float is NOT shift time (TQ autos without shift time)
        names = list(PROPERTY_NAMES_LONG[1:count + 1])
        for i in range(len(names), count):
            names.append((f'Property_{i}', ''))
        return names


@dataclass
class GearRecord:
    label: str          # 'R', 'N', '1', '2', 'R2', 'L1', etc.
    ratio: float        # Gear ratio (negative for reverse, 0 for neutral)
    efficiency: float   # Typically 10.0 (bikes) or 100.0 (trucks/cars)
    gear_type: int      # Label byte count including null (2='R\0', 3='R4\0')
    neutral: bool       # True for neutral gears (encoded as 80 07 01)


@dataclass
class TransmissionData:
    """Parsed transmission data."""
    header_bytes: bytes         # Raw header preserved for round-trip
    padding: bytes              # 4 zero bytes after header
    gears: List[GearRecord]
    default_gear_index: int     # Usually 1 for manuals, 2+ for trucks
    tail_floats: List[float]    # ShiftTimeSeconds and possibly more
    gear_grinding_sound: int    # Import ref (always -5 = SC_Grinding)
    description_length: int
    description: str            # e.g. "Eaton Fuller FS-4106A"
    raw_bytes: bytes

    @property
    def clutch_type(self) -> int:
        """Extract ClutchType from header (3rd byte from end)."""
        if len(self.header_bytes) >= 3:
            return self.header_bytes[-3]
        return 0

    @property
    def clutch_type_name(self) -> str:
        return CLUTCH_TYPES.get(self.clutch_type, f'Unknown({self.clutch_type})')

    @property
    def category(self) -> int:
        """Extract TransmissionCategory from header (2nd byte from end)."""
        if len(self.header_bytes) >= 2:
            return self.header_bytes[-2]
        return 0

    @property
    def category_name(self) -> str:
        return TRANS_CATEGORIES.get(self.category, f'Unknown({self.category})')

    @property
    def num_forward_gears(self) -> int:
        return sum(1 for g in self.gears
                   if not g.neutral and not g.label.startswith('R'))

    @property
    def num_reverse_gears(self) -> int:
        return sum(1 for g in self.gears if g.label.startswith('R'))

    @property
    def gear_ratios(self) -> Dict[str, float]:
        return {g.label: g.ratio for g in self.gears}

    @property
    def has_shift_time(self) -> bool:
        """Whether the first tail float is ShiftTimeSeconds (vs stall speed)."""
        if not self.tail_floats:
            return False
        return self.tail_floats[0] < 10.0

    @property
    def shift_time(self) -> Optional[float]:
        """Return ShiftTimeSeconds if present."""
        if self.has_shift_time:
            return self.tail_floats[0]
        return None

    @shift_time.setter
    def shift_time(self, value: float) -> None:
        """Set ShiftTimeSeconds (only if the first tail float is shift time)."""
        if self.has_shift_time and self.tail_floats:
            self.tail_floats[0] = value

    def to_display_dict(self) -> Dict[str, Any]:
        prop_names = _get_property_names(len(self.tail_floats), self.has_shift_time)

        result = {
            'ClutchType':       {'raw': self.clutch_type, 'display': self.clutch_type_name,
                                 'unit': '', 'editable': False},
            'Category':         {'raw': self.category, 'display': self.category_name,
                                 'unit': '', 'editable': False},
            'GearCount':        {'raw': len(self.gears), 'display': str(len(self.gears)),
                                 'unit': 'total gears', 'editable': False},
            'ForwardGears':     {'raw': self.num_forward_gears,
                                 'display': str(self.num_forward_gears),
                                 'unit': '', 'editable': False},
            'DefaultGearIndex': {'raw': self.default_gear_index,
                                 'display': str(self.default_gear_index), 'unit': ''},
            'Description':      {'raw': self.description, 'display': self.description, 'unit': ''},
        }
        # Gear ratios
        for i, g in enumerate(self.gears):
            editable = not g.neutral
            result[f'Gear_{g.label}_Ratio'] = {
                'raw': g.ratio, 'display': f"{g.ratio:.4f}", 'unit': '',
                'editable': editable,
            }
        # Named tail properties
        for i, v in enumerate(self.tail_floats):
            name, unit = prop_names[i] if i < len(prop_names) else (f'Property_{i}', '')
            result[name] = {'raw': v, 'display': f"{v:.6g}", 'unit': unit}
        # GearGrindingSound
        result['GearGrindingSound'] = {
            'raw': self.gear_grinding_sound,
            'display': f'SC_Grinding (import {self.gear_grinding_sound})',
            'unit': '', 'editable': False,
        }
        return result


def _find_gear_start(data: bytes) -> Optional[int]:
    """Find the start of gear records (after 00000000 padding)."""
    for i in range(4, min(30, len(data) - 5)):
        if data[i:i + 4] == b'\x00\x00\x00\x00':
            next_b = data[i + 4]
            if next_b == 0x07 or next_b == 0x80:
                return i + 4
    return None


def parse_transmission(data: bytes) -> TransmissionData:
    """Parse a transmission .uexp file into structured data."""
    gear_start = _find_gear_start(data)
    if gear_start is None:
        raise ValueError("Cannot find gear start marker in transmission file")

    header_end = gear_start - 4
    header = data[:header_end]
    padding = data[header_end:gear_start]
    num_gears = header[-1]

    # Parse gear records
    gears: List[GearRecord] = []
    off = gear_start

    for g in range(num_gears):
        if off >= len(data) - 4:
            break

        marker = data[off]

        if marker == 0x07:
            # Normal gear: 07 [ratio:f32] [eff:f32] [type:i32] [label:type_bytes]
            ratio = struct.unpack_from('<f', data, off + 1)[0]
            eff = struct.unpack_from('<f', data, off + 5)[0]
            gtype = struct.unpack_from('<i', data, off + 9)[0]
            label_len = gtype  # includes null terminator
            label = data[off + 13:off + 13 + label_len - 1].decode('ascii', errors='replace')
            rec_end = off + 13 + label_len
            gears.append(GearRecord(
                label=label, ratio=ratio, efficiency=eff,
                gear_type=gtype, neutral=False,
            ))
            off = rec_end

        elif marker == 0x80:
            # Neutral gear: 80 07 01 [eff:f32] [type:i32] [label:type_bytes]
            eff = struct.unpack_from('<f', data, off + 3)[0]
            gtype = struct.unpack_from('<i', data, off + 7)[0]
            label_len = gtype
            label = data[off + 11:off + 11 + label_len - 1].decode('ascii', errors='replace')
            rec_end = off + 11 + label_len
            gears.append(GearRecord(
                label=label, ratio=0.0, efficiency=eff,
                gear_type=gtype, neutral=True,
            ))
            off = rec_end

        else:
            raise ValueError(
                f"Unexpected gear marker 0x{marker:02x} at offset {off}"
            )

        # Skip single 00 separator between gears
        if g < num_gears - 1 and off < len(data) and data[off] == 0x00:
            off += 1

    # Parse tail properties
    # DefaultGearIndex
    default_gear_index = struct.unpack_from('<i', data, off)[0]
    off += 4

    # Read floats until we hit the import ref (negative int, typically -5)
    tail_floats: List[float] = []
    gear_grinding_sound = 0
    while off + 4 <= len(data) - 8:
        val_i = struct.unpack_from('<i', data, off)[0]
        if val_i < 0 and val_i > -20:
            gear_grinding_sound = val_i
            off += 4
            break
        tail_floats.append(struct.unpack_from('<f', data, off)[0])
        off += 4

    # Read description string (if present — when desc_len=0, the field is absent
    # and the next 8 bytes are the footer)
    desc_len = 0
    description = ""
    if off + 8 <= len(data):
        candidate = data[off:off + 8]
        if candidate == FOOTER:
            # No description field — footer starts immediately
            pass
        else:
            desc_len = struct.unpack_from('<i', data, off)[0]
            off += 4
            if desc_len > 0 and off + desc_len <= len(data):
                description = data[off:off + desc_len - 1].decode('ascii', errors='replace')

    return TransmissionData(
        header_bytes=header,
        padding=padding,
        gears=gears,
        default_gear_index=default_gear_index,
        tail_floats=tail_floats,
        gear_grinding_sound=gear_grinding_sound,
        description_length=desc_len,
        description=description,
        raw_bytes=data,
    )


def serialize_transmission(trans: TransmissionData) -> bytes:
    """Serialize transmission data back to binary .uexp format."""
    parts: List[bytes] = [trans.header_bytes, trans.padding]

    for i, gear in enumerate(trans.gears):
        label_bytes = gear.label.encode('ascii') + b'\x00'

        if gear.neutral:
            # Neutral gear: 80 07 01 [eff:f32] [type:i32] [label_bytes]
            parts.append(b'\x80\x07\x01')
            parts.append(struct.pack('<f', gear.efficiency))
            parts.append(struct.pack('<i', gear.gear_type))
            parts.append(label_bytes)
        else:
            # Normal gear: 07 [ratio:f32] [eff:f32] [type:i32] [label_bytes]
            parts.append(b'\x07')
            parts.append(struct.pack('<f', gear.ratio))
            parts.append(struct.pack('<f', gear.efficiency))
            parts.append(struct.pack('<i', gear.gear_type))
            parts.append(label_bytes)

        # Separator between gears
        if i < len(trans.gears) - 1:
            next_gear = trans.gears[i + 1]
            if next_gear.neutral:
                # Separator before neutral gear is 0x80 (not 0x00)
                # The 0x80 is consumed by the neutral gear's 80 07 01 prefix
                # so we DON'T emit it here — it's emitted as part of the next gear
                pass
            else:
                parts.append(b'\x00')

    # DefaultGearIndex
    parts.append(struct.pack('<i', trans.default_gear_index))

    # Tail floats
    for v in trans.tail_floats:
        parts.append(struct.pack('<f', v))

    # GearGrindingSound import ref
    parts.append(struct.pack('<i', trans.gear_grinding_sound))

    # Description string (only written if description exists)
    if trans.description_length > 0:
        parts.append(struct.pack('<i', trans.description_length))
        parts.append(trans.description.encode('ascii') + b'\x00')

    # Footer
    parts.append(FOOTER)

    return b''.join(parts)


def round_trip_test(data: bytes) -> bool:
    """Verify that parse→serialize produces identical bytes."""
    try:
        trans = parse_transmission(data)
        rebuilt = serialize_transmission(trans)
        return rebuilt == data
    except Exception:
        return False
