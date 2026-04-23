"""
VehicleParts0.uasset helpers.

VehicleParts0 is the shared non-engine DataTable used for tires and many other
part-shop rows. The .uasset side holds the name table and import table that the
VehicleParts0.uexp rows reference.
"""
import struct
from typing import Any, Dict, List, Optional

from parsers.uasset_clone import _build_name_entry, _cityhash_lite, _parse_name_table, _read_fstring


def parse_name_lookup(uasset_data: bytes) -> tuple[dict[int, str], dict[str, int]]:
    """Return ``(idx_to_name, name_to_idx)`` for the VehicleParts0 name table."""
    _folder_text, folder_bytes = _read_fstring(uasset_data, 32)
    folder_end = 32 + folder_bytes
    name_count = struct.unpack_from('<i', uasset_data, folder_end + 4)[0]
    name_offset = struct.unpack_from('<i', uasset_data, folder_end + 8)[0]
    entries, _ = _parse_name_table(uasset_data, name_offset, name_count)

    idx_to_name = {i: entry['text'] for i, entry in enumerate(entries)}
    name_to_idx = {entry['text']: i for i, entry in enumerate(entries)}
    return idx_to_name, name_to_idx


def get_fname_index(uasset_data: bytes, name: str) -> int:
    """Return the 0-based FName index for *name*, or -1 when absent."""
    _idx_to_name, name_to_idx = parse_name_lookup(uasset_data)
    if name in name_to_idx:
        return name_to_idx[name]

    needle = name.lower()
    for key, idx in name_to_idx.items():
        if key.lower() == needle:
            return idx
    return -1


def get_import_count(uasset_data: bytes) -> int:
    """Return the import-count stored in VehicleParts0.uasset."""
    _folder_text, folder_bytes = _read_fstring(uasset_data, 32)
    folder_end = 32 + folder_bytes
    return struct.unpack_from('<i', uasset_data, folder_end + 36)[0]


def parse_imports(uasset_data: bytes) -> List[Dict[str, Any]]:
    """Parse VehicleParts0 imports into convenient dictionaries."""
    idx_to_name, _ = parse_name_lookup(uasset_data)
    _folder_text, folder_bytes = _read_fstring(uasset_data, 32)
    folder_end = 32 + folder_bytes

    import_count = struct.unpack_from('<i', uasset_data, folder_end + 36)[0]
    import_offset = struct.unpack_from('<i', uasset_data, folder_end + 40)[0]

    imports: List[Dict[str, Any]] = []
    for i in range(import_count):
        off = import_offset + i * 32
        class_pkg_idx, _class_pkg_num, class_name_idx, _class_name_num, outer_index, object_name_idx, _obj_num, optional = (
            struct.unpack_from('<iiiiiiii', uasset_data, off)
        )
        imports.append({
            'import_index': i + 1,
            'negative_ref': -(i + 1),
            'class_package_idx': class_pkg_idx,
            'class_package': idx_to_name.get(class_pkg_idx, ''),
            'class_name_idx': class_name_idx,
            'class_name': idx_to_name.get(class_name_idx, ''),
            'outer_index': outer_index,
            'object_name_idx': object_name_idx,
            'object_name': idx_to_name.get(object_name_idx, ''),
            'optional': optional,
        })

    for entry in imports:
        entry['outer_name'] = _resolve_outer_name(imports, entry['outer_index'])
        entry['package_path'] = _resolve_package_path(imports, entry['outer_index'])
        if entry['package_path'] and entry['class_name'] != 'Package':
            entry['resolved_object_path'] = f"{entry['package_path']}.{entry['object_name']}"
        else:
            entry['resolved_object_path'] = entry['object_name']

    return imports


def find_import_ref(uasset_data: bytes, *,
                    object_name: str,
                    class_name: Optional[str] = None,
                    package_path: Optional[str] = None) -> Optional[int]:
    """Return the negative import ref for a matching import, if present."""
    for entry in parse_imports(uasset_data):
        if entry.get('object_name') != object_name:
            continue
        if class_name and entry.get('class_name') != class_name:
            continue
        if package_path and entry.get('package_path') != package_path:
            continue
        return entry['negative_ref']
    return None


def append_name_entries(uasset_data: bytes, names: List[str]) -> tuple[bytes, Dict[str, int]]:
    """Append missing FName entries and return updated bytes plus indexes.

    Existing names are reused case-insensitively. This helper updates all
    header offsets and the single export's SerialOffset exactly like the engine
    DataTable path.
    """
    if not names:
        return uasset_data, {}

    data = uasset_data
    fixed_header = data[:28]
    old_total_size = struct.unpack_from('<i', data, 28)[0]

    _folder_text, folder_bytes = _read_fstring(data, 32)
    folder_end = 32 + folder_bytes

    name_count = struct.unpack_from('<i', data, folder_end + 4)[0]
    name_offset = struct.unpack_from('<i', data, folder_end + 8)[0]
    header_fields = bytearray(data[folder_end:name_offset])

    name_entries, name_table_size = _parse_name_table(data, name_offset, name_count)
    rest_start = name_offset + name_table_size
    rest_data = data[rest_start:]

    existing_lookup = {entry['text'].lower(): i for i, entry in enumerate(name_entries)}
    requested_indexes: Dict[str, int] = {}
    added_entries = []

    next_index = name_count
    for raw_name in names:
        name = str(raw_name)
        lower = name.lower()
        if lower in existing_lookup:
            requested_indexes[name] = existing_lookup[lower]
            continue
        existing_lookup[lower] = next_index
        requested_indexes[name] = next_index
        added_entries.append({
            'text': name,
            'hash': _cityhash_lite(name),
        })
        next_index += 1

    if not added_entries:
        return uasset_data, requested_indexes

    new_name_table = b''.join(
        _build_name_entry(entry['text'], entry['hash'])
        for entry in name_entries
    ) + b''.join(
        _build_name_entry(entry['text'], entry['hash'])
        for entry in added_entries
    )

    name_table_delta = len(new_name_table) - name_table_size
    struct.pack_into('<i', header_fields, 4, name_count + len(added_entries))

    old_serial_size = 0
    export_offset = struct.unpack_from('<i', header_fields, 32)[0]
    if export_offset > 0 and export_offset < len(data):
        old_serial_size = struct.unpack_from('<q', data, export_offset + 28)[0]
    upper_bound = old_total_size + max(old_serial_size, 0)

    for byte_off in range(0, len(header_fields) - 3, 4):
        value = struct.unpack_from('<i', header_fields, byte_off)[0]
        if rest_start <= value <= upper_bound:
            struct.pack_into('<i', header_fields, byte_off, value + name_table_delta)

    gen_off = 22 * 4
    if gen_off + 4 <= len(header_fields):
        old_gen = struct.unpack_from('<i', header_fields, gen_off)[0]
        if old_gen == name_count:
            struct.pack_into('<i', header_fields, gen_off, name_count + len(added_entries))

    new_total_size = old_total_size + name_table_delta

    export_count = struct.unpack_from('<i', header_fields, 28)[0]
    depends_offset = struct.unpack_from('<i', data, folder_end + 44)[0]
    if name_table_delta != 0 and export_count > 0 and export_offset > 0:
        rest_buf = bytearray(rest_data)
        if depends_offset > export_offset and export_count > 0:
            entry_size = (depends_offset - export_offset) // export_count
        else:
            entry_size = 96
        for i in range(export_count):
            serial_off_pos = (export_offset - rest_start) + i * entry_size + 36
            if 0 <= serial_off_pos and serial_off_pos + 8 <= len(rest_buf):
                old_serial = struct.unpack_from('<q', rest_buf, serial_off_pos)[0]
                struct.pack_into('<q', rest_buf, serial_off_pos, old_serial + name_table_delta)
        rest_data = bytes(rest_buf)

    result = bytearray()
    result += fixed_header
    result += struct.pack('<i', new_total_size)
    result += data[32:32 + folder_bytes]
    result += header_fields
    result += new_name_table
    result += rest_data
    return bytes(result), requested_indexes


def add_part_import(uasset_data: bytes, *,
                    package_path: str,
                    object_name: str,
                    class_name: str,
                    class_package: str = '/Script/MotorTown') -> tuple[bytes, int, int]:
    """Append a package import + asset import for a VehicleParts0 referenced asset.

    Returns ``(updated_bytes, asset_negative_ref, package_negative_ref)``.
    Unused imports are tolerated by UE, so we intentionally do not try to
    deduplicate identical import pairs here.
    """
    required_names = [package_path, object_name, class_name, class_package, '/Script/CoreUObject', 'Package']
    data, indexes = append_name_entries(uasset_data, required_names)

    package_path_idx = indexes[package_path]
    object_name_idx = indexes[object_name]
    class_name_idx = indexes[class_name]
    class_package_idx = indexes[class_package]
    coreuobject_idx = indexes['/Script/CoreUObject']
    package_name_idx = indexes['Package']

    buf = bytearray(data)
    _folder_text, folder_bytes = _read_fstring(bytes(buf), 32)
    folder_end = 32 + folder_bytes

    import_count = struct.unpack_from('<i', buf, folder_end + 36)[0]
    import_offset = struct.unpack_from('<i', buf, folder_end + 40)[0]
    export_offset = struct.unpack_from('<i', buf, folder_end + 32)[0]
    old_total_size = struct.unpack_from('<i', buf, 28)[0]

    new_package_import_idx = -(import_count + 1)
    new_asset_import_idx = -(import_count + 2)

    package_import = struct.pack(
        '<iiiiiiii',
        coreuobject_idx, 0,
        package_name_idx, 0,
        0,
        package_path_idx, 0,
        0,
    )
    asset_import = struct.pack(
        '<iiiiiiii',
        class_package_idx, 0,
        class_name_idx, 0,
        new_package_import_idx,
        object_name_idx, 0,
        0,
    )

    import_end = import_offset + import_count * 32
    import_delta = 64
    buf = bytearray(bytes(buf[:import_end]) + package_import + asset_import + bytes(buf[import_end:]))
    struct.pack_into('<i', buf, folder_end + 36, import_count + 2)

    old_serial_size = 0
    if export_offset > 0 and export_offset < len(data):
        old_serial_size = struct.unpack_from('<q', data, export_offset + 28)[0]
    upper_bound = old_total_size + max(old_serial_size, 0)
    header_end = struct.unpack_from('<i', buf, folder_end + 8)[0]
    for abs_off in range(folder_end, header_end - 3, 4):
        value = struct.unpack_from('<i', buf, abs_off)[0]
        if import_end <= value <= upper_bound:
            struct.pack_into('<i', buf, abs_off, value + import_delta)

    struct.pack_into('<i', buf, 28, old_total_size + import_delta)

    new_export_offset = struct.unpack_from('<i', buf, folder_end + 32)[0]
    serial_off_pos = new_export_offset + 36
    if serial_off_pos + 8 <= len(buf):
        old_serial = struct.unpack_from('<q', buf, serial_off_pos)[0]
        struct.pack_into('<q', buf, serial_off_pos, old_serial + import_delta)

    preload_offset = struct.unpack_from('<i', buf, folder_end + 160)[0]
    preload_count = struct.unpack_from('<i', buf, folder_end + 156)[0]
    sbs = struct.unpack_from('<i', buf, new_export_offset + 76)[0]
    cbs = struct.unpack_from('<i', buf, new_export_offset + 80)[0]
    sbc = struct.unpack_from('<i', buf, new_export_offset + 84)[0]

    if preload_offset > 0:
        insert_abs = preload_offset + (sbs + cbs + sbc) * 4
        buf = bytearray(bytes(buf[:insert_abs]) + struct.pack('<i', new_asset_import_idx) + bytes(buf[insert_abs:]))
        struct.pack_into('<i', buf, new_export_offset + 84, sbc + 1)
        struct.pack_into('<i', buf, folder_end + 156, preload_count + 1)
        struct.pack_into('<i', buf, 28, struct.unpack_from('<i', buf, 28)[0] + 4)
        serial_off_pos = new_export_offset + 36
        old_serial = struct.unpack_from('<q', buf, serial_off_pos)[0]
        struct.pack_into('<q', buf, serial_off_pos, old_serial + 4)

    return bytes(buf), new_asset_import_idx, new_package_import_idx


def list_part_asset_paths(uasset_data: bytes, prefix: str = '/Game/Cars/Parts/') -> List[str]:
    """Return unique part asset package paths referenced by VehicleParts0."""
    paths = []
    seen = set()
    for entry in parse_imports(uasset_data):
        package_path = entry.get('package_path') or ''
        if not package_path.startswith(prefix):
            continue
        if package_path in seen:
            continue
        seen.add(package_path)
        paths.append(package_path)
    return paths


def list_tire_asset_paths(uasset_data: bytes) -> List[str]:
    """Return unique tire asset package paths referenced by VehicleParts0."""
    return list_part_asset_paths(uasset_data, prefix='/Game/Cars/Parts/Tire/')


def build_vehicleparts_uasset_catalog(uasset_data: bytes) -> Dict[str, Any]:
    """Return a compact catalog view of VehicleParts0.uasset."""
    idx_to_name, name_to_idx = parse_name_lookup(uasset_data)
    imports = parse_imports(uasset_data)
    return {
        'idx_to_name': idx_to_name,
        'name_to_idx': name_to_idx,
        'imports': imports,
        'part_asset_paths': list_part_asset_paths(uasset_data),
        'tire_asset_paths': list_tire_asset_paths(uasset_data),
    }


def _resolve_outer_name(imports: List[Dict[str, Any]], outer_index: int) -> str:
    """Return the immediate outer import object's name, if any."""
    if outer_index >= 0:
        return ''
    idx = (-outer_index) - 1
    if not (0 <= idx < len(imports)):
        return ''
    return imports[idx].get('object_name', '')


def _resolve_package_path(imports: List[Dict[str, Any]], outer_index: int) -> str:
    """Resolve the package path that owns an import, when available."""
    if outer_index >= 0:
        return ''

    idx = (-outer_index) - 1
    if not (0 <= idx < len(imports)):
        return ''

    outer = imports[idx]
    object_name = outer.get('object_name', '')
    if object_name.startswith('/Game/'):
        return object_name

    parent_path = _resolve_package_path(imports, outer.get('outer_index', 0))
    if parent_path:
        return parent_path
    return object_name if object_name.startswith('/Game/') else ''
