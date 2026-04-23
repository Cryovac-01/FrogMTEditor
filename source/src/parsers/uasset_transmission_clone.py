"""
UAsset cloning for MTTransmissionDataAsset files.

Reuses the core name-table / offset-patching logic from uasset_clone,
but applies transmission-specific name replacement rules (no sound paths,
no torque curves — just asset name and Default__/Class refs).
"""
import os
import struct
import uuid
from typing import Optional

from parsers.uasset_clone import (
    _build_name_entry,
    _cityhash_lite,
    _parse_name_table,
    _read_fstring,
    _write_fstring,
    verify_clone,
)


def clone_transmission_uasset(
    template_path: str,
    new_name: str,
    output_path: str,
) -> bool:
    """Clone a transmission .uasset with a new asset name.

    Replaces all occurrences of the template asset name in the folder path
    and name table, updates header offsets, and generates a fresh GUID.

    Args:
        template_path: Path to the template .uasset
        new_name: New asset name (e.g. 'Truck_6Speed_Stage2')
        output_path: Where to write the cloned .uasset

    Returns:
        True on success.
    """
    with open(template_path, 'rb') as f:
        data = f.read()

    # ── Parse template ──
    fixed_header = data[:28]
    old_total_size = struct.unpack_from('<i', data, 28)[0]

    # FolderName at offset 32
    folder_text, folder_bytes = _read_fstring(data, 32)
    folder_end = 32 + folder_bytes

    # Extract old asset name from folder path
    # e.g. "/Game/Cars/Parts/Transmission/Truck_6Speed" → "Truck_6Speed"
    old_name = folder_text.rsplit('/', 1)[-1]
    base_path = folder_text.rsplit('/', 1)[0]

    # Header fields: from folder_end to NameOffset
    name_count = struct.unpack_from('<i', data, folder_end + 4)[0]
    name_offset = struct.unpack_from('<i', data, folder_end + 8)[0]

    header_fields = bytearray(data[folder_end:name_offset])

    # ── Parse name table ──
    name_entries, name_table_size = _parse_name_table(data, name_offset, name_count)
    rest_start = name_offset + name_table_size
    rest_data = data[rest_start:]

    # ── Replace asset name in name entries ──
    for entry in name_entries:
        text = entry['text']
        if text == old_name:
            entry['text'] = new_name
            entry['hash'] = _cityhash_lite(new_name)
        elif old_name in text:
            new_text = text.replace(old_name, new_name)
            entry['text'] = new_text
            entry['hash'] = _cityhash_lite(new_text)

    # ── Rebuild binary ──
    new_folder = f"{base_path}/{new_name}"
    new_folder_bytes = _write_fstring(new_folder)

    new_name_table = b''
    for entry in name_entries:
        new_name_table += _build_name_entry(entry['text'], entry['hash'])

    # Calculate deltas
    folder_delta = len(new_folder_bytes) - folder_bytes
    name_table_delta = len(new_name_table) - name_table_size
    total_delta = folder_delta + name_table_delta

    # Save original export table positions BEFORE modifying header_fields
    orig_export_count = struct.unpack_from('<i', header_fields, 28)[0]
    orig_export_offset = struct.unpack_from('<i', header_fields, 32)[0]
    orig_depends_offset = struct.unpack_from('<i', header_fields, 44)[0]

    # Update NameOffset
    new_name_offset = name_offset + folder_delta
    struct.pack_into('<i', header_fields, 8, new_name_offset)

    # Bump ALL post-name-table offset fields by total_delta
    old_serial_size = 0
    eo_tmp = struct.unpack_from('<i', header_fields, 32)[0]
    if 0 < eo_tmp < len(data):
        old_serial_size = struct.unpack_from('<q', data, eo_tmp + 28)[0]
    upper_bound = old_total_size + max(old_serial_size, 0)
    for byte_off in range(0, len(header_fields) - 3, 4):
        val = struct.unpack_from('<i', header_fields, byte_off)[0]
        if rest_start <= val <= upper_bound:
            struct.pack_into('<i', header_fields, byte_off, val + total_delta)

    # Randomize Package GUID
    header_fields[64:80] = uuid.uuid4().bytes

    new_total_size = old_total_size + total_delta

    # ── Patch SerialOffset in export table ──
    if total_delta != 0 and orig_export_count > 0 and orig_export_offset > 0:
        rest_data = bytearray(rest_data)
        if orig_depends_offset > orig_export_offset and orig_export_count > 0:
            entry_size = (orig_depends_offset - orig_export_offset) // orig_export_count
        else:
            entry_size = 96
        for i in range(orig_export_count):
            serial_off_pos = (orig_export_offset - rest_start) + i * entry_size + 36
            if 0 <= serial_off_pos < len(rest_data) - 7:
                old_serial = struct.unpack_from('<q', rest_data, serial_off_pos)[0]
                struct.pack_into('<q', rest_data, serial_off_pos, old_serial + total_delta)
        rest_data = bytes(rest_data)

    # ── Assemble ──
    result = bytearray()
    result += fixed_header
    result += struct.pack('<i', new_total_size)
    result += new_folder_bytes
    result += header_fields
    result += new_name_table
    result += rest_data

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'wb') as f:
        f.write(result)

    return True


def update_serial_size(uasset_path: str, new_uexp_size: int) -> bool:
    """Update the SerialSize field in the export table to match a new .uexp size.

    SerialSize = uexp_size - 4 (the 4-byte footer is not counted).

    Args:
        uasset_path: Path to the .uasset file to modify in-place.
        new_uexp_size: Size of the corresponding .uexp file in bytes.

    Returns:
        True on success.
    """
    with open(uasset_path, 'rb') as f:
        data = bytearray(f.read())

    folder_text, folder_bytes = _read_fstring(data, 32)
    folder_end = 32 + folder_bytes

    export_offset = struct.unpack_from('<i', data, folder_end + 32)[0]
    if export_offset <= 0 or export_offset + 36 + 8 > len(data):
        return False

    new_serial_size = new_uexp_size - 4
    struct.pack_into('<q', data, export_offset + 28, new_serial_size)

    with open(uasset_path, 'wb') as f:
        f.write(data)

    return True
