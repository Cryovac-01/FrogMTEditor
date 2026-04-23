"""
VehicleParts0.uexp DataTable row parser.

Reverse-engineered row shapes currently observed in vanilla and Frogtuning:

* Two row suffix variants:
    - 80 69 10 07 00 0e 00 00 00 00
    - 80 69 30 07 00 0e 00 00 00 00
* Primary text field families:
    - regular FText hist_type 0 (localized/namespaced)
    - regular FText hist_type -1 (culture-invariant)
    - regular FText hist_type 11 (turbo rows)
    - a compact null-text marker used by a few default rows
* Optional secondary text field:
    - prefixed by 00 03 00 00 00 00
    - followed by the same text-field families as the primary field

The row body after texts is:
    int32 price
    float weight
    opaque tail blob (compatibility / asset refs / extra data)
"""
import struct
from typing import Any, Dict, List, Optional

from parsers.uasset_vehicleparts_dt import build_vehicleparts_uasset_catalog


FOOTER = b'\xc1\x83\x2a\x9e'
ROW_COUNT_OFFSET = 0x0A
ROW_DATA_OFFSET = 0x0E

ROW_HEADER_SUFFIX = b'\x80\x69\x10\x07\x00\x0e\x00\x00\x00\x00'
ROW_HEADER_SUFFIX_ALT = b'\x80\x69\x30\x07\x00\x0e\x00\x00\x00\x00'
ROW_SUFFIXES = (ROW_HEADER_SUFFIX, ROW_HEADER_SUFFIX_ALT)

SECONDARY_FIELD_PREFIX = b'\x00\x03\x00\x00\x00\x00'
NULL_TEXT_FIELD = b'\x00\x00\x00\x00\x00\xff\x00\x00\x00\x00'


def get_row_count(data: bytes) -> int:
    """Return the number of rows stored in VehicleParts0.uexp."""
    return struct.unpack_from('<i', data, ROW_COUNT_OFFSET)[0]


def find_rows(data: bytes,
              idx_to_name: Optional[dict[int, str]] = None,
              imports: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """Parse all VehicleParts0 rows.

    Args:
        data:         Raw VehicleParts0.uexp bytes.
        idx_to_name:  Optional name-table lookup from VehicleParts0.uasset.
        imports:      Optional import table from VehicleParts0.uasset.

    Returns:
        A list of row dictionaries with parsed display text, price, weight,
        and any discovered import references inside the opaque tail blob.
    """
    rows = _find_row_headers(data)
    parsed: List[Dict[str, Any]] = []

    for i, row in enumerate(rows):
        row_end = rows[i + 1]['row_start'] if i + 1 < len(rows) else len(data) - len(FOOTER)
        off = row['row_start'] + 18

        primary_field, off = _read_text_field(data, off)

        secondary_field = None
        if data[off:off + len(SECONDARY_FIELD_PREFIX)] == SECONDARY_FIELD_PREFIX:
            off += len(SECONDARY_FIELD_PREFIX)
            secondary_field, off = _read_text_field(data, off)

        price = struct.unpack_from('<i', data, off)[0]
        weight = struct.unpack_from('<f', data, off + 4)[0]
        tail_start = off + 8
        tail = data[tail_start:row_end]

        asset_refs = _scan_import_refs(tail, imports or [])
        row_name = idx_to_name.get(row['fname_idx'], f'[fname:{row["fname_idx"]}]') if idx_to_name else f'[fname:{row["fname_idx"]}]'

        parsed.append({
            **row,
            'row_end': row_end,
            'row_name': row_name,
            'primary_field': primary_field,
            'secondary_field': secondary_field,
            'primary_text': primary_field.get('text', ''),
            'secondary_text': secondary_field.get('text', '') if secondary_field else '',
            'visible_text': (secondary_field.get('text', '') if secondary_field else '') or primary_field.get('text', ''),
            'short_code': primary_field.get('text', '') if secondary_field and secondary_field.get('text', '') else '',
            'price_off': off,
            'weight_off': off + 4,
            'price': price,
            'weight': weight,
            'tail_start': tail_start,
            'tail': tail,
            'asset_refs': asset_refs,
            'row_kind': _classify_row(asset_refs, row_name),
        })

    return parsed


def find_row_by_key(data: bytes, *, fname_idx: int, fname_number: int = 0,
                    idx_to_name: Optional[dict[int, str]] = None,
                    imports: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any] | None:
    """Return one parsed row matching the composite DataTable key."""
    for row in find_rows(data, idx_to_name=idx_to_name, imports=imports):
        if row['fname_idx'] == fname_idx and row['fname_number'] == fname_number:
            return row
    return None


def find_rows_for_asset(rows: List[Dict[str, Any]], *,
                        object_name: Optional[str] = None,
                        class_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return all parsed rows that reference a specific imported asset."""
    matches: List[Dict[str, Any]] = []
    for row in rows:
        refs = row.get('asset_refs', [])
        for ref in refs:
            if object_name and ref.get('object_name') != object_name:
                continue
            if class_name and ref.get('class_name') != class_name:
                continue
            matches.append(row)
            break
    return matches


def build_vehicleparts_catalog(uasset_data: bytes, uexp_data: bytes) -> Dict[str, Any]:
    """Return a combined VehicleParts0 catalog from both .uasset and .uexp."""
    uasset_catalog = build_vehicleparts_uasset_catalog(uasset_data)
    rows = find_rows(
        uexp_data,
        idx_to_name=uasset_catalog['idx_to_name'],
        imports=uasset_catalog['imports'],
    )

    rows_by_asset_object: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        for ref in row.get('asset_refs', []):
            rows_by_asset_object.setdefault(ref['object_name'], []).append(row)

    return {
        **uasset_catalog,
        'row_count': get_row_count(uexp_data),
        'parsed_row_count': len(rows),
        'row_count_mismatch': get_row_count(uexp_data) != len(rows),
        'rows': rows,
        'rows_by_asset_object': rows_by_asset_object,
        'tire_rows': [row for row in rows if row.get('row_kind') == 'tire'],
    }


def build_row_from_template(template_row: Dict[str, Any], *,
                            fname_idx: int,
                            fname_number: int = 0,
                            primary_text: Optional[str] = None,
                            secondary_text: Optional[str] = None,
                            price: Optional[int] = None,
                            weight: Optional[float] = None,
                            import_ref_map: Optional[Dict[int, int]] = None) -> bytes:
    """Build a VehicleParts0 row by cloning a parsed donor row."""
    row_header = struct.pack('<ii', fname_idx, fname_number)
    suffix = template_row['suffix']

    primary_field = _build_text_field(
        template_row['primary_field'],
        template_row['primary_text'] if primary_text is None else primary_text,
    )

    secondary_bytes = b''
    if template_row.get('secondary_field') is not None:
        secondary_value = template_row.get('secondary_text', '') if secondary_text is None else secondary_text
        secondary_bytes = SECONDARY_FIELD_PREFIX + _build_text_field(
            template_row['secondary_field'],
            secondary_value,
        )

    tail = template_row['tail']
    if import_ref_map:
        tail = _patch_import_refs(tail, import_ref_map)

    row_price = template_row['price'] if price is None else int(price)
    row_weight = template_row['weight'] if weight is None else float(weight)
    price_weight = struct.pack('<i', row_price) + struct.pack('<f', row_weight)

    return row_header + suffix + primary_field + secondary_bytes + price_weight + tail


def update_row(data: bytes, *, fname_idx: int, fname_number: int = 0,
               primary_text: Optional[str] = None,
               secondary_text: Optional[str] = None,
               price: Optional[int] = None,
               weight: Optional[float] = None,
               import_ref_map: Optional[Dict[int, int]] = None,
               idx_to_name: Optional[dict[int, str]] = None,
               imports: Optional[List[Dict[str, Any]]] = None) -> bytes:
    """Replace an existing row while preserving its donor layout."""
    row = find_row_by_key(
        data,
        fname_idx=fname_idx,
        fname_number=fname_number,
        idx_to_name=idx_to_name,
        imports=imports,
    )
    if row is None:
        raise KeyError(f'No VehicleParts0 row for fname_idx={fname_idx}, fname_number={fname_number}')

    new_row = build_row_from_template(
        row,
        fname_idx=fname_idx,
        fname_number=fname_number,
        primary_text=primary_text,
        secondary_text=secondary_text,
        price=price,
        weight=weight,
        import_ref_map=import_ref_map,
    )
    return data[:row['row_start']] + new_row + data[row['row_end']:]


def append_row(data: bytes, row_bytes: bytes) -> bytes:
    """Append one row to VehicleParts0.uexp and increment the header row count."""
    count = get_row_count(data)
    buf = bytearray(data)
    struct.pack_into('<i', buf, ROW_COUNT_OFFSET, count + 1)
    return bytes(buf[:-len(FOOTER)]) + row_bytes + FOOTER


def remove_row(data: bytes, *, fname_idx: int, fname_number: int = 0,
               idx_to_name: Optional[dict[int, str]] = None,
               imports: Optional[List[Dict[str, Any]]] = None) -> bytes:
    """Remove a row from VehicleParts0.uexp by composite key."""
    row = find_row_by_key(
        data,
        fname_idx=fname_idx,
        fname_number=fname_number,
        idx_to_name=idx_to_name,
        imports=imports,
    )
    if row is None:
        raise KeyError(f'No VehicleParts0 row for fname_idx={fname_idx}, fname_number={fname_number}')

    buf = bytearray(data[:row['row_start']] + data[row['row_end']:])
    struct.pack_into('<i', buf, ROW_COUNT_OFFSET, get_row_count(data) - 1)
    return bytes(buf)


def suggest_next_number(data: bytes, *, fname_idx: int,
                        idx_to_name: Optional[dict[int, str]] = None,
                        imports: Optional[List[Dict[str, Any]]] = None) -> int:
    """Suggest the next free row number for an existing row-name FName."""
    numbers = [
        row['fname_number']
        for row in find_rows(data, idx_to_name=idx_to_name, imports=imports)
        if row['fname_idx'] == fname_idx
    ]
    if not numbers:
        return 0
    return max(numbers) + 1


def _find_row_headers(data: bytes) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for suffix in ROW_SUFFIXES:
        pos = ROW_DATA_OFFSET
        while True:
            idx = data.find(suffix, pos)
            if idx < 0:
                break
            row_start = idx - 8
            if row_start < ROW_DATA_OFFSET:
                pos = idx + 1
                continue
            fname_idx, fname_number = struct.unpack_from('<ii', data, row_start)
            rows.append({
                'row_start': row_start,
                'fname_idx': fname_idx,
                'fname_number': fname_number,
                'suffix': suffix,
                'suffix_kind': '0x10' if suffix == ROW_HEADER_SUFFIX else '0x30',
            })
            pos = idx + 1
    rows.sort(key=lambda row: row['row_start'])
    return rows


def _read_text_field(data: bytes, offset: int) -> tuple[Dict[str, Any], int]:
    """Read one VehicleParts0 text field."""
    if data[offset:offset + len(NULL_TEXT_FIELD)] == NULL_TEXT_FIELD:
        return {
            'kind': 'null',
            'flags': 0,
            'hist_type': -1,
            'text': '',
            'start': offset,
            'end': offset + len(NULL_TEXT_FIELD),
        }, offset + len(NULL_TEXT_FIELD)

    flags = struct.unpack_from('<I', data, offset)[0]
    hist_type = struct.unpack_from('<b', data, offset + 4)[0]
    off = offset + 5
    result: Dict[str, Any] = {
        'kind': 'ftext',
        'flags': flags,
        'hist_type': hist_type,
        'start': offset,
    }

    if hist_type == 0:
        namespace, off = _read_fstring(data, off)
        key, off = _read_fstring(data, off)
        text, off = _read_fstring(data, off)
        result.update({
            'namespace': namespace,
            'key': key,
            'text': text,
        })
    elif hist_type == -1:
        has_string = struct.unpack_from('<i', data, off)[0]
        off += 4
        text = ''
        if has_string:
            text, off = _read_fstring(data, off)
        result.update({
            'has_string': bool(has_string),
            'text': text,
        })
    elif hist_type == 11:
        unknown_a = struct.unpack_from('<i', data, off)[0]
        unknown_b = struct.unpack_from('<i', data, off + 4)[0]
        off += 8
        text, off = _read_fstring(data, off)
        result.update({
            'unknown_a': unknown_a,
            'unknown_b': unknown_b,
            'text': text,
        })
    else:
        raise ValueError(f'Unsupported VehicleParts0 FText history type: {hist_type} at {offset}')

    result['end'] = off
    return result, off


def _build_text_field(template_field: Dict[str, Any], text: str) -> bytes:
    """Serialize a text field matching an existing parsed template field."""
    kind = template_field.get('kind')
    if kind == 'null':
        if text:
            raise ValueError('Cannot place non-empty text into a null VehicleParts0 text field')
        return NULL_TEXT_FIELD

    flags = template_field.get('flags', 0)
    hist_type = template_field.get('hist_type', -1)
    buf = struct.pack('<I', flags) + struct.pack('<b', hist_type)

    if hist_type == 0:
        buf += _write_fstring(template_field.get('namespace', 'VehicleParts'))
        buf += _write_fstring(template_field.get('key', ''))
        buf += _write_fstring(text)
        return buf

    if hist_type == -1:
        if text:
            buf += struct.pack('<i', 1)
            buf += _write_fstring(text)
        else:
            buf += struct.pack('<i', 0)
        return buf

    if hist_type == 11:
        buf += struct.pack('<i', int(template_field.get('unknown_a', 0)))
        buf += struct.pack('<i', int(template_field.get('unknown_b', 0)))
        buf += _write_fstring(text)
        return buf

    raise ValueError(f'Unsupported VehicleParts0 history type for serialization: {hist_type}')


def _read_fstring(data: bytes, offset: int) -> tuple[str, int]:
    """Read a UE FString and return ``(text, new_offset)``."""
    slen = struct.unpack_from('<i', data, offset)[0]
    if slen < 0 or slen > 4096:
        raise ValueError(f'Invalid FString length {slen} at {offset}')
    if slen == 0:
        return '', offset + 4
    text = data[offset + 4:offset + 4 + slen - 1].decode('ascii', errors='replace')
    return text, offset + 4 + slen


def _write_fstring(text: str) -> bytes:
    """Serialize a UE FString."""
    encoded = text.encode('ascii', errors='replace') + b'\x00'
    return struct.pack('<i', len(encoded)) + encoded


def _scan_import_refs(tail: bytes, imports: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Scan the opaque row tail for negative import references."""
    if not imports:
        return []

    seen: set[tuple[int, int]] = set()
    refs: List[Dict[str, Any]] = []
    import_count = len(imports)

    for off in range(0, max(len(tail) - 3, 0)):
        value = struct.unpack_from('<i', tail, off)[0]
        if not (-import_count <= value < 0):
            continue
        key = (off, value)
        if key in seen:
            continue
        seen.add(key)

        import_entry = imports[-value - 1]
        if import_entry.get('class_name') == 'Package':
            continue

        refs.append({
            'tail_offset': off,
            'negative_ref': value,
            'import_index': import_entry['import_index'],
            'class_name': import_entry.get('class_name', ''),
            'object_name': import_entry.get('object_name', ''),
            'package_path': import_entry.get('package_path', ''),
            'resolved_object_path': import_entry.get('resolved_object_path', ''),
        })

    return refs


def _patch_import_refs(tail: bytes, import_ref_map: Dict[int, int]) -> bytes:
    """Replace exact negative import references inside a row tail blob."""
    patched = tail
    for old_ref, new_ref in import_ref_map.items():
        patched = patched.replace(struct.pack('<i', old_ref), struct.pack('<i', new_ref))
    return patched


def _classify_row(asset_refs: List[Dict[str, Any]], row_name: str) -> str:
    """Best-effort row classification for inspection/debugging."""
    classes = {ref.get('class_name', '') for ref in asset_refs}
    if 'MTTirePhysicsDataAsset' in classes:
        return 'tire'
    if 'StaticMesh' in classes:
        return 'mesh_part'
    if 'BlueprintGeneratedClass' in classes:
        return 'blueprint_part'
    if 'SoundWave' in classes:
        return 'audio_part'
    if row_name in ('DefaultBody', 'DefaultAttachment'):
        return 'default'
    return 'config'
