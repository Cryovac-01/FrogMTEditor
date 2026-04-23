"""
Policies DataTable parser for Motor Town.

Binary format of Policies.uexp:
  [10-byte header]
  [int32 num_rows]
  [rows...]
  [4-byte footer: C1 83 2A 9E]

Each row:
  [FName: int32 name_idx + int32 instance]      (8 bytes)
  [11-byte constant prefix]                      (FText header)
  [int32 display_string_length]
  [display_string with null terminator]
  [int32 cost]
  [float secondary_value]
  [int32 zero_pad]
  [int32 flag]
  [FName: int32 effect_type_idx + int32 instance] (8 bytes)
  [float effect_value]

Name table in Policies.uasset:
  Each entry: [int32 str_len] [chars + null] [uint32 hash]
  NameCount at header offset 0x41
  NameOffset at header offset 0x45

Effect types (enum EMTTownPolicyEffectType):
  FuelSubsidy
  MaxCargoHeightAdd
  MaxGVWKgAdd
  MaxVehicleLengthAdd
  CompanyBusConditionDecreaseSpeedMultiplier
  CompanyTaxiConditionDecreaseSpeedMultiplier
  CompanyTruckConditionDecreaseSpeedMultiplier
"""
import struct
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

FOOTER = b'\xc1\x83\x2a\x9e'
HEADER_SIZE = 10
ROW_PREFIX = bytes([0x00, 0x09, 0x02, 0x00, 0x00, 0x00, 0xFF, 0x01, 0x00, 0x00, 0x00])

# Header offsets (relative to start of .uasset after FolderName)
# These are absolute offsets in the vanilla Policies.uasset
NAME_COUNT_OFFSET = 0x41
NAME_OFFSET_OFFSET = 0x45
TOTAL_HEADER_SIZE_OFFSET = 0x1C
EXPORT_OFFSET_FIELD = 0x5D       # Header field holding ExportOffset

# Export entry field offsets (relative to export entry start)
EXPORT_SERIAL_SIZE_OFF = 28      # int64: serialized .uexp content size (excl. footer)
EXPORT_SERIAL_OFFSET_OFF = 36    # int64: absolute offset where serial data begins

# Effect type short names → full enum strings
EFFECT_TYPES = {
    'FuelSubsidy': 'EMTTownPolicyEffectType::FuelSubsidy',
    'MaxCargoHeightAdd': 'EMTTownPolicyEffectType::MaxCargoHeightAdd',
    'MaxGVWKgAdd': 'EMTTownPolicyEffectType::MaxGVWKgAdd',
    'MaxVehicleLengthAdd': 'EMTTownPolicyEffectType::MaxVehicleLengthAdd',
    'CompanyBusConditionDecreaseSpeedMultiplier': 'EMTTownPolicyEffectType::CompanyBusConditionDecreaseSpeedMultiplier',
    'CompanyTaxiConditionDecreaseSpeedMultiplier': 'EMTTownPolicyEffectType::CompanyTaxiConditionDecreaseSpeedMultiplier',
    'CompanyTruckConditionDecreaseSpeedMultiplier': 'EMTTownPolicyEffectType::CompanyTruckConditionDecreaseSpeedMultiplier',
}

# User-friendly labels for effect types
EFFECT_TYPE_LABELS = {
    'FuelSubsidy': 'Fuel Subsidy',
    'MaxCargoHeightAdd': 'Cargo Height Limit Increase',
    'MaxGVWKgAdd': 'GVW (Weight) Limit Increase',
    'MaxVehicleLengthAdd': 'Vehicle Length Limit Increase',
    'CompanyBusConditionDecreaseSpeedMultiplier': 'Bus Condition Wear Reduction',
    'CompanyTaxiConditionDecreaseSpeedMultiplier': 'Taxi Condition Wear Reduction',
    'CompanyTruckConditionDecreaseSpeedMultiplier': 'Truck Condition Wear Reduction',
}

# What units each effect type uses
EFFECT_TYPE_UNITS = {
    'FuelSubsidy': ('multiplier', 'Multiplier (e.g. 0.2 = 20% subsidy)'),
    'MaxCargoHeightAdd': ('cm', 'Height in cm (e.g. 100 = 1m)'),
    'MaxGVWKgAdd': ('kg', 'Weight in kg (e.g. 10000 = 10t)'),
    'MaxVehicleLengthAdd': ('cm', 'Length in cm (e.g. 500 = 5m)'),
    'CompanyBusConditionDecreaseSpeedMultiplier': ('multiplier', 'Wear speed multiplier (e.g. 0.8 = 20% slower)'),
    'CompanyTaxiConditionDecreaseSpeedMultiplier': ('multiplier', 'Wear speed multiplier (e.g. 0.8 = 20% slower)'),
    'CompanyTruckConditionDecreaseSpeedMultiplier': ('multiplier', 'Wear speed multiplier (e.g. 0.8 = 20% slower)'),
}


@dataclass
class PolicyRow:
    """A single policy row from the DataTable."""
    row_name: str                 # FName row identifier (e.g. "Policy1")
    row_name_idx: int             # Name table index for row name
    row_name_instance: int        # FName instance number
    display_name: str             # Human-readable display text
    cost: int                     # Policy cost (game currency)
    secondary_value: float        # Secondary float (UI-related)
    flag: int                     # Enabled flag (always 1 in vanilla)
    effect_type: str              # Short effect type name (e.g. "FuelSubsidy")
    effect_type_idx: int          # Name table index for the enum FName
    effect_value: float           # The actual effect magnitude
    is_new: bool = False          # True if added by the mod (not in vanilla)

    def effect_label(self) -> str:
        return EFFECT_TYPE_LABELS.get(self.effect_type, self.effect_type)

    def effect_unit_info(self) -> Tuple[str, str]:
        return EFFECT_TYPE_UNITS.get(self.effect_type, ('', ''))


@dataclass
class PoliciesData:
    """Parsed policies DataTable."""
    header: bytes                 # 10-byte .uexp header
    rows: List[PolicyRow]
    names: List[str]              # Name table from .uasset
    name_hashes: List[int]        # Hash for each name entry
    uasset_bytes: bytes           # Full .uasset bytes (for reconstruction)
    uexp_bytes: bytes             # Full .uexp bytes (for reference)

    # Offset info for .uasset patching
    name_table_start: int = 0     # Byte offset where name table begins
    name_table_end: int = 0       # Byte offset where name table ends

    def get_effect_type_idx(self, short_name: str) -> int:
        """Find the name table index for an effect type enum value."""
        full = EFFECT_TYPES.get(short_name)
        if not full:
            return -1
        for i, n in enumerate(self.names):
            if n == full:
                return i
        return -1


def _compute_fname_hash(name: str) -> int:
    """Compute a UE4-compatible FName hash.

    UE4 uses a case-insensitive CRC (Strihash).  For modded assets loaded
    via pak patching the engine re-hashes on load, so the stored value is
    advisory.  We use Python's zlib CRC-32 on the lowercase name.
    """
    import zlib
    return zlib.crc32(name.lower().encode('utf-8')) & 0xFFFFFFFF


def _parse_name_table(ua: bytes) -> Tuple[List[str], List[int], int, int]:
    """Parse the name table from a Policies .uasset.

    Returns (names, hashes, table_start_offset, table_end_offset).
    """
    name_count = struct.unpack_from('<i', ua, NAME_COUNT_OFFSET)[0]
    name_offset = struct.unpack_from('<i', ua, NAME_OFFSET_OFFSET)[0]

    names: List[str] = []
    hashes: List[int] = []
    off = name_offset

    for _ in range(name_count):
        str_len = struct.unpack_from('<i', ua, off)[0]
        off += 4
        if str_len <= 0 or str_len > 1024:
            break
        name = ua[off:off + str_len - 1].decode('utf-8', errors='replace')
        off += str_len
        h = struct.unpack_from('<I', ua, off)[0]
        off += 4
        names.append(name)
        hashes.append(h)

    return names, hashes, name_offset, off


def parse_policies(ua: bytes, ue: bytes) -> PoliciesData:
    """Parse policies from .uasset + .uexp byte data."""
    names, hashes, nt_start, nt_end = _parse_name_table(ua)

    # Build reverse lookup: effect enum full name → short name
    enum_to_short = {}
    for short, full in EFFECT_TYPES.items():
        enum_to_short[full] = short

    header = ue[:HEADER_SIZE]
    num_rows = struct.unpack_from('<i', ue, HEADER_SIZE)[0]

    rows: List[PolicyRow] = []
    off = HEADER_SIZE + 4

    for _ in range(num_rows):
        # FName
        name_idx = struct.unpack_from('<i', ue, off)[0]
        name_inst = struct.unpack_from('<i', ue, off + 4)[0]
        row_name = names[name_idx] if name_idx < len(names) else f'Unknown_{name_idx}'
        off += 8

        # Skip 11-byte prefix
        off += len(ROW_PREFIX)

        # Display string
        str_len = struct.unpack_from('<i', ue, off)[0]
        off += 4
        display = ue[off:off + str_len - 1].decode('utf-8', errors='replace')
        off += str_len

        # Fields
        cost = struct.unpack_from('<i', ue, off)[0]; off += 4
        secondary = struct.unpack_from('<f', ue, off)[0]; off += 4
        _pad = struct.unpack_from('<i', ue, off)[0]; off += 4
        flag = struct.unpack_from('<i', ue, off)[0]; off += 4
        effect_idx = struct.unpack_from('<i', ue, off)[0]; off += 4
        _effect_inst = struct.unpack_from('<i', ue, off)[0]; off += 4
        effect_val = struct.unpack_from('<f', ue, off)[0]; off += 4

        effect_full = names[effect_idx] if effect_idx < len(names) else ''
        effect_short = enum_to_short.get(effect_full, effect_full.split('::')[-1])

        rows.append(PolicyRow(
            row_name=row_name,
            row_name_idx=name_idx,
            row_name_instance=name_inst,
            display_name=display,
            cost=cost,
            secondary_value=secondary,
            flag=flag,
            effect_type=effect_short,
            effect_type_idx=effect_idx,
            effect_value=effect_val,
        ))

    return PoliciesData(
        header=header,
        rows=rows,
        names=list(names),
        name_hashes=list(hashes),
        uasset_bytes=ua,
        uexp_bytes=ue,
        name_table_start=nt_start,
        name_table_end=nt_end,
    )


def serialize_uexp(data: PoliciesData) -> bytes:
    """Serialize policy rows back to .uexp binary."""
    parts = [data.header]
    parts.append(struct.pack('<i', len(data.rows)))

    for row in data.rows:
        # FName
        parts.append(struct.pack('<ii', row.row_name_idx, row.row_name_instance))
        # Prefix
        parts.append(ROW_PREFIX)
        # Display string
        encoded = row.display_name.encode('utf-8') + b'\x00'
        parts.append(struct.pack('<i', len(encoded)))
        parts.append(encoded)
        # Fields
        parts.append(struct.pack('<i', row.cost))
        parts.append(struct.pack('<f', row.secondary_value))
        parts.append(struct.pack('<i', 0))       # zero pad
        parts.append(struct.pack('<i', row.flag))
        parts.append(struct.pack('<ii', row.effect_type_idx, 0))  # effect FName
        parts.append(struct.pack('<f', row.effect_value))

    parts.append(FOOTER)
    return b''.join(parts)


def update_uasset_serial_size(ua: bytes, uexp: bytes) -> bytes:
    """Update the .uasset export entry's SerialSize to match actual .uexp content.

    The SerialSize field (int64 at export_entry + 28) must equal the .uexp
    file size minus the 4-byte footer. If this doesn't match, UE5's async
    loader will fail with:
        LowLevelFatalError [...AsyncLoading.cpp] No outstanding IO,
        no nodes in the queue, yet we still have N 'AddedNodes'

    This function MUST be called after serialize_uexp() whenever the .uexp
    content may have changed size (modified display names, added/removed rows).

    Args:
        ua: Current .uasset bytes (possibly already modified by _add_name_to_uasset).
        uexp: The serialized .uexp bytes from serialize_uexp().

    Returns:
        Updated .uasset bytes with correct SerialSize.
    """
    new_serial_size = len(uexp) - len(FOOTER)

    buf = bytearray(ua)
    export_offset = struct.unpack_from('<i', buf, EXPORT_OFFSET_FIELD)[0]
    serial_size_pos = export_offset + EXPORT_SERIAL_SIZE_OFF

    if serial_size_pos + 8 <= len(buf):
        # Write as int64 (little-endian) to match UE5's FObjectExport layout
        struct.pack_into('<q', buf, serial_size_pos, new_serial_size)

    return bytes(buf)


def _add_name_to_uasset(ua: bytes, name: str, names: List[str],
                         hashes: List[int], nt_end: int) -> Tuple[bytes, int]:
    """Add a new name entry to the .uasset name table.

    Returns (new_uasset_bytes, new_name_index).
    Adjusts NameCount and all offsets that point past the name table.
    """
    # Build the new name entry bytes
    encoded = name.encode('utf-8') + b'\x00'
    h = _compute_fname_hash(name)
    entry = struct.pack('<i', len(encoded)) + encoded + struct.pack('<I', h)
    shift = len(entry)
    new_idx = len(names)

    # Insert entry at nt_end
    new_ua = bytearray(ua[:nt_end]) + bytearray(entry) + bytearray(ua[nt_end:])

    # Update NameCount
    old_count = struct.unpack_from('<i', new_ua, NAME_COUNT_OFFSET)[0]
    struct.pack_into('<i', new_ua, NAME_COUNT_OFFSET, old_count + 1)

    # Update TotalHeaderSize (0x1C)
    old_total = struct.unpack_from('<i', new_ua, TOTAL_HEADER_SIZE_OFFSET)[0]
    if old_total > 0:
        struct.pack_into('<i', new_ua, TOTAL_HEADER_SIZE_OFFSET, old_total + shift)

    # Find and adjust all int32 offset fields in the header that point
    # past the name table.  We scan a known set of header offset positions.
    # These offsets were mapped from the vanilla Policies.uasset:
    #   0x4D: SoftObjectPathsOffset
    #   0x5D: ExportOffset
    #   0x65: ImportOffset
    #   0x69: DependsOffset
    OFFSET_FIELDS = [0x4D, 0x5D, 0x65, 0x69]
    for field_off in OFFSET_FIELDS:
        old_val = struct.unpack_from('<i', new_ua, field_off)[0]
        if old_val >= nt_end:
            struct.pack_into('<i', new_ua, field_off, old_val + shift)

    # Also fix the export entry's SerialOffset.
    # The export table starts at the (now shifted) ExportOffset.
    export_offset = struct.unpack_from('<i', new_ua, 0x5D)[0]
    # In the export entry, SerialOffset is at +36 bytes from entry start
    # (based on vanilla: ExportOffset=0x4BC, SerialOffset at 0x4E0 = 0x4BC+36)
    serial_off_pos = export_offset + 36
    if serial_off_pos + 4 <= len(new_ua):
        old_serial = struct.unpack_from('<i', new_ua, serial_off_pos)[0]
        if old_serial > 0:
            struct.pack_into('<i', new_ua, serial_off_pos, old_serial + shift)

    # NOTE: SerialSize (int64 at export_entry + 28) is NOT updated here —
    # it must be finalized by calling update_uasset_serial_size() after
    # serialize_uexp(), since the final .uexp size depends on row content.

    # Update the cached data
    names.append(name)
    hashes.append(h)

    return bytes(new_ua), new_idx


def add_policy_row(data: PoliciesData, display_name: str, cost: int,
                   effect_short: str, effect_value: float,
                   row_name: str = '') -> PolicyRow:
    """Add a new policy row to the data.

    Creates a new name table entry for the row name if needed, and
    looks up the existing effect type enum name index.

    Args:
        data: PoliciesData to modify in-place.
        display_name: Human-readable policy description.
        cost: Policy cost in game currency.
        effect_short: Short effect type key (e.g. 'FuelSubsidy').
        effect_value: Numeric effect magnitude.
        row_name: Optional row name. Auto-generated if empty.

    Returns:
        The newly created PolicyRow.
    """
    # Find effect type index (must already exist in name table)
    effect_idx = data.get_effect_type_idx(effect_short)
    if effect_idx < 0:
        raise ValueError(f"Unknown effect type: {effect_short}")

    # Generate row name if not provided
    if not row_name:
        existing = {r.row_name for r in data.rows}
        base = effect_short.replace('::', '_')
        for i in range(1, 100):
            candidate = f"{base}_{i}"
            if candidate not in existing and candidate not in data.names:
                row_name = candidate
                break
        if not row_name:
            row_name = f"CustomPolicy_{len(data.rows)}"

    # Add name to .uasset if needed
    if row_name not in data.names:
        new_ua, name_idx = _add_name_to_uasset(
            data.uasset_bytes, row_name, data.names, data.name_hashes,
            data.name_table_end,
        )
        data.uasset_bytes = new_ua
        # Recalculate name table end
        _, _, _, data.name_table_end = _parse_name_table(new_ua)
    else:
        name_idx = data.names.index(row_name)

    # Determine secondary_value from effect type
    # Fuel subsidy and condition multipliers use 0.0834, dimension adds use 0.1667
    if effect_short in ('FuelSubsidy',
                        'CompanyBusConditionDecreaseSpeedMultiplier',
                        'CompanyTaxiConditionDecreaseSpeedMultiplier',
                        'CompanyTruckConditionDecreaseSpeedMultiplier'):
        secondary = 0.0834
    else:
        secondary = 0.166667

    row = PolicyRow(
        row_name=row_name,
        row_name_idx=name_idx,
        row_name_instance=0,
        display_name=display_name,
        cost=cost,
        secondary_value=secondary,
        flag=1,
        effect_type=effect_short,
        effect_type_idx=effect_idx,
        effect_value=effect_value,
        is_new=True,
    )
    data.rows.append(row)
    return row


def remove_new_rows(data: PoliciesData) -> None:
    """Remove all mod-added rows (is_new=True), keeping vanilla rows."""
    data.rows = [r for r in data.rows if not r.is_new]


def round_trip_test(ua: bytes, ue: bytes) -> bool:
    """Verify that parse → serialize reproduces the original .uexp bytes."""
    try:
        data = parse_policies(ua, ue)
        rebuilt = serialize_uexp(data)
        return rebuilt == ue
    except Exception:
        return False
