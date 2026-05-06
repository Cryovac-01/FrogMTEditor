"""Buildings DataTable construction-cost modifier.

Targets Motor Town's Buildings DataTables (e.g. Buildings_Houses.uexp).
The .uexp file contains row blocks for every building (depots, garages,
houses, parking spaces); each row that has a construction cost embeds
a cargo-requirement array somewhere inside its block.

Cargo array binary layout (verified by reverse-engineering vanilla
Buildings_Houses.uexp against the in-game Construction screen for
Depot_01 — quantities 15, 15, 4, 3, 3 matched exactly):

    [int32 count]              array length
    [int32 zero_pad]           always 0
    [int32 zero_pad]           always 0
    count × {
        int32 quantity         the cargo amount required
        int32 name_idx         FName index into the .uasset name table
        int32 name_inst        FName instance, always 0 here
    }

The structure is unambiguous enough that we can find the cargo arrays
without resolving FNames against the .uasset name table — we just
pattern-match on the layout (count + two zero pads + N entries where
each entry has a small positive quantity, a non-negative name index,
and a zero instance).

Zeroing every quantity yields a "free construction" mod: the building
still has the same step structure and the construction site still
appears in-game, but every required cargo amount drops to 0, so the
build completes the moment the player places the construction site
without any deliveries.

Why this approach instead of UE4SS-Lua reflection: Motor Town's row
struct field names aren't exposed via reflection on current builds,
which made the runtime-Lua mod (CryovacFreeDepotConstruction) unable
to locate the cargo collection. The .uexp byte structure, in contrast,
hasn't changed — and once we've identified it, modifying the bytes
in place is deterministic and survives game updates that don't
change the DT layout itself.
"""
from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from typing import List, Tuple


# Plausibility bounds for cargo-array detection. Tightening these
# lowers false positives; loosening lets the scan find arrays that
# happen to share offsets with random data.
_MAX_ENTRY_COUNT  = 15      # arrays larger than this are unlikely
_MIN_ENTRY_COUNT  = 2       # need at least 2 entries
_MAX_QUANTITY     = 200     # vanilla quantities top out around 30
_MAX_NAME_INDEX   = 10000   # generous upper bound for name-table size


@dataclass
class CargoArray:
    """One detected construction-cost array inside a .uexp."""
    count_offset: int          # byte offset of the array's int32 count
    count: int                 # number of entries
    entry_offsets: List[int]   # byte offset of each entry's int32 quantity
    quantities: List[int]      # original quantity values
    name_indices: List[int]    # FName idx for each entry (kept for diagnostics)


def find_cargo_arrays(uexp_bytes: bytes) -> List[CargoArray]:
    """Scan *uexp_bytes* for cargo-requirement arrays.

    Returns the list of detected arrays. Each entry's `entry_offsets`
    points at the int32 quantity slot, ready for a 4-byte write.
    """
    found: List[CargoArray] = []
    n = len(uexp_bytes)
    for off in range(0, n - 16, 4):
        count = struct.unpack_from('<i', uexp_bytes, off)[0]
        if not (_MIN_ENTRY_COUNT <= count <= _MAX_ENTRY_COUNT):
            continue
        pad1 = struct.unpack_from('<i', uexp_bytes, off + 4)[0]
        pad2 = struct.unpack_from('<i', uexp_bytes, off + 8)[0]
        if pad1 != 0 or pad2 != 0:
            continue
        entries_start = off + 12
        if entries_start + count * 12 > n:
            continue
        # Validate each entry's plausibility before accepting.
        entry_offsets: List[int] = []
        quantities: List[int] = []
        name_indices: List[int] = []
        e = entries_start
        ok = True
        for _ in range(count):
            qty = struct.unpack_from('<i', uexp_bytes, e)[0]
            idx = struct.unpack_from('<i', uexp_bytes, e + 4)[0]
            inst = struct.unpack_from('<i', uexp_bytes, e + 8)[0]
            if not (1 <= qty <= _MAX_QUANTITY):
                ok = False; break
            if not (0 <= idx <= _MAX_NAME_INDEX):
                ok = False; break
            if inst != 0:
                ok = False; break
            entry_offsets.append(e)
            quantities.append(qty)
            name_indices.append(idx)
            e += 12
        if ok:
            found.append(CargoArray(
                count_offset=off,
                count=count,
                entry_offsets=entry_offsets,
                quantities=quantities,
                name_indices=name_indices,
            ))
    return found


def zero_all_quantities(uexp_bytes: bytes) -> Tuple[bytes, List[CargoArray]]:
    """Return a copy of *uexp_bytes* with every cargo-array quantity
    set to 0, plus the list of arrays the modifier touched.

    The .uasset doesn't need to be modified — the name table, import
    table, export table, and offsets all stay identical. Only the
    .uexp values change, and the .uexp's serial size in the .uasset
    export entry stays the same.
    """
    arrays = find_cargo_arrays(uexp_bytes)
    if not arrays:
        return uexp_bytes, []
    buf = bytearray(uexp_bytes)
    for arr in arrays:
        for off in arr.entry_offsets:
            struct.pack_into('<i', buf, off, 0)
    return bytes(buf), arrays


def patch_buildings_uexp(input_path: str, output_path: str) -> Tuple[int, int]:
    """Read the .uexp at *input_path*, zero every cargo quantity, and
    write the result to *output_path*. Returns (arrays_touched,
    total_quantities_zeroed)."""
    with open(input_path, 'rb') as f:
        original = f.read()
    modified, arrays = zero_all_quantities(original)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'wb') as f:
        f.write(modified)
    total_zeroed = sum(arr.count for arr in arrays)
    return len(arrays), total_zeroed


def deploy_free_construction(unpacked_root: str, mod_tree_root: str) -> dict:
    """End-to-end deploy: copy + patch every Buildings* .uexp from
    the unpacked vanilla tree into the mod tree, with all cargo
    quantities zeroed. The matching .uasset files are copied
    unchanged (they don't need patching — we only changed values
    inside the .uexp, not its size).

    Args:
      unpacked_root: path to <Motor Town>/MotorTown/Content/...
                     (typically the user's "Select Unpacked Folder")
      mod_tree_root: path to <project>/data/mod/MotorTown/Content/...
                     (where Pack Mod will pick up the changes)

    Returns a dict with success/error info + per-file stats.
    """
    src_dir = os.path.join(unpacked_root, 'MotorTown', 'Content',
                           'DataAsset', 'Buildings')
    if not os.path.isdir(src_dir):
        return {'success': False,
                'error': f'Buildings DataAsset folder not found at {src_dir!r}'}

    dst_dir = os.path.join(mod_tree_root, 'MotorTown', 'Content',
                           'DataAsset', 'Buildings')
    os.makedirs(dst_dir, exist_ok=True)

    per_file = []
    total_arrays = 0
    total_zeroed = 0
    for name in sorted(os.listdir(src_dir)):
        if not name.startswith('Buildings'):
            continue
        if not (name.endswith('.uasset') or name.endswith('.uexp')):
            continue
        src_path = os.path.join(src_dir, name)
        dst_path = os.path.join(dst_dir, name)
        if name.endswith('.uexp'):
            arrays, zeroed = patch_buildings_uexp(src_path, dst_path)
            per_file.append({'file': name, 'arrays': arrays, 'zeroed': zeroed})
            total_arrays += arrays
            total_zeroed += zeroed
        else:
            # .uasset — copy verbatim
            with open(src_path, 'rb') as f:
                data = f.read()
            with open(dst_path, 'wb') as f:
                f.write(data)
            per_file.append({'file': name, 'arrays': 0, 'zeroed': 0,
                             'copied_unchanged': True})

    return {
        'success': True,
        'arrays_touched': total_arrays,
        'quantities_zeroed': total_zeroed,
        'files': per_file,
        'mod_tree_path': dst_dir,
    }
