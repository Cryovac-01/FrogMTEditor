"""Buildings DataTable construction-cost modifier.

Targets Motor Town's Buildings DataTables (Buildings_Houses.uexp). The
.uexp file contains row blocks for every building. Depot rows embed a
Materials TMap<FName, int32> with the construction-cost requirements.

Materials TMap binary layout (CORRECTED 2026-05-08; the original
parser interpretation in this file was wrong):

    [int32 count]
    count × {
        int32 name_idx     // FName index in the .uasset name table
        int32 name_inst    // FName instance number (always 0 here)
        int32 value        // the required quantity
    }

There are no zero pads after the count — the original parser's
"zero pad" detection happened to match because Concrete (the typical
first material) has name_idx=0 in vanilla, so [name_idx=0,
name_inst=0] looked like "two zero pads" to the old scanner. The
old scanner's "qty" writes coincidentally landed on the actual value
bytes by 8-byte alignment, so its bulk modifications worked — but its
diagnostic outputs (which materials, in what order) were wrong.

Working "free depot construction" approach (verified in-game v5+):
shrink the depot row's Materials TMap from 5 entries to 1 entry
(Sand=1). Player drops a single Sand cargo at the construction site,
the natural completion event fires (because TMap.length matches
DeliveredMaterials.length), construction completes end-to-end
including save persistence — no runtime Lua needed.

The legacy "zero all quantities" approach is preserved below in
zero_all_quantities() for reference but should NOT be used: setting
required=0 leaves slots that can't receive delivery events, so the
state machine never advances and the construction stays stuck.
"""
from __future__ import annotations

import os
import shutil
import struct
import sys
from dataclasses import dataclass
from typing import Dict, List, Tuple

# Resolve sibling packages when imported from outside src/
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)


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


def zero_all_quantities(uexp_bytes: bytes,
                        token_qty: int = 1) -> Tuple[bytes, List[CargoArray]]:
    """Return a copy of *uexp_bytes* with every construction-cost
    quantity reduced to a token value (default 1), plus the list of
    arrays touched.

    Why every entry gets a token instead of just one:
      Motor Town's construction state machine advances on delivery
      events — when a player delivers cargo to a construction site,
      the state machine fires "step delivered" and progresses toward
      "construction finished". With requirements at 0, no delivery
      can fire (the slot is already full at 0/0), so the completion
      event never triggers and the building stays stuck.

      Earlier attempts left a token requirement on a single entry
      (the assumed Sand position), but that produced inconsistent
      results — likely because (a) Motor Town's construction has
      multiple steps that each need their own delivery event, and/or
      (b) the array entry order doesn't reliably match the in-game
      UI order, so picking "the Sand slot" was a guess.

      Setting EVERY entry to 1 sidesteps both unknowns: the player
      delivers one of each cargo type (5 trivial deliveries), every
      step's every requirement gets satisfied, and the vanilla
      completion flow fires reliably.

    Practical effect on a depot/garage construction site:
      All 5 materials show 0/1. Drop one of each from any industrial
      pickup. Construction completes. Total cost: ~5 cargo units of
      whatever the cheapest available items are.

    Args:
      uexp_bytes: the original .uexp content
      token_qty:  the quantity left on every entry. Default 1
                  ("effectively free"). Pass 0 to truly zero
                  everything (results in stuck construction sites,
                  per the state-machine behaviour described above).

    The .uasset doesn't need updating — only int32 values inside the
    .uexp change, all sizes and offsets stay identical.
    """
    arrays = find_cargo_arrays(uexp_bytes)
    if not arrays:
        return uexp_bytes, []
    buf = bytearray(uexp_bytes)
    for arr in arrays:
        for off in arr.entry_offsets:
            struct.pack_into('<i', buf, off, token_qty)
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


def _resolve_buildings_source_dir(unpacked_root: str = '') -> str:
    """Pick the source directory that holds vanilla Buildings_*.uasset/.uexp.

    Priority:
      1. <project>/data/vanilla/Buildings/  (bundled with the editor —
         no unpacking required, works out of the box)
      2. <unpacked_root>/MotorTown/Content/DataAsset/Buildings/
         (fall back when the user has set an Unpacked folder; this
         is the always-fresh path that picks up MT updates)

    The bundled copy is preferred because the binary structure of
    Buildings_Houses construction-cost arrays has been stable across
    Motor Town releases and the patch we apply (zeroing int32
    quantities) doesn't add or remove rows, so a slightly stale
    vanilla snapshot is still safe. If the bundled file is missing
    AND no unpacked folder is set, the function returns ''.
    """
    # 1. Bundled copy at <project>/data/vanilla/Buildings/
    proj_root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)
    )))
    bundled = os.path.join(proj_root, 'data', 'vanilla', 'Buildings')
    if os.path.isdir(bundled) and any(
        f.startswith('Buildings_Houses') for f in os.listdir(bundled)
    ):
        return bundled
    # 2. Unpacked folder
    if unpacked_root:
        candidate = os.path.join(unpacked_root, 'MotorTown', 'Content',
                                 'DataAsset', 'Buildings')
        if os.path.isdir(candidate):
            return candidate
    return ''


def deploy_free_construction(unpacked_root: str = '',
                             mod_tree_root: str = '') -> dict:
    """End-to-end deploy: read vanilla Buildings_*.uasset/.uexp, zero
    all construction-cargo quantities, and write the result into the
    mod tree. Pack Mod picks them up automatically.

    Args:
      unpacked_root: optional path to <Motor Town>/. Used as a
                     fallback source if the editor doesn't have
                     bundled vanilla Buildings files. Most users
                     don't need to set this — the editor ships with
                     the vanilla files in data/vanilla/Buildings/.
      mod_tree_root: required. Path to <project>/data/mod/. The mod
                     Buildings folder is created under
                     <mod_tree_root>/MotorTown/Content/DataAsset/Buildings/.

    Returns a dict with success/error info + per-file stats. The
    returned dict's `source` key tells the caller whether the
    bundled vanilla copy or the user's unpacked folder was used.
    """
    src_dir = _resolve_buildings_source_dir(unpacked_root)
    if not src_dir:
        return {
            'success': False,
            'error': (
                'Vanilla Buildings DataTable not available. The editor '
                'usually ships with this in data/vanilla/Buildings/. If '
                'that folder is missing in your install, point the '
                'Economy panel at your unpacked Motor Town folder and '
                'try again.'
            ),
        }

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
        'source': src_dir,
    }


# ==========================================================================
# v6 mod-pak path (CORRECTED layout) — the working approach as of 2026-05-08
# ==========================================================================

# Vanilla Depot offsets in Buildings_Houses.uexp.
# These are the start of the Materials TMap count field. The TMap layout is:
#   [int32 count][count × (name_idx, name_inst, value)]
# Depot_01 vanilla: 5 entries = Concrete=10, Sand=10, WoodPlank=2, H-Beam=2, Pipes=2
# Depot_02 vanilla: 5 entries = Concrete=15, Sand=15, WoodPlank=4, H-Beam=3, Pipes=3
DEPOT_TARGETS = [
    {'name': 'Depot_02', 'count_offset': 0x4c8, 'vanilla_count': 5},
    {'name': 'Depot_01', 'count_offset': 0x408, 'vanilla_count': 5},
]

# Sand's name index in Buildings_Houses.uasset name table. We're keeping
# Sand because it's the only trivial-to-acquire material on the Depot
# requirements list — Concrete/WoodPlank/H-Beam/PlasticPipes all involve
# multi-step production chains.
SAND_NAME_IDX = 24

# .uasset Export[0].SerialSize lives at this byte offset. SerialSize must
# match the new (shrunk) .uexp size minus the 4-byte footer.
EXPORT_SERIAL_SIZE_OFFSET = 176489 + 28

# Each TMap entry is name_idx + name_inst + value, all int32.
ENTRY_SIZE = 12


def shrink_materials_tmap_to_sand(uexp: bytes,
                                  count_offset: int,
                                  vanilla_count: int,
                                  target_value: int = 1) -> bytes:
    """Shrink a Materials TMap at count_offset down to a single
    Sand=target_value entry.

    Returns the new uexp bytes; size shrinks by (vanilla_count - 1) * 12.
    """
    found = struct.unpack_from('<i', uexp, count_offset)[0]
    if found != vanilla_count:
        raise ValueError(
            f'Expected count={vanilla_count} at 0x{count_offset:x}, got {found}')

    entries_end = count_offset + 4 + vanilla_count * ENTRY_SIZE
    sand_entry = struct.pack('<iii', SAND_NAME_IDX, 0, target_value)
    return (
        uexp[:count_offset] +
        struct.pack('<i', 1) +
        sand_entry +
        uexp[entries_end:]
    )


def generate_free_depots_pak(output_pak_path: str,
                             vanilla_uasset: bytes = None,
                             vanilla_uexp: bytes = None) -> Dict:
    """Generate a mod-pak that makes both Depot_01 and Depot_02 buildable
    from a single Sand cargo delivery.

    The pak modifies Buildings_Houses.uexp by shrinking each depot row's
    Materials TMap from 5 entries to 1 entry (Sand=1). The .uasset's
    Export[0].SerialSize is updated to match. After installation, the
    architect blueprint price stays the same — only the construction
    delivery requirements change.

    Args:
      output_pak_path:  Where to write the .pak file (e.g.
                        ~/Motor Town/Content/Paks/ZZZ_FrogModFreeDepots_P.pak).
      vanilla_uasset:   Optional in-memory vanilla Buildings_Houses.uasset
                        bytes. If omitted, reads from the bundled vanilla
                        copy (data/vanilla/Buildings/) or the user's
                        unpacked folder.
      vanilla_uexp:     Same, for Buildings_Houses.uexp.

    Returns:
      {success: bool, pak_path: str, pak_size: int,
       targets_modified: List[str], bytes_removed: int}
       — or {success: False, error: str} on failure.
    """
    # Lazy-import the pak writer to avoid a circular import in the
    # parsers package's __init__.
    from parsers.pak_writer import write_pak

    if vanilla_uasset is None or vanilla_uexp is None:
        src_dir = _resolve_buildings_source_dir()
        if not src_dir:
            return {
                'success': False,
                'error': 'Vanilla Buildings_Houses files not available. '
                         'The editor usually ships these in '
                         'data/vanilla/Buildings/.'
            }
        with open(os.path.join(src_dir, 'Buildings_Houses.uasset'), 'rb') as f:
            vanilla_uasset = f.read()
        with open(os.path.join(src_dir, 'Buildings_Houses.uexp'), 'rb') as f:
            vanilla_uexp = f.read()

    # Apply target shrinks in descending count_offset order so earlier
    # modifications don't shift later target offsets.
    new_uexp = vanilla_uexp
    targets_done: List[str] = []
    total_shrink = 0
    for tgt in sorted(DEPOT_TARGETS, key=lambda t: -t['count_offset']):
        before = len(new_uexp)
        try:
            new_uexp = shrink_materials_tmap_to_sand(
                new_uexp, tgt['count_offset'], tgt['vanilla_count'])
        except ValueError as exc:
            return {
                'success': False,
                'error': (
                    f'Layout mismatch for {tgt["name"]}: {exc}. '
                    f'Game version may have changed. Update '
                    f'DEPOT_TARGETS in uexp_buildings_dt.py.'),
            }
        total_shrink += before - len(new_uexp)
        targets_done.append(tgt['name'])

    # Update .uasset Export[0].SerialSize
    vanilla_serial = struct.unpack_from(
        '<q', vanilla_uasset, EXPORT_SERIAL_SIZE_OFFSET)[0]
    new_serial = vanilla_serial - total_shrink
    new_uasset = bytearray(vanilla_uasset)
    struct.pack_into('<q', new_uasset, EXPORT_SERIAL_SIZE_OFFSET, new_serial)
    new_uasset = bytes(new_uasset)

    # Stage the files in a temp directory mirroring the pak's internal
    # path structure: MotorTown/Content/DataAsset/Buildings/...
    pak_dir = os.path.dirname(os.path.abspath(output_pak_path))
    os.makedirs(pak_dir, exist_ok=True)
    stage_root = os.path.join(pak_dir, '.frogmod_freedepots_staging')
    if os.path.exists(stage_root):
        shutil.rmtree(stage_root, ignore_errors=True)
    stage_dir = os.path.join(
        stage_root, 'MotorTown', 'Content', 'DataAsset', 'Buildings')
    os.makedirs(stage_dir, exist_ok=True)
    try:
        with open(os.path.join(stage_dir, 'Buildings_Houses.uasset'), 'wb') as f:
            f.write(new_uasset)
        with open(os.path.join(stage_dir, 'Buildings_Houses.uexp'), 'wb') as f:
            f.write(new_uexp)

        # Pack. write_pak preserves the directory name as the pak's
        # root, so we point it at MotorTown/ inside the staging tree.
        pack_root = os.path.join(stage_root, 'MotorTown')
        if os.path.exists(output_pak_path):
            os.remove(output_pak_path)
        result = write_pak(pack_root, output_pak_path)

        return {
            'success': True,
            'pak_path': output_pak_path,
            'pak_size': result.get('pak_size', 0),
            'targets_modified': targets_done,
            'bytes_removed': total_shrink,
            'serial_size_before': vanilla_serial,
            'serial_size_after': new_serial,
        }
    finally:
        # Clean up staging
        if os.path.exists(stage_root):
            shutil.rmtree(stage_root, ignore_errors=True)
