"""Rebuild all website template engines as vanilla-based engine assets."""
from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, 'src')

from api.routes import (  # noqa: E402
    ENGINE_DISPLAY_NAMES,
    ENGINE_WEIGHTS,
    TEMPLATES_ENGINE_DIR,
    ENGINES_DT_BASE,
    _fallback_weight,
    _patch_datatable_serial_size,
    _register_engine_datatable_entry,
)
from engine_audio import (  # noqa: E402
    ENGINE_AUDIO_MANIFEST_PATH,
    ENGINE_AUDIO_OVERRIDE_PATH,
    load_engine_audio_overrides,
    sync_enabled_sound_overrides,
    update_primary_engine_sound_asset,
)
from engine_validation import audit_engine_value_consistency, validate_engine_generation_tree  # noqa: E402
from engine_pricing import build_torque_price_model, recommend_price_from_torque  # noqa: E402
from parsers.pak_reader import read_pak  # noqa: E402
from parsers.pak_writer import write_pak  # noqa: E402
from parsers.vanilla_engine_builder import (  # noqa: E402
    materialize_template_files,
    rebuild_template_files,
    resolve_structure_donor_name,
)
from template_engines import load_template_specs, sort_key  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parent
VANILLA_ENGINE_DIR = PROJECT_ROOT / 'data' / 'vanilla' / 'Engine'
VANILLA_DT_BASE = PROJECT_ROOT / 'data' / 'vanilla' / 'DataTable' / 'Engines'
MOD_ENGINE_DIR = PROJECT_ROOT / 'data' / 'mod' / 'MotorTown' / 'Content' / 'Cars' / 'Parts' / 'Engine'
MOD_DT_DIR = PROJECT_ROOT / 'data' / 'mod' / 'MotorTown' / 'Content' / 'DataAsset' / 'VehicleParts'
GENERATOR_SCRIPT = PROJECT_ROOT / 'scripts' / 'create_templates.py'
MIN_SAFE_DIESEL_RPM = 1500.0

SOURCE_DONOR_BY_VARIANT = {
    'ice_standard': 'H2_30HP',
    'ice_compact': 'I4Sport_150HP',
    'diesel_hd': 'HeavyDuty_440HP',
    'bike': 'Bike_i4_100HP',
    'ev': 'Electric_300HP',
}


def _allowed_template_names() -> set[str]:
    """Return the curated website template set."""
    return set(ENGINE_WEIGHTS)


def _fuel_prefix(spec) -> str:
    if spec.variant == 'ev' or spec.fuel_type == 3:
        return '[E]'
    if spec.variant == 'diesel_hd' or spec.fuel_type == 2:
        return '[D]'
    return '[G]'


def _pack_shop_title(spec) -> str:
    return f'{_fuel_prefix(spec)} {spec.shop_title}'


def _diesel_runtime_props(gen, hp: float, rpm: float) -> dict[str, float]:
    effective_rpm = max(float(rpm), MIN_SAFE_DIESEL_RPM)
    return {
        'MaxTorque': gen.hp_to_torque_raw(hp, effective_rpm),
        'MaxRPM': effective_rpm,
        'StarterRPM': min(effective_rpm, 1500.0),
        'FuelConsumption': gen.fuel_consumption_for('', 'diesel_hd', hp),
    }


def _clear_engine_dir(engine_dir: Path) -> None:
    engine_dir.mkdir(parents=True, exist_ok=True)
    for subdir_name in ('Sound', 'TorqueCurve'):
        subdir = engine_dir / subdir_name
        if subdir.exists():
            shutil.rmtree(subdir)
    for child in engine_dir.iterdir():
        if child.is_file() and child.suffix in {'.uasset', '.uexp'}:
            child.unlink()


def _override_sound_asset(spec, overrides: dict[str, dict] | None = None) -> str | None:
    row = (overrides or {}).get(spec.name) or {}
    if row.get('enabled'):
        return row.get('override_sound_asset') or None
    return None


def _load_generator_module():
    spec = importlib.util.spec_from_file_location('template_generator_defs', GENERATOR_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Unable to load template generator: {GENERATOR_SCRIPT}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_template_definitions() -> dict[str, dict]:
    """Load the authoritative template specs from scripts/create_templates.py."""
    gen = _load_generator_module()
    definitions: dict[str, dict] = {}

    for name, hp, rpm, _sound in gen.ICE_STANDARD:
        definitions[name] = {
            'variant': 'ice_standard',
            'properties': gen.standard_props(name, hp, rpm),
        }

    for name, hp, rpm, _sound in gen.ICE_COMPACT:
        definitions[name] = {
            'variant': 'ice_compact',
            'properties': gen.compact_props(hp, rpm, name=name),
        }

    for name, hp, rpm, _sound in gen.DIESEL_HD:
        definitions[name] = {
            'variant': 'diesel_hd',
            'properties': gen.diesel_props(hp, rpm, name=name),
        }

    for name, hp, rpm, _sound in gen.BIKE:
        definitions[name] = {
            'variant': 'bike',
            'properties': gen.bike_props(hp, rpm, name=name),
        }

    for name, hp, max_rpm, torque_nm, power_kw, voltage_v in gen.EV:
        definitions[name] = {
            'variant': 'ev',
            'properties': gen.ev_props(name, hp, max_rpm, torque_nm, power_kw, voltage_v),
        }

    return definitions


def _audit_engine_dir(engine_dir: Path, label: str) -> None:
    gen = _load_generator_module()
    audit = audit_engine_value_consistency(
        str(engine_dir),
        standard_baseline=gen.STANDARD_BASELINE_PROPS,
        required_standard_heating_power=gen.STANDARD_HEATING_POWER,
        forbidden_standard_format_hint=gen.STANDARD_LEGACY_LAYOUT_FORMAT_HINT,
        compact_baseline=gen.COMPACT_BASELINE_PROPS,
        compact_outlier_signature=gen.COMPACT_OUTLIER_SIGNATURE,
        bike_baseline=gen.BIKE_BASELINE_PROPS,
        diesel_baseline=gen.DIESEL_BASELINE_PROPS,
        ev_baseline=gen.EV_BASELINE_PROPS,
        min_fuel_consumption=gen.MIN_SAFE_FUEL_CONSUMPTION,
    )
    if audit.get('legacy_bike_names'):
        preview = ', '.join(audit['legacy_bike_names'][:5])
        extra = '' if len(audit['legacy_bike_names']) <= 5 else f' (+{len(audit["legacy_bike_names"]) - 5} more)'
        print(f'{label} audit error: legacy bike layouts remain for {preview}{extra}')
    elif audit['warnings']:
        preview = '; '.join(audit['warnings'][:3])
        extra = '' if len(audit['warnings']) <= 3 else f' (+{len(audit["warnings"]) - 3} more)'
        print(f'{label} audit warnings: {preview}{extra}')
    if not audit['valid']:
        preview = '; '.join(audit['errors'][:6])
        extra = '' if len(audit['errors']) <= 6 else f' (+{len(audit["errors"]) - 6} more)'
        raise RuntimeError(f'{label} audit failed: {preview}{extra}')
    print(f'{label} audit passed ({audit["checked"]} engines checked)')


def _restore_template_sources() -> int:
    """Regenerate clean template .uexp sources from the authoritative definitions."""
    from parsers.uexp_engine import parse_engine, serialize_engine

    definitions = _load_template_definitions()
    allowed_names = _allowed_template_names()
    templates_dir = Path(TEMPLATES_ENGINE_DIR)
    os.makedirs(templates_dir, exist_ok=True)

    missing = sorted(name for name in allowed_names if name not in definitions)
    if missing:
        raise RuntimeError(f'Missing template definitions for: {", ".join(missing)}')

    for suffix in ('.uasset', '.uexp'):
        for path in templates_dir.glob(f'*{suffix}'):
            if path.stem not in allowed_names:
                path.unlink()

    restored = 0
    for name in sorted(allowed_names):
        definition = definitions[name]
        donor_name = SOURCE_DONOR_BY_VARIANT[definition['variant']]
        donor_path = VANILLA_ENGINE_DIR / f'{donor_name}.uexp'
        engine = parse_engine(donor_path.read_bytes())
        for key, value in definition['properties'].items():
            if key in engine.properties:
                engine.properties[key] = value
        (templates_dir / f'{name}.uexp').write_bytes(serialize_engine(engine))
        restored += 1

    return restored


def _copy_template_engines_to_mod(engine_dir: Path, specs,
                                  overrides: dict[str, dict] | None = None) -> int:
    copied = 0
    for spec in specs:
        output_uasset_path, _output_uexp_path = materialize_template_files(
            spec.name,
            spec.asset_name,
            spec.variant,
            TEMPLATES_ENGINE_DIR,
            str(VANILLA_ENGINE_DIR),
            str(engine_dir),
            donor_name=spec.donor_name,
            structure_donor_name=resolve_structure_donor_name(spec.variant, spec.donor_name, spec.hp),
            sound_dir=(spec.sound_dir or None),
        )
        override_sound_asset = _override_sound_asset(spec, overrides)
        if override_sound_asset:
            update_primary_engine_sound_asset(Path(output_uasset_path), override_sound_asset)
        copied += 1
    return copied


def rebuild_template_uassets(specs, overrides: dict[str, dict] | None = None) -> dict[str, int]:
    counts: dict[str, int] = {}
    for spec in specs:
        output_uasset_path, _output_uexp_path = rebuild_template_files(
            spec.name,
            spec.variant,
            TEMPLATES_ENGINE_DIR,
            str(VANILLA_ENGINE_DIR),
            TEMPLATES_ENGINE_DIR,
            donor_name=spec.donor_name,
            structure_donor_name=resolve_structure_donor_name(spec.variant, spec.donor_name, spec.hp),
            sound_dir=(spec.sound_dir or None),
        )
        override_sound_asset = _override_sound_asset(spec, overrides)
        if override_sound_asset:
            update_primary_engine_sound_asset(Path(output_uasset_path), override_sound_asset)
        counts[spec.donor_name] = counts.get(spec.donor_name, 0) + 1
    return counts


def rebuild_mod_datatable(specs) -> None:
    MOD_DT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(f'{VANILLA_DT_BASE}.uasset', MOD_DT_DIR / 'Engines.uasset')
    shutil.copy2(f'{VANILLA_DT_BASE}.uexp', MOD_DT_DIR / 'Engines.uexp')

    ua = (MOD_DT_DIR / 'Engines.uasset').read_bytes()
    ue = (MOD_DT_DIR / 'Engines.uexp').read_bytes()
    price_model = build_torque_price_model(specs)

    for spec in sorted(specs, key=sort_key):
        price = recommend_price_from_torque(price_model, spec.torque_nm)
        weight = ENGINE_WEIGHTS.get(spec.name) or _fallback_weight(spec.variant, spec.hp)
        ua, ue, _ = _register_engine_datatable_entry(
            ua,
            ue,
            spec.asset_name,
            _pack_shop_title(spec),
            price,
            weight,
            spec.variant,
            update_existing=False,
            description=spec.shop_subtitle,
        )

    ua = _patch_datatable_serial_size(ua, len(ue))
    (MOD_DT_DIR / 'Engines.uasset').write_bytes(ua)
    (MOD_DT_DIR / 'Engines.uexp').write_bytes(ue)


def _normalized_pak_path(raw: str) -> str:
    path = raw.strip()
    if path.lower().endswith('.pak'):
        path = path[:-4]
    if not path.endswith('_P'):
        path += '_P'
    return path + '.pak'


def pack_engine_only_mod(pack_path: str) -> dict[str, int | str]:
    """Pack only generated engine assets plus Engines DataTable."""
    pack_path = _normalized_pak_path(pack_path)
    staged_root = MOD_DT_DIR.parent.parent.parent
    validation = validate_engine_generation_tree(str(staged_root))
    if not validation['valid']:
        preview = '; '.join(validation['errors'][:6])
        extra = '' if len(validation['errors']) <= 6 else f' (+{len(validation["errors"]) - 6} more)'
        raise RuntimeError(f'Mod tree validation failed: {preview}{extra}')
    temp_dir = tempfile.mkdtemp(prefix='mte_full_')
    try:
        temp_mt = Path(temp_dir) / 'MotorTown'
        engine_dir = temp_mt / 'Content' / 'Cars' / 'Parts' / 'Engine'
        dt_dir = temp_mt / 'Content' / 'DataAsset' / 'VehicleParts'
        engine_dir.mkdir(parents=True, exist_ok=True)
        dt_dir.mkdir(parents=True, exist_ok=True)

        engine_files = 0
        for src in sorted(MOD_ENGINE_DIR.glob('*.uasset')):
            shutil.copy2(src, engine_dir / src.name)
            engine_files += 1
        for src in sorted(MOD_ENGINE_DIR.glob('*.uexp')):
            shutil.copy2(src, engine_dir / src.name)
            engine_files += 1
        sound_dir = MOD_ENGINE_DIR / 'Sound'
        if sound_dir.is_dir():
            for src in sorted(sound_dir.rglob('*')):
                if not src.is_file():
                    continue
                rel = src.relative_to(sound_dir)
                dst = engine_dir / 'Sound' / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                engine_files += 1

        for suffix in ('.uasset', '.uexp'):
            shutil.copy2(f'{ENGINES_DT_BASE}{suffix}', dt_dir / f'Engines{suffix}')

        result = write_pak(str(temp_mt), pack_path)
        pak = read_pak(pack_path)
        return {
            'output_path': pack_path,
            'engine_files': engine_files,
            'datatable_files': 2,
            'file_count': result['file_count'],
            'pak_size': result['pak_size'],
            'verified_entries': len(pak['entries']),
        }
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def summarize(specs, donor_counts: dict[str, int]) -> None:
    groups: dict[str, int] = {}
    for spec in specs:
        groups[spec.sort_group] = groups.get(spec.sort_group, 0) + 1

    print(f'Templates rebuilt: {len(specs)}')
    print('Shop groups:')
    for key in ('gas_bike', 'gas_car', 'gas_truck', 'diesel', 'ev'):
        print(f'  {key}: {groups.get(key, 0)}')
    print('Vanilla donors:')
    for donor_name, count in sorted(donor_counts.items(), key=lambda item: (-item[1], item[0])):
        print(f'  {donor_name}: {count}')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--pack-path', default='', help='Optional .pak output path')
    parser.add_argument('--exclude-bikes', action='store_true',
                        help='Exclude bike engines from the rebuilt mod tree and pak output')
    args = parser.parse_args()

    restored = _restore_template_sources()
    all_specs = load_template_specs(TEMPLATES_ENGINE_DIR, ENGINE_DISPLAY_NAMES)
    specs = [spec for spec in all_specs if not (args.exclude_bikes and spec.variant == 'bike')]
    overrides = load_engine_audio_overrides(ENGINE_AUDIO_OVERRIDE_PATH) if ENGINE_AUDIO_OVERRIDE_PATH.is_file() else {}

    donor_counts = rebuild_template_uassets(all_specs, overrides=overrides)
    _audit_engine_dir(Path(TEMPLATES_ENGINE_DIR), 'Template source')

    _clear_engine_dir(MOD_ENGINE_DIR)
    sound_sync = (
        sync_enabled_sound_overrides(ENGINE_AUDIO_MANIFEST_PATH, ENGINE_AUDIO_OVERRIDE_PATH)
        if ENGINE_AUDIO_MANIFEST_PATH.is_file()
        else {'synced_engines': 0, 'copied_assets': 0}
    )
    copied = _copy_template_engines_to_mod(MOD_ENGINE_DIR, specs, overrides=overrides)
    rebuild_mod_datatable(specs)
    _audit_engine_dir(MOD_ENGINE_DIR, 'Mod engine')

    summarize(specs, donor_counts)
    print(f'Template sources restored: {restored}')
    print(f'Mod engine files copied: {copied}')
    print(f'Enabled sound overrides synced: {sound_sync.get("synced_engines", 0)} engines, {sound_sync.get("copied_assets", 0)} audio assets')
    if args.exclude_bikes:
        print('Bike engines excluded from mod tree/pak output')
    print(f'Mod DataTable rebuilt at: {ENGINES_DT_BASE}.uasset/.uexp')

    if args.pack_path:
        result = pack_engine_only_mod(args.pack_path)
        print(f'Packed {result["file_count"]} files to {result["output_path"]}')
        print(f'Pak verified with {result["verified_entries"]} entries')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
