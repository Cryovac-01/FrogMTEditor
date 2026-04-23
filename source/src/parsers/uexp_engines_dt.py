"""
Engines.uexp DataTable row builder/appender.

Binary layout of Engines.uexp (UE5 DataTable, 163 rows, 64601 bytes):
  offset 0x00–0x09  file header
  offset 0x0a       row count (int32-LE)
  offset 0x0e       first row begins
  last 4 bytes      footer = c1 83 2a 9e

Each row structure:
  [ 8 bytes ] FName  → struct.pack('<ii', fname_idx, 0)
  [10 bytes ] fixed suffix → b'\x80\x69\x10\x07\x00\x0c\x00\x00\x00\x00'
  [ 5 bytes ] FText header → b'\x00\x00\x00\x00\x00'  (flags=0, hist_type=0)
  [17 bytes ] namespace    → b'\x0d\x00\x00\x00VehicleParts\x00'
  [37 bytes ] GUID FString → int32(33) + 32-char UUID uppercase + \x00
  [ 4+N bytes] display FStr → int32(N) + display_text + \x00  (N = len+1)
  [15 bytes ] null-desc    → b'\x00\x03\x00\x00\x00\x00\x00\x00\x00\x00\xff\x00\x00\x00\x00'
  [ 4 bytes ] price        → struct.pack('<i', price)
  [ 4 bytes ] weight       → struct.pack('<f', weight)
  [N bytes  ] tail         → variable-length struct remainder (299-748 bytes),
                              contains vehicle compatibility arrays and physics params
"""
import struct
import uuid as _uuid


FOOTER = b'\xc1\x83\x2a\x9e'
ROW_COUNT_OFFSET = 0x0a
ROW_HEADER_SUFFIX = b'\x80\x69\x10\x07\x00\x0c\x00\x00\x00\x00'
ROW_HEADER_SUFFIX_ALT = b'\x80\x69\x00\x07\x00\x0c\x00\x00\x00\x00'
NAMESPACE_FSTR = b'\x0d\x00\x00\x00VehicleParts\x00'
DESC_FTEXT_PREFIX = b'\x00\x03\x00\x00\x00\x00\x00\x00\x00\x00\xff'
FTEXT_HDR = b'\x00\x00\x00\x00\x00'

# Total fixed overhead before display FString within FText block:
#   FTEXT_HDR(5) + NAMESPACE_FSTR(17) + GUID_FSTR(37) = 59 bytes
# FText block starts at byte 18 of each row (after FName 8 + suffix 10)
_FTEXT_OFFSET_IN_ROW = 18
_GUID_FSTR_LEN = 37  # int32(33) + 32 chars + \x00
_FTEXT_BEFORE_DISPLAY = len(FTEXT_HDR) + len(NAMESPACE_FSTR) + _GUID_FSTR_LEN  # 59


def get_row_count(data: bytes) -> int:
    """Return the number of rows stored in the DataTable."""
    return struct.unpack_from('<i', data, ROW_COUNT_OFFSET)[0]


def _find_type_a_rows(data: bytes) -> list:
    """Scan Engines.uexp for rows using the 10-byte suffix marker.

    Returns a list of dicts:
      row_start  – absolute offset of FName (start of row)
      tail_start – absolute offset where the variable-length tail begins
      display    – decoded display name string
      slen       – raw FString length field value (includes null terminator)
    """
    rows = []
    # Find all suffix matches (both primary and alternate variant)
    suffix_hits = []
    for suffix in (ROW_HEADER_SUFFIX, ROW_HEADER_SUFFIX_ALT):
        pos = 0x0e
        while True:
            idx = data.find(suffix, pos)
            if idx == -1:
                break
            suffix_hits.append(idx)
            pos = idx + 1
    suffix_hits = sorted(set(suffix_hits))

    for idx in suffix_hits:
        # Suffix is at idx, row_start is 8 bytes before (FName)
        row_start = idx - 8
        if row_start < 0x0e:
            continue
        if row_start + 23 >= len(data):
            continue

        # Parse FText block after suffix
        off = idx + len(ROW_HEADER_SUFFIX)
        if off + 5 > len(data):
            continue

        ftext_flags = struct.unpack_from('<I', data, off)[0]
        off += 4
        hist_type = struct.unpack_from('<b', data, off)[0]
        off += 1
        bhas = None

        if hist_type == 0:
            # Has namespace + GUID key + display
            if off + 4 > len(data):
                continue
            ns_len = struct.unpack_from('<i', data, off)[0]; off += 4
            if ns_len <= 0 or ns_len > 256:
                continue
            off += ns_len  # skip namespace string
            if off + 4 > len(data):
                continue
            key_len = struct.unpack_from('<i', data, off)[0]; off += 4
            if key_len <= 0 or key_len > 256:
                continue
            off += key_len  # skip key/GUID
            if off + 4 > len(data):
                continue
            slen = struct.unpack_from('<i', data, off)[0]; off += 4
            if slen <= 0 or slen > 256:
                continue
            display_bytes = data[off:off + slen - 1]
            try:
                display = display_bytes.decode('ascii')
            except Exception:
                continue
            off += slen
        elif hist_type == -1:
            # Culture-invariant string rows store bHasCultureInvariantString first.
            if off + 4 > len(data):
                continue
            bhas = struct.unpack_from('<i', data, off)[0]
            off += 4
            if bhas not in (0, 1):
                continue
            if bhas:
                if off + 4 > len(data):
                    continue
                slen = struct.unpack_from('<i', data, off)[0]
                off += 4
                if slen <= 0 or slen > 256:
                    continue
                display_bytes = data[off:off + slen - 1]
                try:
                    display = display_bytes.decode('ascii')
                except Exception:
                    continue
                off += slen
            else:
                slen = 0
                display = ''
        else:
            continue

        desc, desc_end = _read_description_field(data, off)
        price_off = desc_end
        weight_off = price_off + 4
        tail_start = weight_off + 4
        if tail_start > len(data):
            continue

        rows.append({
            'row_start': row_start,
            'tail_start': tail_start,
            'price_off': price_off,
            'weight_off': weight_off,
            'display': display,
            'slen': slen,
            'fname_idx': struct.unpack_from('<i', data, row_start)[0],
            'flags': ftext_flags,
            'hist_type': hist_type,
            'bhas': bhas,
            'description': desc,
        })

    return rows


def _read_description_field(data: bytes, offset: int) -> tuple[str, int]:
    """Read the optional second-line description FText used by compatibility rows."""
    prefix_len = len(DESC_FTEXT_PREFIX)
    if offset + prefix_len + 4 > len(data):
        return '', offset
    if data[offset:offset + prefix_len] != DESC_FTEXT_PREFIX:
        return '', offset

    off = offset + prefix_len
    has_desc = struct.unpack_from('<i', data, off)[0]
    off += 4
    if has_desc not in (0, 1):
        return '', offset
    if not has_desc:
        return '', off

    if off + 4 > len(data):
        return '', offset
    slen = struct.unpack_from('<i', data, off)[0]
    off += 4
    if slen <= 0 or off + slen > len(data):
        return '', offset

    desc_bytes = data[off:off + slen - 1]
    try:
        desc = desc_bytes.decode('ascii')
    except Exception:
        desc = ''
    return desc, off + slen


def find_template_row_for_variant(data: bytes, variant: str) -> dict | None:
    """Return a donor row whose display/tail fits the requested engine variant."""
    VARIANT_DISPLAY_PREFERENCES = {
        'diesel_hd': [
            'Heavy-Duty 440HP',
            'Heavy-Duty 350HP',
            'Heavy-Duty 260HP',
            'Heavy-Duty 540HP',
            'Medium-Duty 330HP',
            'Medium-Duty 250HP',
            'Medium-Duty 190HP',
            'Bus 400HP',
        ],
        'bike': [
            'Bike i4 100HP',
            'Bike i4 160HP',
            'Bike 100HP',
            'Bike 50HP',
            'Bike 30HP',
            'H2 30HP',
        ],
        'ev': [
            'EV 300HP',
            'EV 130HP',
            'EV 670HP',
        ],
        'ice_standard': [
            'V12 400HP',
            'V8 320HP',
            'V8 240HP',
            'V8 180HP',
            'V8 140HP',
            'V6 400HP',
        ],
        'ice_compact': [
            'I4 150HP',
            'I6 200HP',
            'I4 90HP',
            'I4 50HP',
            'Scooter 15HP',
            'Scooter 10HP',
            'V6 400HP',
        ],
    }

    rows = _find_type_a_rows(data)
    preferences = VARIANT_DISPLAY_PREFERENCES.get(variant, [])

    def _norm(text: str) -> str:
        return ' '.join(text.lower().split())

    def _with_tail(idx: int, row: dict) -> dict | None:
        row_end = rows[idx + 1]['row_start'] if idx + 1 < len(rows) else len(data) - len(FOOTER)
        tail = data[row['tail_start']:row_end]
        if len(tail) < 100:
            return None
        return {**row, 'row_end': row_end, 'tail': tail}

    for preferred_display in preferences:
        preferred_norm = _norm(preferred_display)
        for i, row in enumerate(rows):
            if _norm(row['display']) != preferred_norm:
                continue
            match = _with_tail(i, row)
            if match is not None:
                return match

    for i, row in enumerate(rows):
        match = _with_tail(i, row)
        if match is not None:
            return match

    return None


def find_tail_for_variant(data: bytes, variant: str) -> bytes:
    """Return the tail bytes appropriate for the given engine variant.

    The tail encodes vehicle-type compatibility / physics parameters.
    We clone it from an existing row that matches the variant.
    Tail length is VARIABLE (299-748 bytes) — never truncate.

    variant values: 'diesel_hd', 'bike', 'ev', 'ice_standard', 'ice_compact'
    Falls back to first row tail.
    """
    row = find_template_row_for_variant(data, variant)
    if row is not None:
        return row['tail']
    return data[0x80:0x80 + 299]


def _build_description_field(description: str = '') -> bytes:
    """Build the optional second-line description field."""
    if not description:
        return DESC_FTEXT_PREFIX + struct.pack('<i', 0)
    desc_enc = description.encode('ascii') + b'\x00'
    return DESC_FTEXT_PREFIX + struct.pack('<i', 1) + struct.pack('<i', len(desc_enc)) + desc_enc


def build_row(fname_idx: int, display_name: str, price: int,
              weight: float, tail: bytes, *,
              description: str = '',
              hist_type: int = 0, flags: int = 0) -> bytes:
    """Build a complete Engines DataTable row binary.

    Args:
        fname_idx:    Index of the row-key FName in the .uasset name table
        display_name: Human-readable engine name shown in the shop
        price:        Coin price (int32)
        weight:       Weight in kg (float32)
        tail:         Variable-length tail cloned from a variant template row

    Returns:
        Complete row bytes ready to insert before the DataTable footer
    """
    # FName (8 bytes)
    fname = struct.pack('<ii', fname_idx, 0)

    # Fixed suffix (10 bytes)
    suffix = ROW_HEADER_SUFFIX

    display_enc = display_name.encode('ascii') + b'\x00'
    display_fstr = struct.pack('<i', len(display_enc)) + display_enc

    if hist_type == -1:
        ftext = struct.pack('<I', flags) + struct.pack('<b', -1) + struct.pack('<i', 1) + display_fstr
    else:
        guid_str = _uuid.uuid4().hex.upper()  # 32 hex chars
        guid_enc = guid_str.encode('ascii') + b'\x00'
        guid_fstr = struct.pack('<i', len(guid_enc)) + guid_enc
        ftext = FTEXT_HDR + NAMESPACE_FSTR + guid_fstr + display_fstr

    desc_bytes = _build_description_field(description)

    # Price + weight (8 bytes)
    price_weight = struct.pack('<i', price) + struct.pack('<f', weight)

    return fname + suffix + ftext + desc_bytes + price_weight + tail


def build_row_from_template(fname_idx: int, display_name: str, price: int,
                            weight: float, tail: bytes, template_row: dict,
                            description: str = '') -> bytes:
    """Build a row matching an existing donor row's FText style."""
    return build_row(
        fname_idx,
        display_name,
        price,
        weight,
        tail,
        description=description,
        hist_type=template_row.get('hist_type', 0),
        flags=template_row.get('flags', 0),
    )


def find_row_by_fname_idx(data: bytes, fname_idx: int) -> dict | None:
    """Return the row-info dict for the row whose FName index matches *fname_idx*.

    Returns None if no matching row is found.
    The returned dict has the same keys as _find_type_a_rows entries plus
    ``fname_idx`` and ``row_end`` (absolute offset of the byte after the tail).
    """
    rows = _find_type_a_rows(data)
    for i, row in enumerate(rows):
        idx = struct.unpack_from('<i', data, row['row_start'])[0]
        if idx == fname_idx:
            if i + 1 < len(rows):
                row_end = rows[i + 1]['row_start']
            else:
                row_end = len(data) - len(FOOTER)
            return {**row, 'fname_idx': fname_idx, 'row_end': row_end}
    return None


def read_row(data: bytes, fname_idx: int) -> dict | None:
    """Read display_name, price and weight for the row with *fname_idx*.

    Returns a dict ``{'display_name': str, 'price': int, 'weight': float}``
    or None if the row is not found.
    """
    row = find_row_by_fname_idx(data, fname_idx)
    if row is None:
        return None
    price = struct.unpack_from('<i', data, row['price_off'])[0]
    weight = struct.unpack_from('<f', data, row['weight_off'])[0]
    return {
        'display_name': row['display'],
        'description': row.get('description', ''),
        'price': price,
        'weight': round(weight, 3),
    }


def update_row(data: bytes, fname_idx: int, display_name: str,
               price: int, weight: float, description: str | None = None) -> bytes:
    """Rewrite the display_name, price and weight fields for an existing row.

    Because the display FString is variable-length the whole row is rebuilt
    (tail bytes are cloned from the original row so physics data is preserved).
    Row count is unchanged.

    Returns updated .uexp bytes.
    """
    rows = _find_type_a_rows(data)
    target = None
    target_i = None
    for i, row in enumerate(rows):
        if struct.unpack_from('<i', data, row['row_start'])[0] == fname_idx:
            target = row
            target_i = i
            break

    if target is None:
        raise KeyError(f'No Engines DataTable row with fname_idx={fname_idx}')

    # Determine row boundaries
    if target_i + 1 < len(rows):
        row_end = rows[target_i + 1]['row_start']
    else:
        row_end = len(data) - len(FOOTER)

    # Extract existing tail (preserve full variable-length physics/compat bytes)
    tail = data[target['tail_start']:row_end]

    new_row = build_row(
        fname_idx,
        display_name,
        price,
        weight,
        tail,
        description=target.get('description', '') if description is None else description,
        hist_type=target['hist_type'],
        flags=target['flags'],
    )

    # Splice: everything before old row  +  new row  +  everything after old row
    # Row count field stays the same (same number of rows)
    return data[:target['row_start']] + new_row + data[row_end:]


def patch_row_price_weight(data: bytes, fname_idx: int,
                           price: int, weight: float) -> bytes:
    """Patch only the price and weight fields of an existing row in-place.

    Does NOT rebuild the row or touch the FText display name — safe for rows
    that use any hist_type format (0 or -1).  The DataTable binary is returned
    with exactly the same size as the input; only 8 bytes change.

    Args:
        data:      Original .uexp bytes
        fname_idx: FName index of the row to update
        price:     New coin price (int32)
        weight:    New weight in kg (float32)

    Returns:
        Updated .uexp bytes (same length as input).
    Raises:
        KeyError if the row is not found.
    """
    rows = _find_type_a_rows(data)
    for row in rows:
        if struct.unpack_from('<i', data, row['row_start'])[0] == fname_idx:
            buf = bytearray(data)
            struct.pack_into('<i', buf, row['price_off'], price)
            struct.pack_into('<f', buf, row['weight_off'], weight)
            return bytes(buf)
    raise KeyError(f'No Engines DataTable row with fname_idx={fname_idx}')


def append_row(data: bytes, row_bytes: bytes) -> bytes:
    """Append a row to the DataTable binary.

    Increments the row count at ROW_COUNT_OFFSET and inserts row_bytes
    immediately before the 4-byte footer.

    Args:
        data:      Original .uexp file bytes
        row_bytes: Pre-built row from build_row()

    Returns:
        Updated .uexp bytes
    """
    count = get_row_count(data)
    buf = bytearray(data)
    struct.pack_into('<i', buf, ROW_COUNT_OFFSET, count + 1)
    body = bytes(buf[:-len(FOOTER)])
    return body + row_bytes + FOOTER

