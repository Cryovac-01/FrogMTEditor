"""
Engines.uasset name-table appender.

Appends a new FName entry (row key) to the name table of the Engines DataTable
.uasset file, then fixes up all affected header offsets and TotalHeaderSize.

Reuses helpers from uasset_clone.py — the binary layout is identical:
  fixed_header (28 bytes)
  TotalHeaderSize (int32 @ offset 28)
  FolderName FString (@ offset 32)
  header_fields: PackageFlags@0, NameCount@4, NameOffset@8, ...
  name_table
  rest (imports, exports, depends, preload deps, ...)
"""
import struct
from parsers.uasset_clone import (
    _read_fstring,
    _parse_name_table,
    _build_name_entry,
    _cityhash_lite,
)


def get_fname_index(uasset_data: bytes, name: str) -> int:
    """Return the 0-based FName index for *name* in the Engines.uasset name table.

    Comparison is case-insensitive.  Returns -1 if not found.
    """
    data = uasset_data
    _folder_text, folder_bytes = _read_fstring(data, 32)
    folder_end = 32 + folder_bytes
    name_count = struct.unpack_from('<i', data, folder_end + 4)[0]
    name_offset = struct.unpack_from('<i', data, folder_end + 8)[0]
    entries, _ = _parse_name_table(data, name_offset, name_count)
    needle = name.lower()
    for i, entry in enumerate(entries):
        if entry['text'].lower() == needle:
            return i
    return -1


def add_row_key(uasset_data: bytes, row_key: str) -> tuple:
    """Append a FName entry for row_key at the end of the name table.

    Args:
        uasset_data: Raw bytes of the Engines.uasset file
        row_key:     New engine name to register (e.g. 'myCustomEngine')

    Returns:
        (updated_bytes, new_fname_index)
        where new_fname_index is the 0-based index to use in FName fields
        (= old NameCount, since we append at the end)
    """
    data = uasset_data

    # ── Parse header ──
    fixed_header = data[:28]
    old_total_size = struct.unpack_from('<i', data, 28)[0]

    # FolderName @ offset 32
    _folder_text, folder_bytes = _read_fstring(data, 32)
    folder_end = 32 + folder_bytes

    # header_fields layout (offsets from folder_end):
    #   0: PackageFlags (uint32)
    #   4: NameCount (int32)
    #   8: NameOffset (int32)
    #  16: field[4] — first offset after name table
    #  32: field[8] — export offset
    #  40: field[10] — import offset
    #  44: field[11] — depends offset
    #  88: field[22] — GenerationNameCount

    name_count = struct.unpack_from('<i', data, folder_end + 4)[0]
    name_offset = struct.unpack_from('<i', data, folder_end + 8)[0]

    # Copy header_fields as mutable
    header_fields = bytearray(data[folder_end: name_offset])

    # ── Parse + rebuild name table ──
    name_entries, name_table_size = _parse_name_table(data, name_offset, name_count)
    rest_start = name_offset + name_table_size
    rest_data = data[rest_start:]

    # New entry goes at the end; its index = old name_count (0-based)
    new_fname_index = name_count

    # Build new name table: existing entries + short name + full path
    new_name_table = b''
    for entry in name_entries:
        new_name_table += _build_name_entry(entry['text'], entry['hash'])
    new_name_table += _build_name_entry(row_key, _cityhash_lite(row_key))
    full_path = f'/Game/Cars/Parts/Engine/{row_key}'
    new_name_table += _build_name_entry(full_path, _cityhash_lite(full_path))
    path_fname_index = name_count + 1  # index of the full path entry

    # ── Update header fields ──
    name_table_delta = len(new_name_table) - name_table_size

    # Increment NameCount (+2: short name + full path)
    struct.pack_into('<i', header_fields, 4, name_count + 2)

    # Bump ALL post-name-table offset fields by name_table_delta.
    # Includes offsets within the file AND BulkDataStartOffset beyond file end.
    old_serial_size = 0
    eo_tmp = struct.unpack_from('<i', header_fields, 32)[0]
    if eo_tmp > 0 and eo_tmp < len(data):
        old_serial_size = struct.unpack_from('<q', data, eo_tmp + 28)[0]
    upper_bound = old_total_size + max(old_serial_size, 0)
    for byte_off in range(0, len(header_fields) - 3, 4):
        val = struct.unpack_from('<i', header_fields, byte_off)[0]
        if rest_start <= val <= upper_bound:
            struct.pack_into('<i', header_fields, byte_off, val + name_table_delta)

    # Sync GenerationNameCount (field 22, byte offset 88) if it mirrors NameCount
    gen_off = 22 * 4
    if gen_off + 4 <= len(header_fields):
        old_gen = struct.unpack_from('<i', header_fields, gen_off)[0]
        if old_gen == name_count:
            struct.pack_into('<i', header_fields, gen_off, name_count + 2)

    # ── New TotalHeaderSize ──
    new_total_size = old_total_size + name_table_delta

    # ── Patch SerialOffset in export table ──
    # Export entries are in rest_data. SerialOffset (int64 at byte 36 of each
    # export entry) must track TotalHeaderSize changes.
    orig_export_count = struct.unpack_from('<i', header_fields, 28)[0]
    orig_export_offset = struct.unpack_from('<i', data, folder_end + 32)[0]  # use ORIGINAL
    orig_depends_offset = struct.unpack_from('<i', data, folder_end + 44)[0]
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

    # ── Assemble ──
    result = bytearray()
    result += fixed_header
    result += struct.pack('<i', new_total_size)
    result += data[32: 32 + folder_bytes]   # FolderName unchanged
    result += header_fields
    result += new_name_table
    result += rest_data

    return bytes(result), new_fname_index, path_fname_index


def append_names_if_missing(uasset_data: bytes, names: list) -> tuple:
    """Append each given name to the FName table if not already present.

    Used by the Engine Unlock Requirements writer to make sure
    EMTCharacterLevelType enum names (CL_Driver, CL_Bus, ...) the
    user picked are referenceable from the Engines.uexp row tail.
    Mirrors the offset-bumping pattern of add_row_key but allows
    appending an arbitrary list of plain names (no /Game/... full
    paths).

    Args:
        uasset_data: Raw Engines.uasset bytes.
        names:       List of plain names to ensure present.

    Returns:
        (updated_uasset_bytes, name_to_fname_index_map) where the map
        contains an entry for each input name (existing or newly added).
    """
    data = uasset_data

    # Resolve which names are missing
    existing_idx = {n: get_fname_index(data, n) for n in names}
    missing = [n for n, i in existing_idx.items() if i < 0]
    if not missing:
        return data, {n: existing_idx[n] for n in names}

    # ── Parse header (same as add_row_key) ──
    fixed_header = data[:28]
    old_total_size = struct.unpack_from('<i', data, 28)[0]
    _folder_text, folder_bytes = _read_fstring(data, 32)
    folder_end = 32 + folder_bytes
    name_count = struct.unpack_from('<i', data, folder_end + 4)[0]
    name_offset = struct.unpack_from('<i', data, folder_end + 8)[0]
    header_fields = bytearray(data[folder_end: name_offset])
    name_entries, name_table_size = _parse_name_table(data, name_offset, name_count)
    rest_start = name_offset + name_table_size
    rest_data = data[rest_start:]

    # ── Build new name table: existing + each missing name ──
    new_indices = {}
    new_name_table = b''
    for entry in name_entries:
        new_name_table += _build_name_entry(entry['text'], entry['hash'])
    for n in missing:
        new_indices[n] = name_count + len(new_indices)
        new_name_table += _build_name_entry(n, _cityhash_lite(n))

    name_table_delta = len(new_name_table) - name_table_size
    added = len(missing)

    # Bump NameCount and offsets that point past the name table
    struct.pack_into('<i', header_fields, 4, name_count + added)
    old_serial_size = 0
    eo_tmp = struct.unpack_from('<i', header_fields, 32)[0]
    if eo_tmp > 0 and eo_tmp < len(data):
        old_serial_size = struct.unpack_from('<q', data, eo_tmp + 28)[0]
    upper_bound = old_total_size + max(old_serial_size, 0)
    for byte_off in range(0, len(header_fields) - 3, 4):
        val = struct.unpack_from('<i', header_fields, byte_off)[0]
        if rest_start <= val <= upper_bound:
            struct.pack_into('<i', header_fields, byte_off, val + name_table_delta)

    # GenerationNameCount mirror
    gen_off = 22 * 4
    if gen_off + 4 <= len(header_fields):
        old_gen = struct.unpack_from('<i', header_fields, gen_off)[0]
        if old_gen == name_count:
            struct.pack_into('<i', header_fields, gen_off, name_count + added)

    new_total_size = old_total_size + name_table_delta

    # Patch SerialOffset in export entries (same as add_row_key)
    orig_export_count = struct.unpack_from('<i', header_fields, 28)[0]
    orig_export_offset = struct.unpack_from('<i', data, folder_end + 32)[0]
    orig_depends_offset = struct.unpack_from('<i', data, folder_end + 44)[0]
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

    # ── Assemble ──
    result = bytearray()
    result += fixed_header
    result += struct.pack('<i', new_total_size)
    result += data[32: 32 + folder_bytes]
    result += header_fields
    result += new_name_table
    result += rest_data
    new_data = bytes(result)

    # Combine new + existing indices
    out_map = {n: existing_idx[n] for n in names if existing_idx[n] >= 0}
    out_map.update(new_indices)
    return new_data, out_map


def add_engine_import(uasset_data: bytes, engine_name: str,
                      path_fname_idx: int, name_fname_idx: int) -> bytes:
    """Add Package + MHEngineDataAsset import entries for a new engine.

    Each engine needs 2 imports (32 bytes each = 64 total):
      1. Package: ClassPkg="/Script/CoreUObject" Class="Package"
                  Name="/Game/Cars/Parts/Engine/<name>"
      2. Asset:   ClassPkg="/Script/MotorTown" Class="MHEngineDataAsset"
                  Outer=<package_import> Name="<short_name>"

    Also updates:
      - ImportCount (+2)
      - All header offsets past the import insertion point
      - TotalHeaderSize and SerialOffset
      - PreloadDependencies (optionally inserts the asset import as SBC)
      - Export entry SBC count (+1) when inserted
      - PreloadDependencyCount (+1) when inserted

    We intentionally leave DependsMap and CreateBeforeCreateDeps at their
    vanilla shape. The known-good compatibility DataTable does not grow those
    sections when registering many custom engines, and our full rebuild became
    unstable once those lists expanded aggressively.

    Export entry layout (96 bytes, no PackageGUID, has GeneratePublicHash):
      byte 72: FirstExportDependency
      byte 76: SBS count (SerializationBeforeSerializationDeps)
      byte 80: CBS count (CreateBeforeSerializationDeps)
      byte 84: SBC count (SerializationBeforeCreateDeps)  ← engine assets
      byte 88: CBC count (CreateBeforeCreateDeps)          ← package imports

    Args:
        uasset_data:    Current Engines.uasset bytes
        engine_name:    Short engine name (for logging only)
        path_fname_idx: FName index of "/Game/Cars/Parts/Engine/<name>"
        name_fname_idx: FName index of "<name>" (short name)

    Returns:
        Updated Engines.uasset bytes
    """
    data = bytearray(uasset_data)
    _, folder_bytes = _read_fstring(bytes(data), 32)
    folder_end = 32 + folder_bytes

    # Read key header fields
    import_count  = struct.unpack_from('<i', data, folder_end + 36)[0]
    import_offset = struct.unpack_from('<i', data, folder_end + 40)[0]
    export_offset = struct.unpack_from('<i', data, folder_end + 32)[0]
    old_total_size = struct.unpack_from('<i', data, 28)[0]
    name_offset   = struct.unpack_from('<i', data, folder_end + 8)[0]

    # Find FName indices for known names
    name_count = struct.unpack_from('<i', data, folder_end + 4)[0]
    entries, _ = _parse_name_table(bytes(data), name_offset, name_count)
    name_lookup = {e['text']: i for i, e in enumerate(entries)}

    coreuobject_idx = name_lookup.get('/Script/CoreUObject', 92)
    motortown_idx   = name_lookup.get('/Script/MotorTown', 95)
    package_idx     = name_lookup.get('Package', 117)
    mhengine_idx    = name_lookup.get('MHEngineDataAsset', 116)

    # New import indices (1-based negative)
    new_pkg_import_idx   = -(import_count + 1)  # Package import
    new_asset_import_idx = -(import_count + 2)  # MHEngineDataAsset import

    pkg_import = struct.pack('<iiiiiiii',
        coreuobject_idx, 0,   # ClassPackage FName
        package_idx, 0,       # ClassName FName
        0,                    # OuterIndex
        path_fname_idx, 0,    # ObjectName FName
        0)                    # bImportOptional

    asset_import = struct.pack('<iiiiiiii',
        motortown_idx, 0,     # ClassPackage FName
        mhengine_idx, 0,      # ClassName FName
        new_pkg_import_idx,   # OuterIndex → Package import
        name_fname_idx, 0,    # ObjectName FName
        0)                    # bImportOptional

    new_imports  = pkg_import + asset_import  # 64 bytes
    import_delta = 64

    # ── 1. Insert imports at end of import table ──────────────────────────────
    import_end = import_offset + import_count * 32
    data = bytearray(bytes(data[:import_end]) + new_imports + bytes(data[import_end:]))
    struct.pack_into('<i', data, folder_end + 36, import_count + 2)

    # Bump all header offsets past import_end
    old_serial_size = 0
    if export_offset > 0 and export_offset < len(uasset_data):
        old_serial_size = struct.unpack_from('<q', uasset_data, export_offset + 28)[0]
    upper_bound = old_total_size + max(old_serial_size, 0)
    hf_start = folder_end
    hf_end   = name_offset
    for abs_off in range(hf_start, hf_end - 3, 4):
        val = struct.unpack_from('<i', data, abs_off)[0]
        if import_end <= val <= upper_bound:
            struct.pack_into('<i', data, abs_off, val + import_delta)

    struct.pack_into('<i', data, 28, old_total_size + import_delta)

    # Update SerialOffset in export entry (+import_delta)
    new_eo = struct.unpack_from('<i', data, folder_end + 32)[0]
    so_pos = new_eo + 36
    if so_pos + 8 <= len(data):
        struct.pack_into('<q', data, so_pos,
                         struct.unpack_from('<q', data, so_pos)[0] + import_delta)

    # ── 2. Update PreloadDependencies ────────────────────────────────────────
    # Read current (already-bumped) PreloadDep state
    pdo = struct.unpack_from('<i', data, folder_end + 160)[0]  # PreloadDepOffset
    pdc = struct.unpack_from('<i', data, folder_end + 156)[0]  # PreloadDepCount

    # Export entry dep counts (96-byte entry, no PackageGUID layout)
    sbs = struct.unpack_from('<i', data, new_eo + 76)[0]
    cbs = struct.unpack_from('<i', data, new_eo + 80)[0]
    sbc = struct.unpack_from('<i', data, new_eo + 84)[0]
    # Insert MHEngineDataAsset import as SBC entry (before existing CBC entries).
    # Every registered template row needs its engine asset import preloaded; capping
    # this list leaves later DataTable rows present but unresolved by the game.
    sbc_insert_abs = pdo + (sbs + cbs + sbc) * 4
    data = bytearray(bytes(data[:sbc_insert_abs])
                     + struct.pack('<i', new_asset_import_idx)
                     + bytes(data[sbc_insert_abs:]))
    struct.pack_into('<i', data, new_eo + 84, sbc + 1)
    cur_total = struct.unpack_from('<i', data, 28)[0] + 4
    struct.pack_into('<i', data, 28, cur_total)
    so_pos = new_eo + 36
    struct.pack_into('<q', data, so_pos,
                     struct.unpack_from('<q', data, so_pos)[0] + 4)
    struct.pack_into('<i', data, folder_end + 156, pdc + 1)

    return bytes(data)

