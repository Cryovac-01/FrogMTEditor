"""Cryovac Free Depot Construction — mod-pak based (v8, 2026-05-08).

Replaces the v7.x runtime Lua force-complete approach with a clean
mod-pak that ships a modified Buildings_Houses.uexp/.uasset. Both
Depot_01 and Depot_02 are reduced to a single-Sand-cargo construction
requirement; the architect blueprint price is unchanged.

History
-------
v7.2.x  .pak modification of Buildings DT — earlier test concluded
        "doesn't work" but the test was buggy. We've since proven
        .uexp overrides via mod-pak DO take effect on this game.
v7.3-v7.32 Runtime Lua force-complete chain — the long iteration
        through the UE4SS Lua minefield (FName-from-string crashes,
        TArray:Add no-ops, freeze-on-spawn, BeginPlay overlap crashes,
        rotation arg order, etc). Eventually got an in-session
        working depot but the runtime spawn doesn't persist across
        save+reload because the engine's natural completion code
        never runs.
v7.33   Final runtime-Lua state — fully working in-session, no
        persistence. Retired in favor of v8.
v8 (this file): direct mod-pak modification of Buildings_Houses.uexp.
        Each depot row's Materials TMap is shrunk from 5 entries to
        1 entry (Sand=1). Player drops one Sand cargo, the engine's
        natural completion code fires end-to-end including save
        persistence. Confirmed working in-game with reload survival.

Mechanism
---------
The Materials TMap binary layout in the .uexp:
    [int32 count]
    count × [int32 name_idx, int32 name_inst, int32 value]

Vanilla Depot_02 has 5 entries: Concrete=15, Sand=15,
WoodPlank_14ft_5t=4, lHBeam_6m=3, PlasticPipes_6m=3.

We shrink to 1 entry: Sand=1. The .uasset's Export[0].SerialSize is
also updated to match the new (shorter) .uexp.

Why "Sand=1" specifically: of the five vanilla materials, only Sand
is trivial to acquire (single-step production at any Sand pickup).
The other four require multi-step production chains that defeat the
"free construction" goal. The engine completion check is gated on
DeliveredMaterials.length() matching Steps[currentStep].Materials.length(),
so requiring just Sand=1 lets the natural completion fire after a
single delivery instead of needing all five materials.

Output
------
deploy() generates ZZZ_FrogModFreeDepots_P.pak and places it in the
user's configured pak_output_dir (File > Customize > Pak output folder).
The user drops the pak into <Motor Town>/Content/Paks/.

A tiny no-op Lua stub is also written to the lua_output_dir for
backward compat with the existing UE4SS-Mods workflow — the stub
just logs that the real work is done by the pak.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

from . import register, DEFAULT_OUTPUT_DIR, Setting, ModeOption
from ._shared import write_mod_folder


MOD_NAME = 'CryovacFreeDepotConstruction'
UI_TITLE = 'Free Depot Construction'

UI_DESCRIPTION = (
    "<b>Reduces both depot construction sites to require only ONE Sand "
    "cargo delivery.</b> The architect blueprint price is unchanged — "
    "only the on-site delivery requirements drop.\n\n"

    "<b>How it works (v8, 2026-05-08):</b> ships a modified "
    "<code>Buildings_Houses.uexp</code> inside a mod-pak. Each depot "
    "row's Materials TMap is shrunk from 5 entries to 1 (Sand=1). When "
    "the player drops a single Sand cargo at the construction site, the "
    "game's <i>natural</i> completion code runs end-to-end — including "
    "save persistence. The depot persists across reload exactly like a "
    "depot that completed via the vanilla 39-cargo flow.\n\n"

    "<b>Why this is better than the previous v7.x runtime Lua mod:</b> "
    "the v7.x mod force-completed construction by manually applying state "
    "writes from Lua, which worked in-session but did not persist on "
    "reload. v8's natural-completion path is recorded by the engine's "
    "own save logic, so reload restores the operational depot correctly.\n\n"

    "<b>Output:</b> a pak file is written to your configured "
    "<i>Pak output folder</i> (File &gt; Customize). Default name: "
    "<code>ZZZ_FrogModFreeDepots_P.pak</code>. Drop it in "
    "<code>&lt;Motor Town&gt;/Content/Paks/</code> and launch the game.\n\n"

    "<b>Garages:</b> in vanilla, garages already build instantly (no "
    "construction-cost requirements). No mod is needed for them."
)


# Settings: just one — should the pak overwrite an existing file in the
# configured output dir without prompting? Most users want this; an
# explicit toggle gives the careful user a check.
SETTINGS: List[Setting] = [
    Setting(
        key='overwrite_existing',
        label='Overwrite existing pak file',
        kind='bool',
        default=True,
        tooltip=(
            'If a ZZZ_FrogModFreeDepots_P.pak already exists in your '
            'Pak output folder, replace it. Untick to abort the deploy '
            'instead of overwriting.'
        ),
    ),
]

DEFAULT_CONFIG: Dict[str, Any] = {
    'overwrite_existing': True,
}


# Output filename. Keeps the ZZZ_ prefix (loads after Cryovac's
# ZZZ_FrogMod_P.pak alphabetically, so any DT conflict resolves to
# our depot mod) and the _P.pak suffix UE's pak loader looks for.
_DEFAULT_PAK_NAME = 'ZZZ_FrogModFreeDepots_P.pak'


def generate_main_lua(config: Dict[str, Any]) -> str:
    """No-op Lua stub. The actual mod runs entirely from the pak's
    Buildings_Houses modifications — UE4SS Lua isn't involved at all
    in v8. We still emit a tiny stub so the UE4SS Mods folder layout
    looks normal and any leftover mods.txt entries don't break."""
    return (
        '-- Cryovac Free Depot Construction (v8, mod-pak based)\n'
        '--\n'
        '-- This Lua file is intentionally a no-op. The actual mod runs\n'
        '-- from a mod-pak that modifies Buildings_Houses.uexp directly.\n'
        '-- Look for ZZZ_FrogModFreeDepots_P.pak in your configured Pak\n'
        '-- output folder, and drop it in <Motor Town>/Content/Paks/.\n'
        '\n'
        'print("[CryovacFreeDepotConstruction] v8 stub loaded — '
        'real work is done by ZZZ_FrogModFreeDepots_P.pak")\n'
    )


def generate_readme(config: Dict[str, Any]) -> str:
    body = (
        "Reduces depot construction (Depot_01 and Depot_02) to a single\n"
        "Sand cargo delivery. The architect blueprint cost is unchanged.\n\n"

        "OUTPUT FILE\n"
        "-----------\n"
        "  ZZZ_FrogModFreeDepots_P.pak\n\n"
        "Generated in your configured Pak output folder (File > Customize).\n"
        "Drop the pak into <Motor Town>/Content/Paks/.\n\n"

        "WHAT THIS MOD DOES\n"
        "------------------\n"
        "Modifies Buildings_Houses.uexp inside the mod-pak so that each\n"
        "depot row's Materials TMap has only one entry: Sand=1.\n\n"
        "  Depot_01 vanilla: Concrete=10, Sand=10, WoodPlank=2,\n"
        "                    H-Beam=2, Plastic Pipes=2  (5 materials)\n"
        "  Depot_01 modded:  Sand=1                       (1 material)\n\n"
        "  Depot_02 vanilla: Concrete=15, Sand=15, WoodPlank=4,\n"
        "                    H-Beam=3, Plastic Pipes=3  (5 materials)\n"
        "  Depot_02 modded:  Sand=1                       (1 material)\n\n"

        "WHY ONLY SAND\n"
        "-------------\n"
        "Of the five vanilla depot materials, only Sand is trivial to\n"
        "acquire. The other four (Concrete, WoodPlank_14ft_5t, lHBeam_6m,\n"
        "PlasticPipes_6m) all involve multi-step production chains that\n"
        "would defeat the 'free construction' goal.\n\n"
        "The Materials TMap is shrunk to a single key (Sand) rather than\n"
        "left with 4 zero-required keys, because the engine's completion\n"
        "check is gated on DeliveredMaterials.length() matching Materials\n"
        ".length(). With 5 keys but only Sand delivered, the lengths\n"
        "don't match and the construction never completes (we tested\n"
        "this — see v3 of the test pak in the project history). Shrinking\n"
        "the TMap lets the natural completion fire after a single delivery.\n\n"

        "PERSISTENCE\n"
        "-----------\n"
        "Once Sand is delivered, the engine's natural construction\n"
        "completion code runs — including the save state update. The\n"
        "operational depot persists across save+reload exactly as if it\n"
        "had been built via the vanilla 39-cargo flow.\n\n"

        "GARAGES\n"
        "-------\n"
        "Garages (Garage_01 / LargeGarage_01) already build instantly\n"
        "in vanilla — they have no construction-cost materials. No mod\n"
        "needed for them.\n\n"

        "INSTALLATION\n"
        "------------\n"
        "1. The editor produces ZZZ_FrogModFreeDepots_P.pak.\n"
        "2. Copy it to your Motor Town install:\n"
        "     <Motor Town install>\\MotorTown\\Content\\Paks\\\n"
        "3. Launch the game. Visit the architect, buy a Depot blueprint,\n"
        "   place it on a vacant lot. Construction screen now shows only\n"
        "   Sand 0/1.\n"
        "4. Drop one Sand cargo at the construction site. Construction\n"
        "   completes; the operational depot spawns.\n\n"

        "UNINSTALLING\n"
        "------------\n"
        "Delete ZZZ_FrogModFreeDepots_P.pak from <Motor Town>/Content/Paks/.\n"
        "The depots will revert to their vanilla 5-material requirements.\n"
        "Existing depots that were already constructed remain operational.\n\n"

        "MULTIPLAYER\n"
        "-----------\n"
        "The pak modifies a server-authoritative DataTable. Install on\n"
        "the host or dedicated server. Other players don't need the pak\n"
        "(it's read by whichever side authored the construction events).\n"
    )
    # render_install_readme expects a specific structure — but we want a
    # custom format here since this isn't a Lua mod. Inline the basic
    # README format.
    return (
        f'{MOD_NAME}\n'
        f'{"=" * len(MOD_NAME)}\n\n'
        f'{body}\n'
    )


def _resolve_pak_output_dir() -> str:
    """Look up the user's configured Pak output folder. Falls back to
    DEFAULT_OUTPUT_DIR if not set or missing.

    The user sets this via File > Customize > Pak output folder.
    """
    try:
        from customize_settings import load as _load_cs
        cfg = _load_cs()
        pak_dir = (cfg.get('pak_output_dir') or '').strip()
        if pak_dir and os.path.isdir(pak_dir):
            return pak_dir
    except Exception:
        pass
    # Fallback to the editor's default paks dir (one level above
    # lua_mod_output, alongside the workspace's other generated paks).
    src_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proj_root = os.path.dirname(src_root)
    return os.path.join(proj_root, 'data', 'default_paks')


def deploy(config: Dict[str, Any], output_dir: str = None) -> Dict[str, Any]:
    """Deploy the Free Depot Construction mod-pak.

    output_dir is the LUA mod folder (where we drop a no-op stub for
    backward compat). The actual pak goes to the user's configured
    pak_output_dir.

    Returns:
      {success, lua_path?, pak_path?, pak_size?, message?, error?}
    """
    out_dir = output_dir or DEFAULT_OUTPUT_DIR

    # 1. Write the no-op Lua mod folder (so the LUA Scripts panel still
    # has something to point at). Doesn't affect gameplay.
    lua_result = write_mod_folder(
        mod_name=MOD_NAME,
        output_dir=out_dir,
        main_lua=generate_main_lua(config),
        readme=generate_readme(config),
        mod_info={
            'strategy': 'mod_pak_buildings_houses_shrink',
            'pak_filename': _DEFAULT_PAK_NAME,
            'targets': ['Depot_01', 'Depot_02'],
            'replaces_runtime_lua_v7': True,
        },
    )
    if not lua_result.get('success'):
        return {
            'success': False,
            'error': f'Lua stub deploy failed: {lua_result.get("error")}'
        }

    # 2. Generate the pak in the user's configured pak_output_dir.
    pak_dir = _resolve_pak_output_dir()
    os.makedirs(pak_dir, exist_ok=True)
    pak_path = os.path.join(pak_dir, _DEFAULT_PAK_NAME)

    # Honor the overwrite_existing setting
    if os.path.exists(pak_path) and not config.get('overwrite_existing', True):
        return {
            'success': False,
            'lua_path': lua_result.get('path'),
            'error': (
                f'Pak file already exists at {pak_path}. Tick '
                f'"Overwrite existing pak file" or remove the existing '
                f'file manually.'
            ),
        }

    # Lazy import to keep this file's imports light; parsers package
    # has its own sys.path setup.
    import sys as _sys
    parser_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if parser_dir not in _sys.path:
        _sys.path.insert(0, parser_dir)
    from parsers.uexp_buildings_dt import generate_free_depots_pak

    pak_result = generate_free_depots_pak(pak_path)
    if not pak_result.get('success'):
        return {
            'success': False,
            'lua_path': lua_result.get('path'),
            'error': f'Pak generation failed: {pak_result.get("error")}',
        }

    return {
        'success': True,
        'lua_path': lua_result.get('path'),
        'pak_path': pak_result['pak_path'],
        'pak_size': pak_result['pak_size'],
        'targets_modified': pak_result.get('targets_modified', []),
        'bytes_removed': pak_result.get('bytes_removed', 0),
        'message': (
            f'Generated {os.path.basename(pak_result["pak_path"])} '
            f'({pak_result["pak_size"]} bytes). Copy it to '
            f'<Motor Town>/Content/Paks/ to install.'
        ),
    }


import sys as _sys
register(_sys.modules[__name__])
