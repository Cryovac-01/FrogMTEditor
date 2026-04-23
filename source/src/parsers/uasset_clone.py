"""
UAsset cloning with name patching.
Takes a template .uasset and creates a new one with a different asset name,
properly updating the folder name, name table entries, and all header offsets.

Binary layout of a Motor Town .uasset (UE5, LegacyFileVersion=-8):
  [fixed_header: 28 bytes]
  [TotalHeaderSize: int32]
  [FolderName: FString (int32 len + chars + null)]
  [header_fields: ~180 bytes of int32s including PackageFlags, NameCount,
   NameOffset, various offsets, GUID, Generations]
  [name_table: variable-size name entries]
  [rest: import table, export table, depends, preload deps, etc.]
"""
import struct
import os
from typing import Optional

_SOUND_SKIP_DIRS = frozenset({'Backfire', 'Intake', 'jake'})
_SOUND_CUE_BY_DIR = {
    'V8': 'SC_V8Engine',
    'v12': 'SC_V12Engine',
    'Electric': 'SC_ElectricMotor',
}


def _read_fstring(data: bytes, offset: int) -> tuple:
    """Read a UE FString (int32 length + chars + null). Returns (string, bytes_consumed)."""
    slen = struct.unpack_from('<i', data, offset)[0]
    if slen <= 0:
        return ("", 4)
    text = data[offset + 4:offset + 4 + slen - 1].decode('ascii', errors='replace')
    return (text, 4 + slen)


def _write_fstring(text: str) -> bytes:
    """Write a UE FString (int32 length + chars + null)."""
    encoded = text.encode('ascii') + b'\x00'
    return struct.pack('<i', len(encoded)) + encoded


def _parse_name_table(data: bytes, offset: int, count: int) -> list:
    """Parse the name table. Returns list of (text, hash_bytes, total_entry_size)."""
    entries = []
    off = offset
    for _ in range(count):
        slen = struct.unpack_from('<i', data, off)[0]
        off += 4
        if slen > 0 and slen < 1000:
            text = data[off:off + slen - 1].decode('ascii', errors='replace')
            off += slen
            hash_bytes = data[off:off + 4]
            off += 4
            entries.append({
                'text': text,
                'hash': hash_bytes,
                'size': 4 + slen + 4,  # len_field + string + hash
            })
        elif slen < 0:
            # UTF-16 string (negative length = UTF-16 char count)
            char_count = -slen
            raw = data[off:off + char_count * 2]
            text = raw.decode('utf-16-le', errors='replace').rstrip('\x00')
            off += char_count * 2
            hash_bytes = data[off:off + 4]
            off += 4
            entries.append({
                'text': text,
                'hash': hash_bytes,
                'size': 4 + char_count * 2 + 4,
            })
        else:
            entries.append({
                'text': '',
                'hash': b'\x00\x00\x00\x00',
                'size': 4 + 4,
            })
    return entries, off - offset


def _build_name_entry(text: str, hash_bytes: bytes) -> bytes:
    """Build a single name table entry."""
    encoded = text.encode('ascii') + b'\x00'
    return struct.pack('<i', len(encoded)) + encoded + hash_bytes


def _parse_engine_sound_ref(text: str) -> Optional[dict]:
    """Return parsed info for an engine sound object path, or None."""
    marker = '/Cars/Parts/Engine/Sound/'
    if marker not in text:
        return None

    _prefix, suffix = text.split(marker, 1)
    parts = suffix.split('/')
    if not parts:
        return None

    head = parts[0]
    if head in _SOUND_SKIP_DIRS:
        return None

    object_name = None
    if head == 'Bike':
        if len(parts) < 2:
            return None
        object_name = parts[1]
    elif parts:
        object_name = parts[-1]

    return {
        'head': head,
        'parts': parts,
        'object_name': object_name,
    }


def _rewrite_engine_sound_path(text: str, new_sound_dir: str) -> Optional[str]:
    """Rewrite an engine sound path while preserving category-specific layout."""
    info = _parse_engine_sound_ref(text)
    if not info:
        return None

    marker = '/Cars/Parts/Engine/Sound/'
    prefix, _suffix = text.split(marker, 1)
    parts = list(info['parts'])
    head = info['head']

    if head == 'Bike':
        if len(parts) < 2 or parts[1] == new_sound_dir:
            return None
        parts[1] = new_sound_dir
        return prefix + marker + '/'.join(parts)

    if head == new_sound_dir:
        return None

    parts[0] = new_sound_dir
    if len(parts) >= 2 and parts[1].startswith('SC_') and new_sound_dir in _SOUND_CUE_BY_DIR:
        parts[1] = _SOUND_CUE_BY_DIR[new_sound_dir]
    return prefix + marker + '/'.join(parts)


def _should_rewrite_sound_object_name(head: str, old_name: str, new_name: str) -> bool:
    """Return True when a changed path also needs its standalone cue FName updated."""
    if not old_name or not new_name or old_name == new_name:
        return False
    if head == 'Bike':
        return True
    return old_name.startswith('SC_') and new_name.startswith('SC_')


def _rewrite_sound_object_names(name_entries: list, replacements: dict[str, str]) -> None:
    """Apply exact sound cue FName replacements after path rewrites."""
    if not replacements:
        return

    for entry in name_entries:
        text = entry['text']
        new_text = replacements.get(text)
        if not new_text or new_text == text:
            continue
        entry['text'] = new_text
        entry['hash'] = _cityhash_lite(new_text)


def _cityhash_lite(text: str) -> bytes:
    """Compute the correct UE5 FName hash for a name table entry.

    The hash combines two CRC algorithms:
      Lower 16 bits: Strihash_DEPRECATED (uppercase, CRC-32 normal polynomial)
      Upper 16 bits: StrCrc32 (case-preserving, CRC-32 reflected polynomial)
    Stored as big-endian uint32.

    Algorithm reverse-engineered from UAssetAPI CRCGenerator.cs.
    """
    # CRC-32 normal polynomial 0x04C11DB7
    h1 = 0
    for ch in text:
        b = ord(ch.upper() if 'a' <= ch <= 'z' else ch) & 0xFF
        h1 = ((h1 >> 8) & 0x00FFFFFF) ^ _CRC_DEPRECATED[(h1 ^ b) & 0xFF]

    # CRC-32 reflected polynomial 0xEDB88320
    crc = 0xFFFFFFFF
    for ch in text:
        v = ord(ch)
        for _ in range(4):
            crc = (crc >> 8) ^ _CRC_REFLECTED[(crc ^ (v & 0xFF)) & 0xFF]
            v >>= 8
    h2 = (~crc) & 0xFFFFFFFF

    combined = (h1 & 0xFFFF) | ((h2 & 0xFFFF) << 16)
    return struct.pack('<I', combined)


# Pre-computed CRC tables
_CRC_DEPRECATED = [0] * 256
for _i in range(256):
    _c = _i << 24
    for _ in range(8):
        _c = ((_c << 1) ^ 0x04C11DB7) & 0xFFFFFFFF if _c & 0x80000000 else (_c << 1) & 0xFFFFFFFF
    _CRC_DEPRECATED[_i] = _c

_CRC_REFLECTED = [0] * 256
for _i in range(256):
    _c = _i
    for _ in range(8):
        _c = (_c >> 1) ^ 0xEDB88320 if _c & 1 else _c >> 1
    _CRC_REFLECTED[_i] = _c


def clone_uasset(template_path: str, new_name: str, output_path: str,
                 torque_curve_name: Optional[str] = None,
                 sound_dir: Optional[str] = None) -> bool:
    """Clone a .uasset file with a new asset name.

    Args:
        template_path: Path to the template .uasset file
        new_name: New asset name (e.g., 'myCustomEngine')
        output_path: Where to write the new .uasset
        torque_curve_name: Optional new torque curve name to reference
        sound_dir: Optional engine-specific sound directory to use
                   (e.g., 'rb26'). If None, the template's sound dir is kept.

    Returns:
        True if successful
    """
    with open(template_path, 'rb') as f:
        data = f.read()

    # ── Parse template ──
    # Fixed header: 28 bytes
    fixed_header = data[:28]

    # TotalHeaderSize at offset 28
    old_total_size = struct.unpack_from('<i', data, 28)[0]

    # FolderName at offset 32
    folder_text, folder_bytes = _read_fstring(data, 32)
    folder_end = 32 + folder_bytes

    # Extract the old asset name from the folder path
    # e.g., "/Game/Cars/Parts/Engine/lexusV10" -> "lexusV10"
    old_name = folder_text.rsplit('/', 1)[-1]
    base_path = folder_text.rsplit('/', 1)[0]  # "/Game/Cars/Parts/Engine"
    internal_old_name = old_name
    try:
        from parsers.uasset import parse_uasset
        parsed_template = parse_uasset(template_path)
        parsed_name = getattr(parsed_template, 'asset_name', '')
        if parsed_name:
            internal_old_name = parsed_name
    except Exception:
        pass

    # Header fields: from folder_end to NameOffset
    # We need to find NameCount and NameOffset
    # PackageFlags is at folder_end, NameCount at folder_end+4, NameOffset at folder_end+8
    pkg_flags = struct.unpack_from('<I', data, folder_end)[0]
    name_count = struct.unpack_from('<i', data, folder_end + 4)[0]
    name_offset = struct.unpack_from('<i', data, folder_end + 8)[0]

    # The header fields section: from folder_end to name_offset
    header_fields = bytearray(data[folder_end:name_offset])
    header_fields_size = name_offset - folder_end

    # ── Parse name table ──
    name_entries, name_table_size = _parse_name_table(data, name_offset, name_count)
    rest_start = name_offset + name_table_size
    rest_data = data[rest_start:]  # Everything after name table (imports, exports, etc.)

    # ── Replace names ──
    new_folder = f"{base_path}/{new_name}"
    old_names = sorted({name for name in (old_name, internal_old_name) if name}, key=len, reverse=True)

    # Pass 1: replace engine name in all entries EXCEPT sound paths.
    # Sound paths like /Game/Cars/Parts/Engine/Sound/rb26/SC_V8Engine must
    # NOT have 'rb26' replaced with the new engine name — they reference a
    # separate SoundCue asset that lives under a fixed directory.
    for entry in name_entries:
        text = entry['text']
        if '/Cars/Parts/Engine/Sound/' in text:
            continue  # handled in pass 2
        if text in old_names:
            entry['text'] = new_name
            entry['hash'] = _cityhash_lite(new_name)
        else:
            new_text = text
            for prior_name in old_names:
                if prior_name in new_text:
                    new_text = new_text.replace(prior_name, new_name)
            if new_text != text:
                entry['text'] = new_text
                entry['hash'] = _cityhash_lite(new_text)

    # Pass 2: handle sound path entries explicitly.
    # Keep the original sound dir unless `sound_dir` is provided.
    sound_object_replacements = {}
    for entry in name_entries:
        text = entry['text']
        if '/Cars/Parts/Engine/Sound/' not in text:
            continue
        if not sound_dir:
            continue
        old_info = _parse_engine_sound_ref(text)
        new_text = _rewrite_engine_sound_path(text, sound_dir)
        if new_text and new_text != text:
            new_info = _parse_engine_sound_ref(new_text)
            if old_info and new_info:
                old_name = old_info.get('object_name')
                new_name = new_info.get('object_name')
                if _should_rewrite_sound_object_name(old_info['head'], old_name, new_name):
                    sound_object_replacements[old_name] = new_name
            entry['text'] = new_text
            entry['hash'] = _cityhash_lite(new_text)
    _rewrite_sound_object_names(name_entries, sound_object_replacements)

    # Optionally update torque curve reference
    if torque_curve_name:
        for entry in name_entries:
            if entry['text'].startswith('TorqueCurve_') and '/' not in entry['text']:
                entry['text'] = torque_curve_name
                entry['hash'] = _cityhash_lite(torque_curve_name)
            elif '/TorqueCurve/' in entry['text']:
                old_tc = entry['text'].rsplit('/', 1)[-1]
                new_text = entry['text'].replace(old_tc, torque_curve_name)
                entry['text'] = new_text
                entry['hash'] = _cityhash_lite(new_text)

    # ── Rebuild binary ──
    # New folder name
    new_folder_bytes = _write_fstring(new_folder)

    # New name table
    new_name_table = b''
    for entry in name_entries:
        new_name_table += _build_name_entry(entry['text'], entry['hash'])

    # Calculate offset changes
    old_folder_bytes_size = folder_bytes  # includes length field
    new_folder_bytes_size = len(new_folder_bytes)
    folder_delta = new_folder_bytes_size - old_folder_bytes_size

    old_name_table_total = name_table_size
    new_name_table_total = len(new_name_table)
    name_table_delta = new_name_table_total - old_name_table_total

    total_delta = folder_delta + name_table_delta

    # Save original export table positions BEFORE modifying header_fields
    orig_export_count = struct.unpack_from('<i', header_fields, 28)[0]
    orig_export_offset = struct.unpack_from('<i', header_fields, 32)[0]
    orig_depends_offset = struct.unpack_from('<i', header_fields, 44)[0]

    # Update NameOffset in header fields (field index 2, byte offset 8)
    new_name_offset = name_offset + folder_delta
    struct.pack_into('<i', header_fields, 8, new_name_offset)

    # Bump ALL post-name-table offset fields by total_delta.
    # Includes offsets within the file (rest_start..old_total_size) AND
    # BulkDataStartOffset which points past the file (old_total_size..total+serial).
    old_serial_size = 0
    eo_tmp = struct.unpack_from('<i', header_fields, 32)[0]
    if eo_tmp > 0 and eo_tmp < len(data):
        old_serial_size = struct.unpack_from('<q', data, eo_tmp + 28)[0]
    upper_bound = old_total_size + max(old_serial_size, 0)
    for byte_off in range(0, len(header_fields) - 3, 4):
        val = struct.unpack_from('<i', header_fields, byte_off)[0]
        if rest_start <= val <= upper_bound:
            struct.pack_into('<i', header_fields, byte_off, val + total_delta)

    # Update generation name count (field 22 from PackageFlags, byte offset 88)
    # This mirrors NameCount — only if we changed it
    gen_name_off = 22 * 4
    if gen_name_off + 4 <= len(header_fields):
        old_gen = struct.unpack_from('<i', header_fields, gen_name_off)[0]
        if old_gen == name_count:
            struct.pack_into('<i', header_fields, gen_name_off, name_count)

    # Randomize Package GUID (fields 16-19, bytes 64-79) to avoid conflicts
    # when multiple cloned engines coexist — each needs a unique GUID.
    import uuid as _uuid
    guid_bytes = _uuid.uuid4().bytes
    header_fields[64:80] = guid_bytes

    # New TotalHeaderSize
    new_total_size = old_total_size + total_delta

    # ── Patch SerialOffset in export table ──────────────────────────────────
    # Each export entry has SerialOffset (int64 at byte 36 within the entry)
    # that must track TotalHeaderSize changes. For separated .uasset/.uexp
    # files, SerialOffset = TotalHeaderSize + offset_within_uexp.
    # Use ORIGINAL offsets (saved before header_fields modification).
    if total_delta != 0 and orig_export_count > 0 and orig_export_offset > 0:
        rest_data = bytearray(rest_data)
        if orig_depends_offset > orig_export_offset and orig_export_count > 0:
            entry_size = (orig_depends_offset - orig_export_offset) // orig_export_count
        else:
            entry_size = 96
        for i in range(orig_export_count):
            serial_off_pos = (orig_export_offset - rest_start) + i * entry_size + 36
            if 0 <= serial_off_pos and serial_off_pos + 8 <= len(rest_data):
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

    # Write output
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'wb') as f:
        f.write(result)

    return True


def update_sound_in_uasset(uasset_path: str, new_sound_dir: str) -> bool:
    """Update the engine-specific sound directory in an existing .uasset name table.

    Finds name table entries whose text matches the pattern
    /Cars/Parts/Engine/Sound/<dir>/<cue> (where <dir> is not a category dir
    like Bike or Electric) and replaces <dir> with new_sound_dir.

    Rebuilds TotalHeaderSize and all post-name-table offsets to account for
    any size change (different-length sound dir names).

    Returns True if successful.
    """
    with open(uasset_path, 'rb') as f:
        data = f.read()

    fixed_header = data[:28]
    old_total_size = struct.unpack_from('<i', data, 28)[0]

    folder_text, folder_bytes = _read_fstring(data, 32)
    folder_end = 32 + folder_bytes

    name_count = struct.unpack_from('<i', data, folder_end + 4)[0]
    name_offset = struct.unpack_from('<i', data, folder_end + 8)[0]

    header_fields = bytearray(data[folder_end:name_offset])
    name_entries, name_table_size = _parse_name_table(data, name_offset, name_count)
    rest_start = name_offset + name_table_size
    rest_data = data[rest_start:]

    changed = False
    sound_object_replacements = {}
    for entry in name_entries:
        text = entry['text']
        old_info = _parse_engine_sound_ref(text)
        new_text = _rewrite_engine_sound_path(text, new_sound_dir)
        if not new_text or new_text == text:
            continue
        new_info = _parse_engine_sound_ref(new_text)
        if old_info and new_info:
            old_name = old_info.get('object_name')
            new_name = new_info.get('object_name')
            if _should_rewrite_sound_object_name(old_info['head'], old_name, new_name):
                sound_object_replacements[old_name] = new_name
        entry['text'] = new_text
        entry['hash'] = _cityhash_lite(new_text)
        changed = True

    _rewrite_sound_object_names(name_entries, sound_object_replacements)

    if not changed:
        return True  # Nothing to update

    # Rebuild name table
    new_name_table = b''.join(_build_name_entry(e['text'], e['hash']) for e in name_entries)
    name_table_delta = len(new_name_table) - name_table_size

    # Save original export positions BEFORE modifying header_fields
    orig_export_count = struct.unpack_from('<i', header_fields, 28)[0]
    orig_export_offset = struct.unpack_from('<i', header_fields, 32)[0]
    orig_depends_offset = struct.unpack_from('<i', header_fields, 44)[0]

    if name_table_delta != 0:
        # Bump ALL post-name-table offset fields (including BulkDataStartOffset)
        old_serial_size = 0
        eo_tmp = struct.unpack_from('<i', header_fields, 32)[0]
        if eo_tmp > 0 and eo_tmp < len(data):
            old_serial_size = struct.unpack_from('<q', data, eo_tmp + 28)[0]
        upper_bound = old_total_size + max(old_serial_size, 0)
        for byte_off in range(0, len(header_fields) - 3, 4):
            val = struct.unpack_from('<i', header_fields, byte_off)[0]
            if rest_start <= val <= upper_bound:
                struct.pack_into('<i', header_fields, byte_off, val + name_table_delta)

    new_total_size = old_total_size + name_table_delta

    # Patch SerialOffset in export table (use ORIGINAL offsets)
    if name_table_delta != 0 and orig_export_count > 0 and orig_export_offset > 0:
        rest_data = bytearray(rest_data)
        if orig_depends_offset > orig_export_offset and orig_export_count > 0:
            entry_size = (orig_depends_offset - orig_export_offset) // orig_export_count
        else:
            entry_size = 96
        for i in range(orig_export_count):
            serial_off_pos = (orig_export_offset - rest_start) + i * entry_size + 36
            if 0 <= serial_off_pos and serial_off_pos + 8 <= len(rest_data):
                old_serial = struct.unpack_from('<q', rest_data, serial_off_pos)[0]
                struct.pack_into('<q', rest_data, serial_off_pos, old_serial + name_table_delta)
        rest_data = bytes(rest_data)

    result = bytearray()
    result += fixed_header
    result += struct.pack('<i', new_total_size)
    result += _write_fstring(folder_text)
    result += header_fields
    result += new_name_table
    result += rest_data

    with open(uasset_path, 'wb') as f:
        f.write(result)

    return True


def verify_clone(template_path: str, output_path: str) -> dict:
    """Verify a cloned .uasset has valid structure."""
    with open(output_path, 'rb') as f:
        data = f.read()

    result = {'valid': True, 'errors': [], 'info': {}}

    # Check magic
    tag = struct.unpack_from('<I', data, 0)[0]
    if tag != 0x9E2A83C1:
        result['valid'] = False
        result['errors'].append(f'Bad magic: 0x{tag:08X}')

    # Check TotalHeaderSize matches file size
    total_hdr = struct.unpack_from('<i', data, 28)[0]
    if total_hdr != len(data):
        result['valid'] = False
        result['errors'].append(f'TotalHeaderSize ({total_hdr}) != file size ({len(data)})')

    # Check FolderName is readable
    folder_text, folder_bytes = _read_fstring(data, 32)
    result['info']['folder'] = folder_text
    result['info']['size'] = len(data)

    # Try to parse name table
    folder_end = 32 + folder_bytes
    name_count = struct.unpack_from('<i', data, folder_end + 4)[0]
    name_offset = struct.unpack_from('<i', data, folder_end + 8)[0]
    result['info']['name_count'] = name_count
    result['info']['name_offset'] = name_offset

    try:
        entries, _ = _parse_name_table(data, name_offset, name_count)
        result['info']['names'] = [e['text'] for e in entries]
    except Exception as e:
        result['valid'] = False
        result['errors'].append(f'Name table parse failed: {e}')

    return result


def update_torque_curve_ref(uasset_path: str, new_tc_name: str) -> bool:
    """Update the torque curve reference in an existing engine .uasset file.

    Re-reads the file, patches the name table entries for the torque curve,
    rebuilds the binary, and writes it back. The new torque curve name must
    produce entries of the **same byte length** as the old ones (or offsets
    would need patching). For safety this function rebuilds the full file
    using the same logic as clone_uasset.

    Args:
        uasset_path: Path to the engine .uasset to modify in-place.
        new_tc_name: New torque curve name (e.g. 'TorqueCurve_myEngine').

    Returns:
        True on success.
    """
    import uuid

    with open(uasset_path, 'rb') as f:
        data = f.read()

    # Parse header
    fixed_header = data[:28]
    old_total_size = struct.unpack_from('<i', data, 28)[0]
    folder_text, folder_bytes = _read_fstring(data, 32)
    folder_end = 32 + folder_bytes

    name_count = struct.unpack_from('<i', data, folder_end + 4)[0]
    name_offset = struct.unpack_from('<i', data, folder_end + 8)[0]

    header_fields = bytearray(data[folder_end:name_offset])
    name_entries, name_table_size = _parse_name_table(data, name_offset, name_count)
    rest_start = name_offset + name_table_size
    rest_data = data[rest_start:]

    # Replace torque curve references in name table
    changed = False
    for entry in name_entries:
        text = entry['text']
        if text.startswith('TorqueCurve_') and '/' not in text:
            entry['text'] = new_tc_name
            entry['hash'] = _cityhash_lite(new_tc_name)
            changed = True
        elif '/TorqueCurve/' in text:
            old_tc = text.rsplit('/', 1)[-1]
            new_text = text.replace(old_tc, new_tc_name)
            entry['text'] = new_text
            entry['hash'] = _cityhash_lite(new_text)
            changed = True

    if not changed:
        return False

    # Rebuild binary
    new_folder_bytes = _write_fstring(folder_text)
    new_name_table = b''
    for entry in name_entries:
        new_name_table += _build_name_entry(entry['text'], entry['hash'])

    folder_delta = len(new_folder_bytes) - folder_bytes
    name_table_delta = len(new_name_table) - name_table_size
    total_delta = folder_delta + name_table_delta

    # Save original export table positions
    orig_export_count = struct.unpack_from('<i', header_fields, 28)[0]
    orig_export_offset = struct.unpack_from('<i', header_fields, 32)[0]
    orig_depends_offset = struct.unpack_from('<i', header_fields, 44)[0]

    # Update NameOffset
    new_name_offset = name_offset + folder_delta
    struct.pack_into('<i', header_fields, 8, new_name_offset)

    # Bump all post-name-table offsets
    old_serial_size = 0
    eo_tmp = struct.unpack_from('<i', header_fields, 32)[0]
    if 0 < eo_tmp < len(data):
        old_serial_size = struct.unpack_from('<q', data, eo_tmp + 28)[0]
    upper_bound = old_total_size + max(old_serial_size, 0)
    for byte_off in range(0, len(header_fields) - 3, 4):
        val = struct.unpack_from('<i', header_fields, byte_off)[0]
        if rest_start <= val <= upper_bound:
            struct.pack_into('<i', header_fields, byte_off, val + total_delta)

    # Keep GUID (don't randomize — already set during clone)
    new_total_size = old_total_size + total_delta

    # Patch SerialOffset in export table
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

    # Assemble
    result = bytearray()
    result += fixed_header
    result += struct.pack('<i', new_total_size)
    result += new_folder_bytes
    result += header_fields
    result += new_name_table
    result += rest_data

    with open(uasset_path, 'wb') as f:
        f.write(result)

    return True
