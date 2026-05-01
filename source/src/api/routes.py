"""
REST API routes for Frog Mod Editor.
"""
import json
import os
import glob
import shutil
import struct
import hashlib
import threading
import logging
from contextlib import nullcontext
from pathlib import Path
from typing import Dict, Any, List, Optional
import urllib.parse

from engine_pricing import build_torque_price_model, recommend_price_from_torque
from parsers.uasset import parse_uasset
from parsers.uexp_engine import (
    ENGINE_CANONICAL_PROPERTY_ORDER,
    ENGINE_VARIANT_PROPERTY_ORDER,
    EngineVariant,
    build_engine_display_entry,
    parse_engine,
    serialize_engine,
)
from parsers.uexp_tire import (
    TIRE_CANONICAL_PROPERTY_ORDER,
    build_tire_display_entry,
    choose_tire_layout,
    offroad_percent_to_grip_multiplier,
    parse_tire,
    serialize_tire,
)
from parsers.uexp_transmission import parse_transmission, serialize_transmission
from parsers.uexp_lsd import parse_lsd, serialize_lsd
from parsers.uexp_torquecurve import parse_torque_curve, serialize_torque_curve
from engine_audio import (
    ENGINE_AUDIO_MANIFEST_PATH,
    ENGINE_AUDIO_OVERRIDE_PATH,
    load_engine_audio_overrides,
    prepare_engine_audio_workspace as _prepare_engine_audio_workspace,
    resolve_sound_dir_override,
    save_engine_audio_overrides,
)

# Base paths
EXPORTS_BASE = r'C:\Program Files (x86)\Steam\steamapps\common\Motor Town\MotorTown\Content\Paks\Output\Exports'
DEFAULT_PAKS_DIR = r'C:\Program Files (x86)\Steam\steamapps\common\Motor Town\MotorTown\Content\Paks'
DEFAULT_CUSTOM_PAK_FILENAME = 'ZZZ_FrogMod_P.pak'
# All game data is bundled with the project
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MOD_ROOT             = os.path.join(_PROJECT_ROOT, 'data', 'mod')
MOD_BASE             = os.path.join(MOD_ROOT, 'MotorTown', 'Content', 'Cars', 'Parts')
VANILLA_BASE         = os.path.join(_PROJECT_ROOT, 'data', 'vanilla')
VANILLA_DT_BASE      = os.path.join(VANILLA_BASE, 'DataTable', 'Engines')
VANILLA_VEHICLEPARTS0_BASE = os.path.join(VANILLA_BASE, 'DataTable', 'VehicleParts0')
TEMPLATES_ENGINE_DIR = os.path.join(_PROJECT_ROOT, 'data', 'templates', 'Engine')
ENGINES_DT_BASE = os.path.join(MOD_ROOT, 'MotorTown', 'Content', 'DataAsset', 'VehicleParts', 'Engines')
MOD_VEHICLEPARTS0_BASE = os.path.join(MOD_ROOT, 'MotorTown', 'Content', 'DataAsset', 'VehicleParts', 'VehicleParts0')
BACKUP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'backups')
MOD_ENGINE_DIR = os.path.join(MOD_BASE, 'Engine')
MOD_TIRE_DIR = os.path.join(MOD_BASE, 'Tire')
MOD_TRANSMISSION_DIR = os.path.join(MOD_BASE, 'Transmission')
SITE_ENGINE_REGISTRY = os.path.join(MOD_ROOT, 'site_engines.json')
SITE_TIRE_REGISTRY = os.path.join(MOD_ROOT, 'site_tires.json')
MOD_WRITE_LOCK = threading.RLock()

# Part type -> (directory name, parser type)
PART_TYPES = {
    'Engine': ('Engine', 'engine'),
    'Transmission': ('Transmission', 'transmission'),
    'Tire': ('Tire', 'tire'),
    'LSD': ('LSD', 'lsd'),
    'TorqueCurve': ('Engine/TorqueCurve', 'torquecurve'),
}

_CUSTOM_ROW_TEMPLATE_CACHE: Optional[Dict[str, Dict[str, Any]]] = None
_ENGINE_PRICE_MODEL_CACHE: Dict[tuple[bool, int, float], Any] = {}
_ENGINE_TEMPLATE_CATALOG_CACHE: Optional[tuple[tuple[int, float], Dict[str, Any]]] = None
_ENGINE_FIELD_CATALOG_CACHE: Optional[tuple[tuple[int, float], Dict[str, Any]]] = None
_TIRE_FIELD_CATALOG_CACHE: Optional[tuple[tuple[int, float], Dict[str, Any]]] = None
_TIRE_TEMPLATE_CATALOG_CACHE: Optional[tuple[tuple[int, float], Dict[str, Any]]] = None
_TEMPLATE_AUDIT_CACHE: Optional[tuple[tuple[int, float], Dict[str, Any]]] = None
_VEHICLEPARTS0_CATALOG_CACHE: Dict[str, Dict[str, Any]] = {}
_COMPACT_TEMPLATE_BASELINE = {
    'Inertia': 2000.0,
    'StarterTorque': 200000.0,
    'FrictionCoulombCoeff': 180000.0,
    'FrictionViscosityCoeff': 450.0,
    'IdleThrottle': 0.005,
    'BlipThrottle': 3.0,
    'BlipDurationSeconds': 0.3,
}
_STANDARD_TEMPLATE_BASELINE = {
    'Inertia': 5000.0,
    'StarterTorque': 200000.0,
    'FrictionCoulombCoeff': 500000.0,
    'FrictionViscosityCoeff': 1000.0,
    'IdleThrottle': 0.0017,
    'HeatingPower': 0.5,
    'BlipThrottle': 10.0,
    'BlipDurationSeconds': 0.2,
    'AfterFireProbability': 1.0,
}
_STANDARD_REQUIRED_HEATING_POWER = 0.5
_STANDARD_FORBIDDEN_FORMAT_HINT = 'standard_v8_legacy'
_COMPACT_TEMPLATE_OUTLIER_SIGNATURE = {
    'Inertia': 5200.0,
    'StarterTorque': 200000.0,
    'FrictionCoulombCoeff': 430000.0,
    'FrictionViscosityCoeff': 1050.0,
    'IdleThrottle': 480.0,
}
_DIESEL_TEMPLATE_BASELINE = {
    'Inertia': 63000.0,
    'StarterTorque': 3000000.0,
    'StarterRPM': 1500.0,
    'FrictionCoulombCoeff': 2800000.0,
    'FrictionViscosityCoeff': 7000.0,
    'IdleThrottle': 0.017,
    'BlipThrottle': 5.0,
    'IntakeSpeedEfficiency': 1.0,
    'BlipDurationSeconds': 0.5,
    'MaxJakeBrakeStep': 3,
}
_EV_TEMPLATE_BASELINE = {
    'Inertia': 2000.0,
    'FrictionCoulombCoeff': 100.0,
    'FrictionViscosityCoeff': 100.0,
    'MaxRegenTorqueRatio': 0.3,
}
_BIKE_TEMPLATE_BASELINE = {
    'Inertia': 300.0,
    'StarterTorque': 60000.0,
    'StarterRPM': 1500.0,
    'FrictionCoulombCoeff': 45.0,
    'FrictionViscosityCoeff': 300.0,
    'IdleThrottle': 0.00019,
    'HeatingPower': 0.5,
    'BlipThrottle': 1.52,
    'BlipDurationSeconds': 3.0,
    'AfterFireProbability': 2.0,
}
_MIN_SAFE_TEMPLATE_FUEL_CONSUMPTION = 0.1
_CUSTOM_ROW_DONORS = {
    'bike': ['sportster120065HP'],
    'ice_standard': ['13b'],
    'ice_compact': ['20hyundai'],
    'diesel_hd': ['VW19TDI150HP'],
    'ev': ['EVWulingHongguangMiniEV'],
}
_NO_LEVEL_TAIL_DONORS = {
    'ice_standard': ['SmallBlock_140HP'],
    'ice_compact': ['I4_50HP', 'SmallBlock_90HP', 'H2_30HP'],
    'diesel_hd': ['HeavyDuty_260HP', 'Bus_140HP'],
    'ev': ['Electric_130HP'],
}


def _load_json_payload(path: str) -> Dict[str, Any]:
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            payload = json.load(f)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _engine_audio_manifest_state() -> Dict[str, Any]:
    manifest = _load_json_payload(str(ENGINE_AUDIO_MANIFEST_PATH))
    overrides = load_engine_audio_overrides(ENGINE_AUDIO_OVERRIDE_PATH)
    engines = []
    for row in manifest.get('engines', []) if isinstance(manifest.get('engines', []), list) else []:
        if not isinstance(row, dict):
            continue
        engine_name = str(row.get('engine_name') or '').strip()
        if not engine_name:
            continue
        merged = dict(row)
        override = overrides.get(engine_name) or {}
        merged['override_enabled'] = bool(override.get('enabled', False))
        merged['override_state'] = dict(override)
        engines.append(merged)
    engines.sort(key=lambda row: str(row.get('engine_name', '')).lower())
    enabled_count = sum(1 for row in engines if row.get('override_enabled'))
    return {
        'manifest_path': str(ENGINE_AUDIO_MANIFEST_PATH),
        'override_path': str(ENGINE_AUDIO_OVERRIDE_PATH),
        'prepared_engines': manifest.get('prepared_engines', len(engines)),
        'cloned_root_assets': manifest.get('cloned_root_assets', 0),
        'engine_count': len(engines),
        'enabled_count': enabled_count,
        'engines': engines,
        'overrides': overrides,
    }


def prepare_engine_audio_workspace() -> Dict[str, Any]:
    return _prepare_engine_audio_workspace(TEMPLATES_ENGINE_DIR, ENGINE_DISPLAY_NAMES)


def get_engine_audio_manifest() -> Dict[str, Any]:
    return _engine_audio_manifest_state()


def set_engine_audio_override(data: Dict[str, Any]) -> Dict[str, Any]:
    engine_name = str(data.get('engine_name') or data.get('name') or '').strip()
    if not engine_name:
        return {'error': 'No engine name specified'}

    enabled = bool(data.get('enabled', True))
    override_sound_dir = str(data.get('override_sound_dir') or '').strip() or None
    state = _engine_audio_manifest_state()
    overrides = dict(state.get('overrides') or {})
    row = dict(overrides.get(engine_name) or {})

    manifest_row = next((row for row in state.get('engines', []) if row.get('engine_name') == engine_name), None)
    if not override_sound_dir:
        override_sound_dir = (
            row.get('override_sound_dir')
            or (manifest_row or {}).get('override_sound_dir')
            or engine_name
        )

    row.update({
        'enabled': enabled,
        'override_sound_dir': override_sound_dir,
    })
    if manifest_row:
        row.setdefault('vanilla_sound_asset', manifest_row.get('vanilla_sound_asset'))
        row.setdefault('override_sound_asset', manifest_row.get('override_sound_asset'))
        row.setdefault('sound_profile', manifest_row.get('sound_profile'))
        row.setdefault('variant', manifest_row.get('variant'))

    overrides[engine_name] = row
    save_engine_audio_overrides(overrides, ENGINE_AUDIO_OVERRIDE_PATH)
    state = _engine_audio_manifest_state()
    return {
        'success': True,
        'engine_name': engine_name,
        'override': state.get('overrides', {}).get(engine_name, row),
        'manifest_path': state['manifest_path'],
        'override_path': state['override_path'],
        'enabled_count': state['enabled_count'],
    }


def _live_state_files() -> List[str]:
    """Return the generated-part files that define the public site's live state."""
    paths: List[str] = []
    for registry_path in (SITE_ENGINE_REGISTRY, SITE_TIRE_REGISTRY):
        if os.path.isfile(registry_path):
            paths.append(registry_path)
    for name in _prune_site_engine_registry():
        for ext in ('.uasset', '.uexp'):
            path = os.path.join(MOD_ENGINE_DIR, name + ext)
            if os.path.isfile(path):
                paths.append(path)
    for name in _prune_site_tire_registry():
        for ext in ('.uasset', '.uexp'):
            path = os.path.join(MOD_TIRE_DIR, name + ext)
            if os.path.isfile(path):
                paths.append(path)
    for suffix in ('.uasset', '.uexp'):
        for dt_base in (ENGINES_DT_BASE, MOD_VEHICLEPARTS0_BASE):
            dt_path = dt_base + suffix
            if os.path.isfile(dt_path):
                paths.append(dt_path)
    return paths


def _current_live_state() -> Dict[str, Any]:
    """Return a deterministic fingerprint for optimistic concurrency."""
    digest = hashlib.sha1()
    engine_names = _prune_site_engine_registry()
    tire_names = _prune_site_tire_registry()
    engine_count = len(engine_names)
    tire_count = len(tire_names)
    for path in _live_state_files():
        rel = os.path.relpath(path, _PROJECT_ROOT).replace('\\', '/')
        stat = os.stat(path)
        digest.update(rel.encode('utf-8'))
        digest.update(f'{stat.st_size}:{stat.st_mtime_ns}'.encode('ascii'))
    return {
        'version': digest.hexdigest()[:16],
        'engine_count': engine_count,
        'tire_count': tire_count,
        'part_count': engine_count + tire_count,
    }


def _check_live_version(expected_version: str | None) -> Optional[Dict[str, Any]]:
    """Return current live state when the caller is stale, else None."""
    if not expected_version:
        return None
    live = _current_live_state()
    if live['version'] != expected_version:
        return live
    return None


def _restore_backup(src: Optional[str], dest: str) -> None:
    """Best-effort restore helper for rollback paths."""
    if src and os.path.isfile(src):
        shutil.copy2(src, dest)


def _load_site_name_registry(registry_path: str, payload_key: str) -> List[str]:
    """Return a deduplicated list from one site registry file."""
    if not os.path.isfile(registry_path):
        return []
    try:
        with open(registry_path, 'r', encoding='utf-8') as f:
            payload = json.load(f)
        names = payload.get(payload_key, [])
        seen = set()
        clean: List[str] = []
        for raw in names:
            name = str(raw).strip()
            if not name or name in seen:
                continue
            seen.add(name)
            clean.append(name)
        return clean
    except Exception:
        return []


def _save_site_name_registry(registry_path: str, payload_key: str, names: List[str]) -> None:
    """Persist one site registry file."""
    os.makedirs(os.path.dirname(registry_path), exist_ok=True)
    unique = []
    seen = set()
    for raw in names:
        name = str(raw).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        unique.append(name)
    with open(registry_path, 'w', encoding='utf-8') as f:
        json.dump({payload_key: unique}, f, indent=2)


def _load_site_engine_registry() -> List[str]:
    """Return the site-visible user-generated engine names."""
    return _load_site_name_registry(SITE_ENGINE_REGISTRY, 'engines')


def _save_site_engine_registry(names: List[str]) -> None:
    """Persist the site-visible user-generated engine names."""
    _save_site_name_registry(SITE_ENGINE_REGISTRY, 'engines', names)


def _load_site_tire_registry() -> List[str]:
    """Return the site-visible user-generated tire names."""
    return _load_site_name_registry(SITE_TIRE_REGISTRY, 'tires')


def _save_site_tire_registry(names: List[str]) -> None:
    """Persist the site-visible user-generated tire names."""
    _save_site_name_registry(SITE_TIRE_REGISTRY, 'tires', names)


def _prune_site_engine_registry() -> List[str]:
    """Drop registry entries whose engine files are gone."""
    names = _load_site_engine_registry()
    keep = [
        name for name in names
        if os.path.isfile(os.path.join(MOD_ENGINE_DIR, name + '.uasset'))
        and os.path.isfile(os.path.join(MOD_ENGINE_DIR, name + '.uexp'))
    ]
    if keep != names:
        _save_site_engine_registry(keep)
    return keep


def _is_site_engine(name: str) -> bool:
    return name in set(_load_site_engine_registry())


def _register_site_engine(name: str) -> None:
    names = _prune_site_engine_registry()
    if name not in names:
        names.append(name)
        _save_site_engine_registry(names)


def _unregister_site_engine(name: str) -> None:
    names = [n for n in _load_site_engine_registry() if n != name]
    _save_site_engine_registry(names)


def _template_engine_files_and_stamp() -> tuple[List[str], tuple[int, float]]:
    template_files = sorted(glob.glob(os.path.join(TEMPLATES_ENGINE_DIR, '*.uexp')))
    latest_mtime = max((os.path.getmtime(path) for path in template_files), default=0.0)
    return template_files, (len(template_files), latest_mtime)


def _tire_template_sources() -> List[tuple[str, str]]:
    return [
        ('vanilla', os.path.join(VANILLA_BASE, 'Tire')),
    ]


def _tire_template_files_and_stamp() -> tuple[Dict[str, List[str]], tuple[int, float]]:
    source_files: Dict[str, List[str]] = {}
    total_files = 0
    latest_mtime = 0.0

    for source, base_dir in _tire_template_sources():
        files = sorted(glob.glob(os.path.join(base_dir, '*.uexp'))) if os.path.isdir(base_dir) else []
        if files:
            source_files[source] = files
        total_files += len(files)
        latest_mtime = max(latest_mtime, max((os.path.getmtime(path) for path in files), default=0.0))

    return source_files, (total_files, latest_mtime)


def _extend_ordered_names(target: List[str], seen: set[str], names: List[str]) -> None:
    for name in names:
        if name not in seen:
            seen.add(name)
            target.append(name)


def _load_engine_field_catalog() -> Dict[str, Any]:
    global _ENGINE_FIELD_CATALOG_CACHE

    template_files, cache_key = _template_engine_files_and_stamp()
    if _ENGINE_FIELD_CATALOG_CACHE and _ENGINE_FIELD_CATALOG_CACHE[0] == cache_key:
        return _ENGINE_FIELD_CATALOG_CACHE[1]

    all_properties: List[str] = list(ENGINE_CANONICAL_PROPERTY_ORDER)
    all_seen: set[str] = set(all_properties)
    variants: Dict[str, Dict[str, Any]] = {
        variant_key: {
            'properties': list(property_names),
        }
        for variant_key, property_names in ENGINE_VARIANT_PROPERTY_ORDER.items()
    }
    templates: Dict[str, List[str]] = {}

    for file_path in template_files:
        name = os.path.splitext(os.path.basename(file_path))[0]
        try:
            with open(file_path, 'rb') as f:
                engine = parse_engine(f.read())
        except Exception:
            continue

        supported_properties = list(engine.properties.keys())
        templates[name] = supported_properties
        _extend_ordered_names(all_properties, all_seen, supported_properties)

        variant_info = variants.setdefault(engine.variant.value, {'properties': []})
        variant_seen = set(variant_info['properties'])
        _extend_ordered_names(variant_info['properties'], variant_seen, supported_properties)

    catalog = {
        'all_properties': all_properties,
        'variants': variants,
        'templates': templates,
    }
    _ENGINE_FIELD_CATALOG_CACHE = (cache_key, catalog)
    return catalog


def _load_tire_field_catalog() -> Dict[str, Any]:
    global _TIRE_FIELD_CATALOG_CACHE

    source_files, cache_key = _tire_template_files_and_stamp()
    if _TIRE_FIELD_CATALOG_CACHE and _TIRE_FIELD_CATALOG_CACHE[0] == cache_key:
        return _TIRE_FIELD_CATALOG_CACHE[1]

    all_properties: List[str] = list(TIRE_CANONICAL_PROPERTY_ORDER)
    all_seen: set[str] = set(all_properties)
    groups: Dict[str, Dict[str, Any]] = {}
    template_properties: Dict[str, List[str]] = {}
    layouts: Dict[tuple[str, ...], Dict[str, Any]] = {}
    header_layouts: Dict[str, Dict[str, Any]] = {}

    for source, files in source_files.items():
        for file_path in files:
            name = os.path.splitext(os.path.basename(file_path))[0]
            try:
                with open(file_path, 'rb') as f:
                    tire = parse_tire(f.read())
            except Exception:
                continue

            props = list(tire.property_order)
            template_path = f'{source}/Tire/{name}'
            template_properties[template_path] = props
            _extend_ordered_names(all_properties, all_seen, props)

            group_key, group_label = _classify_tire_group(name)
            group = groups.setdefault(group_key, {
                'label': group_label,
                'properties': [],
                '_seen': set(),
            })
            _extend_ordered_names(group['properties'], group['_seen'], props)

            layout_key = tuple(props)
            layout_info = layouts.setdefault(layout_key, {
                'default_header': tire.header_bytes,
                'group_headers': {},
                'examples': [],
            })
            layout_info['group_headers'].setdefault(group_key, tire.header_bytes)
            if len(layout_info['examples']) < 3:
                layout_info['examples'].append({
                    'source': source,
                    'name': name,
                    'group_key': group_key,
                })
            header_layouts.setdefault(tire.header_bytes.hex(), {
                'layout': layout_key,
                'group_key': group_key,
                'source': source,
                'name': name,
            })

    clean_groups = {
        key: {
            'label': value['label'],
            'properties': list(value['properties']),
        }
        for key, value in groups.items()
    }
    catalog = {
        'all_properties': all_properties,
        'groups': clean_groups,
        'templates': template_properties,
        'layouts': layouts,
        'header_layouts': header_layouts,
    }
    _TIRE_FIELD_CATALOG_CACHE = (cache_key, catalog)
    return catalog


def _is_blank_optional_value(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _build_complete_engine_properties(engine) -> Dict[str, Any]:
    catalog = _load_engine_field_catalog()
    known_properties = list(catalog.get('all_properties') or engine.properties.keys())
    display_properties = engine.to_display_dict()
    ordered: Dict[str, Any] = {}
    seen: set[str] = set()
    supported = set(engine.properties.keys())

    for key in known_properties:
        if key in display_properties:
            ordered[key] = display_properties[key]
        else:
            ordered[key] = build_engine_display_entry(key, None, editable=False)
        if key not in supported:
            ordered[key]['editable'] = False
        seen.add(key)

    for key, value in display_properties.items():
        if key not in seen:
            ordered[key] = value

    return ordered


def _build_complete_tire_properties(tire) -> Dict[str, Any]:
    catalog = _load_tire_field_catalog()
    known_properties = list(catalog.get('all_properties') or tire.property_order)
    display_properties = tire.to_display_dict()
    ordered: Dict[str, Any] = {}
    seen: set[str] = set()
    supported = set(tire.properties.keys())

    for key in known_properties:
        ordered[key] = display_properties.get(key, build_tire_display_entry(key, None))
        if key not in supported:
            ordered[key]['editable'] = False
        seen.add(key)

    for key, value in display_properties.items():
        if key not in seen:
            ordered[key] = value

    return ordered


def _select_tire_header_bytes(tire, target_layout: tuple[str, ...], *,
                              tire_field_catalog: Optional[Dict[str, Any]] = None,
                              preferred_group_key: Optional[str] = None) -> bytes:
    if tuple(tire.property_order) == tuple(target_layout):
        return tire.header_bytes

    tire_field_catalog = tire_field_catalog or _load_tire_field_catalog()
    layout_info = (tire_field_catalog.get('layouts') or {}).get(tuple(target_layout))
    if not layout_info:
        raise ValueError(f'No known tire header matches layout: {", ".join(target_layout)}')

    group_headers = layout_info.get('group_headers') or {}
    if preferred_group_key and preferred_group_key in group_headers:
        return group_headers[preferred_group_key]

    current_header_info = (tire_field_catalog.get('header_layouts') or {}).get(tire.header_bytes.hex())
    current_group_key = current_header_info.get('group_key') if current_header_info else None
    if current_group_key and current_group_key in group_headers:
        return group_headers[current_group_key]

    if group_headers:
        return next(iter(group_headers.values()))

    default_header = layout_info.get('default_header')
    if default_header:
        return default_header
    raise ValueError(f'No tire header exemplar available for layout: {", ".join(target_layout)}')


def _apply_tire_property_changes(tire, modified_props: Dict[str, Any], *,
                                 tire_field_catalog: Optional[Dict[str, Any]] = None,
                                 preferred_group_key: Optional[str] = None) -> tuple[bytes, int]:
    tire_field_catalog = tire_field_catalog or _load_tire_field_catalog()
    known_properties = set(tire_field_catalog.get('all_properties') or ())
    current_values = dict(tire.properties)
    target_values = dict(current_values)
    current_keys = set(current_values)
    actual_changes = 0

    for key, raw_value in modified_props.items():
        if _is_blank_optional_value(raw_value):
            continue
        if key not in current_keys and key not in known_properties:
            continue
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            raise ValueError(f'Invalid tire value for {key}: {raw_value!r}')
        if key == 'GripMultiplier':
            converted = offroad_percent_to_grip_multiplier(value)
            if converted is None:
                raise ValueError(f'Invalid tire value for {key}: {raw_value!r}')
            value = converted

        old_value = target_values.get(key)
        if old_value is None or float(old_value) != value:
            actual_changes += 1
        target_values[key] = value

    if actual_changes == 0:
        return serialize_tire(tire), 0

    target_layout = tuple(tire.property_order)
    if set(target_values) != current_keys:
        target_layout = choose_tire_layout(set(target_values), tire.property_order) or ()
        if not target_layout:
            requested = ', '.join(sorted(set(target_values) - current_keys)) or ', '.join(sorted(target_values))
            raise ValueError(f'Unsupported tire field combination: {requested}')

    tire.header_bytes = _select_tire_header_bytes(
        tire,
        target_layout,
        tire_field_catalog=tire_field_catalog,
        preferred_group_key=preferred_group_key,
    )
    tire.property_order = list(target_layout)
    tire.properties = {
        name: float(target_values.get(name, 0.0))
        for name in target_layout
    }
    return serialize_tire(tire), actual_changes


def _prune_site_tire_registry() -> List[str]:
    """Drop registry entries whose tire files are gone."""
    names = _load_site_tire_registry()
    keep = [
        name for name in names
        if os.path.isfile(os.path.join(MOD_TIRE_DIR, name + '.uasset'))
        and os.path.isfile(os.path.join(MOD_TIRE_DIR, name + '.uexp'))
    ]
    if keep != names:
        _save_site_tire_registry(keep)
    return keep


def _is_site_tire(name: str) -> bool:
    return name in set(_load_site_tire_registry())


def _register_site_tire(name: str) -> None:
    names = _prune_site_tire_registry()
    if name not in names:
        names.append(name)
        _save_site_tire_registry(names)


def _unregister_site_tire(name: str) -> None:
    names = [n for n in _load_site_tire_registry() if n != name]
    _save_site_tire_registry(names)


def handle_api_request(method: str, path: str, query: str, body: bytes = None) -> Dict:
    """Route API requests to handlers."""
    params = urllib.parse.parse_qs(query)

    if method == 'GET':
        if path == '/api/parts':
            return get_parts_list()
        elif path == '/api/live/state':
            return _current_live_state()
        elif path.startswith('/api/part/'):
            part_path = path[len('/api/part/'):]
            return get_part_detail(urllib.parse.unquote(part_path))
        elif path == '/api/sources':
            return get_sources()
        elif path.startswith('/api/torquecurve/'):
            curve_name = path[len('/api/torquecurve/'):]
            return get_torque_curve(urllib.parse.unquote(curve_name))
        elif path == '/api/templates/engine':
            return get_engine_templates()
        elif path == '/api/templates/tire':
            return get_tire_templates()
        elif path == '/api/sounds':
            return list_sounds()

    elif method == 'POST':
        if path == '/api/engines/shop-batch':
            return batch_register_engines()
        elif path.startswith('/api/part/'):
            part_path = path[len('/api/part/'):]
            data = json.loads(body) if body else {}
            return save_part(urllib.parse.unquote(part_path), data)
        elif path == '/api/pak/pack':
            data = json.loads(body) if body else {}
            return pack_mod(data.get('output_path', ''), data.get('parts', []))
        elif path == '/api/pak/pack-templates':
            data = json.loads(body) if body else {}
            return pack_templates(data.get('output_path', ''))
        elif path == '/api/pak/restore-datatable':
            data = json.loads(body) if body else {}
            return restore_datatable(data.get('pak_path', ''))
        elif path == '/api/create/engine':
            data = json.loads(body) if body else {}
            return create_engine(data)
        elif path == '/api/create/tire':
            data = json.loads(body) if body else {}
            return create_tire(data)
        elif path == '/api/delete/engine':
            data = json.loads(body) if body else {}
            return delete_engine(data)
        elif path == '/api/delete/tire':
            data = json.loads(body) if body else {}
            return delete_tire(data)
        elif path == '/api/engines/recommend-price':
            data = json.loads(body) if body else {}
            return recommend_engine_price(data)

    return {'error': f'Unknown route: {method} {path}'}


def get_sources() -> Dict:
    """Return available data sources for inspection/debugging."""
    sources = []
    if os.path.isdir(MOD_BASE):
        sources.append({'id': 'mod', 'name': 'MotorTown (Mod)', 'path': MOD_BASE})
    if os.path.isdir(VANILLA_BASE):
        sources.append({'id': 'vanilla', 'name': 'Base Game (Vanilla)', 'path': VANILLA_BASE})
    return {'sources': sources}


def _resolve_vehicleparts0_base(source: str) -> tuple[str, str] | tuple[None, None]:
    """Pick the best VehicleParts0 DataTable for the current inspection source."""
    candidates: List[tuple[str, str]] = []
    if source == 'vanilla':
        candidates.append((VANILLA_VEHICLEPARTS0_BASE, 'Base Game'))
    else:
        candidates.append((MOD_VEHICLEPARTS0_BASE, 'Mod'))
        candidates.append((VANILLA_VEHICLEPARTS0_BASE, 'Base Game'))

    for base_path, label in candidates:
        if os.path.isfile(base_path + '.uasset') and os.path.isfile(base_path + '.uexp'):
            return base_path, label
    return None, None


def _load_vehicleparts0_catalog(source: str) -> Optional[Dict[str, Any]]:
    """Load and cache the parsed VehicleParts0 catalog for tire/part lookups."""
    base_path, label = _resolve_vehicleparts0_base(source)
    if not base_path:
        return None

    ua_path = base_path + '.uasset'
    ue_path = base_path + '.uexp'
    cache_key = base_path
    stamp = (os.path.getmtime(ua_path), os.path.getmtime(ue_path))
    cached = _VEHICLEPARTS0_CATALOG_CACHE.get(cache_key)
    if cached and cached.get('_stamp') == stamp:
        return cached

    from parsers.uexp_vehicleparts_dt import build_vehicleparts_catalog

    ua = open(ua_path, 'rb').read()
    ue = open(ue_path, 'rb').read()
    catalog = build_vehicleparts_catalog(ua, ue)
    catalog['_stamp'] = stamp
    catalog['_source_label'] = label
    catalog['_base_path'] = base_path
    _VEHICLEPARTS0_CATALOG_CACHE[cache_key] = catalog
    return catalog


def _invalidate_vehicleparts0_catalog(base_path: Optional[str] = None) -> None:
    """Drop cached VehicleParts0 catalogs after writes."""
    if base_path:
        _VEHICLEPARTS0_CATALOG_CACHE.pop(base_path, None)
        return
    _VEHICLEPARTS0_CATALOG_CACHE.clear()


def _select_preferred_tire_vehicleparts_row(rows: List[Dict[str, Any]], file_name: str) -> Optional[Dict[str, Any]]:
    """Pick the best-matching row for one tire asset/file."""
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0]

    low_name = (file_name or '').lower()
    digits = ''.join(ch for ch in low_name if ch.isdigit())

    def _score(row: Dict[str, Any]) -> tuple[int, int, int]:
        primary = str(row.get('primary_text') or '').lower()
        secondary = str(row.get('secondary_text') or '').lower()
        score = 0
        if digits and digits in primary:
            score += 100
        if digits and digits in secondary:
            score += 40
        if primary and primary in low_name:
            score += 20
        if secondary and secondary in low_name:
            score += 10
        has_secondary = 1 if row.get('secondary_text') else 0
        return (score, has_secondary, -int(row.get('fname_number', 0)))

    return sorted(rows, key=_score, reverse=True)[0]


def _lookup_tire_vehicleparts_rows(source: str, asset_name: str, file_name: str) -> Optional[Dict[str, Any]]:
    """Return VehicleParts0 rows that reference a specific tire asset."""
    catalog = _load_vehicleparts0_catalog(source)
    if not catalog:
        return None

    candidates = {x for x in (asset_name, file_name) if x}
    if not candidates:
        return None

    matches = []
    for row in catalog.get('rows', []):
        refs = [
            ref for ref in row.get('asset_refs', [])
            if ref.get('class_name') == 'MTTirePhysicsDataAsset'
            and ref.get('object_name') in candidates
        ]
        if not refs:
            continue
        matches.append({
            'row_name': row.get('row_name', ''),
            'row_number': row.get('fname_number', 0),
            'primary_text': row.get('primary_text', ''),
            'secondary_text': row.get('secondary_text', ''),
            'visible_text': row.get('visible_text', ''),
            'price': row.get('price', 0),
            'weight': round(row.get('weight', 0.0), 3),
            'suffix_kind': row.get('suffix_kind', ''),
            'asset_refs': refs,
        })

    if not matches:
        return None

    return {
        'catalog_source': catalog.get('_source_label', ''),
        'rows': matches,
        'preferred_row': _select_preferred_tire_vehicleparts_row(matches, file_name),
    }


def _lookup_raw_tire_vehicleparts_row(source: str, asset_name: str, file_name: str) -> Optional[Dict[str, Any]]:
    """Return the full parsed donor row for one tire asset."""
    catalog = _load_vehicleparts0_catalog(source)
    if not catalog:
        return None

    candidates = {x for x in (asset_name, file_name) if x}
    if not candidates:
        return None

    matches = []
    for row in catalog.get('rows', []):
        refs = [
            ref for ref in row.get('asset_refs', [])
            if ref.get('class_name') == 'MTTirePhysicsDataAsset'
            and ref.get('object_name') in candidates
        ]
        if refs:
            matches.append(row)

    return _select_preferred_tire_vehicleparts_row(matches, file_name)


def _lookup_tire_vehicleparts_row_by_name(target_row_name: str) -> Optional[Dict[str, Any]]:
    """Find a VehicleParts0 tire row by its exact row name (FName).

    Searches vanilla catalog first, then mod catalog.  Used to resolve the
    vehicle-type override where the user picks a specific donor row name
    (e.g. 'BasicTire', 'MotorCycleTire_01') to control vehicle compatibility.
    """
    for source in ('vanilla', 'mod'):
        catalog = _load_vehicleparts0_catalog(source)
        if not catalog:
            continue
        for row in catalog.get('tire_rows', []):
            if row.get('row_name') == target_row_name:
                return row
    return None


def _ensure_mod_vehicleparts0_files() -> tuple[str, str]:
    """Ensure the mod VehicleParts0 pair exists before tire registration writes."""
    dt_dir = os.path.dirname(MOD_VEHICLEPARTS0_BASE)
    os.makedirs(dt_dir, exist_ok=True)
    ua_path = MOD_VEHICLEPARTS0_BASE + '.uasset'
    ue_path = MOD_VEHICLEPARTS0_BASE + '.uexp'
    if os.path.isfile(ua_path) and os.path.isfile(ue_path):
        _sync_uasset_serial_size_file(ua_path, ue_path)
        return ua_path, ue_path

    for donor_base in (VANILLA_VEHICLEPARTS0_BASE,):
        donor_ua = donor_base + '.uasset'
        donor_ue = donor_base + '.uexp'
        if os.path.isfile(donor_ua) and os.path.isfile(donor_ue):
            shutil.copy2(donor_ua, ua_path)
            shutil.copy2(donor_ue, ue_path)
            _sync_uasset_serial_size_file(ua_path, ue_path)
            _invalidate_vehicleparts0_catalog(MOD_VEHICLEPARTS0_BASE)
            return ua_path, ue_path

    raise FileNotFoundError('No VehicleParts0 donor files found')


def _default_tire_shop_values(name: str,
                              preferred_row: Optional[Dict[str, Any]] = None,
                              weight: Optional[float] = None) -> Dict[str, Any]:
    """Return fallback shop metadata for one tire."""
    if preferred_row:
        code = str(preferred_row.get('primary_text') or '').strip()
        display_name = str(
            preferred_row.get('secondary_text')
            or preferred_row.get('visible_text')
            or preferred_row.get('primary_text')
            or name
        ).strip()
        return {
            'kind': 'tire',
            'code': code,
            'display_name': display_name or name,
            'price': int(preferred_row.get('price', 500)),
            'weight': round(float(preferred_row.get('weight', weight or 10.0)), 3),
        }
    return {
        'kind': 'tire',
        'code': '',
        'display_name': name,
        'price': 500,
        'weight': round(float(weight or 10.0), 3),
    }


def _quick_variant(name: str) -> str:
    """Infer engine variant from name using heuristics (no file I/O)."""
    low = name.lower()
    if any(x in low for x in ('electric', '_ev', 'h2_')):
        return 'ev'
    if any(x in low for x in ('bike', 'scooter', 'kart')):
        return 'bike'
    if any(x in low for x in ('heavyduty', 'heavymachine', 'bus_', 'mediumduty',
                               'fh', 'd13', 'dc16', 'detroit', 'mx13', 'catc12',
                               'x15', '770s', 'dv27k')):
        return 'diesel_hd'
    if any(x in low for x in ('lightdiesel', '30tdi', '59cummins', '65detroit',
                               '66duramax', '73powerstroke', 'r10', 'benzi6')):
        return 'diesel'
    return 'ice'


def _build_shop_names_set() -> set:
    """Return set of engine names (row keys) present in the Engines DataTable."""
    try:
        from parsers.uasset_clone import _parse_name_table, _read_fstring
        dt_uasset_p = ENGINES_DT_BASE + '.uasset'
        if not os.path.isfile(dt_uasset_p):
            return set()
        with open(dt_uasset_p, 'rb') as f:
            ua_data = f.read()
        _folder_text, folder_bytes = _read_fstring(ua_data, 32)
        folder_end = 32 + folder_bytes
        name_count  = struct.unpack_from('<i', ua_data, folder_end + 4)[0]
        name_offset = struct.unpack_from('<i', ua_data, folder_end + 8)[0]
        entries, _ = _parse_name_table(ua_data, name_offset, name_count)
        return {e['text'] for e in entries}
    except Exception:
        return set()


_VANILLA_DT_ROW_NAMES = None


def _parse_name_lookup(uasset_data: bytes) -> tuple[dict[int, str], dict[str, int]]:
    """Return FName index/name lookups for a DataTable .uasset."""
    from parsers.uasset_clone import _parse_name_table, _read_fstring

    _folder_text, folder_bytes = _read_fstring(uasset_data, 32)
    folder_end = 32 + folder_bytes
    name_count = struct.unpack_from('<i', uasset_data, folder_end + 4)[0]
    name_offset = struct.unpack_from('<i', uasset_data, folder_end + 8)[0]
    entries, _ = _parse_name_table(uasset_data, name_offset, name_count)
    idx_to_name = {i: e['text'] for i, e in enumerate(entries)}
    name_to_idx = {e['text']: i for i, e in enumerate(entries)}
    return idx_to_name, name_to_idx


def _get_import_count(uasset_data: bytes) -> int:
    """Read the import table count from a .uasset header."""
    from parsers.uasset_clone import _read_fstring

    _folder_text, folder_bytes = _read_fstring(uasset_data, 32)
    folder_end = 32 + folder_bytes
    return struct.unpack_from('<i', uasset_data, folder_end + 36)[0]


def _find_engine_import_ref(uasset_data: bytes, engine_name: str) -> Optional[int]:
    """Return the negative import ID for a row's MHEngineDataAsset import."""
    idx_to_name, name_to_idx = _parse_name_lookup(uasset_data)
    name_fidx = name_to_idx.get(engine_name)
    if name_fidx is None:
        return None

    from parsers.uasset_clone import _read_fstring
    _folder_text, folder_bytes = _read_fstring(uasset_data, 32)
    folder_end = 32 + folder_bytes
    import_count = struct.unpack_from('<i', uasset_data, folder_end + 36)[0]
    import_offset = struct.unpack_from('<i', uasset_data, folder_end + 40)[0]

    for i in range(import_count):
        off = import_offset + i * 32
        if off + 28 > len(uasset_data):
            break
        class_name_fidx = struct.unpack_from('<i', uasset_data, off + 8)[0]
        object_name_fidx = struct.unpack_from('<i', uasset_data, off + 20)[0]
        if object_name_fidx != name_fidx:
            continue
        if idx_to_name.get(class_name_fidx) == 'MHEngineDataAsset':
            return -(i + 1)
    return None


def _replace_first_import_ref(blob: bytes, old_ref: int, new_ref: int) -> tuple[bytes, bool]:
    """Replace the first LE int32 import reference inside an opaque tail blob."""
    target = struct.pack('<i', old_ref)
    pos = blob.find(target)
    if pos < 0:
        return blob, False
    return blob[:pos] + struct.pack('<i', new_ref) + blob[pos + 4:], True


def _infer_tail_import_ref(tail: bytes) -> Optional[int]:
    """Best-effort fallback for rows whose engine ref is not discoverable from imports."""
    for off in range(0, min(len(tail) - 3, 128)):
        value = struct.unpack_from('<i', tail, off)[0]
        if -512 <= value < 0:
            return value
    return None


def _load_vanilla_dt_row_names() -> set[str]:
    """Return the row-name set shipped by the base game DataTable."""
    global _VANILLA_DT_ROW_NAMES
    if _VANILLA_DT_ROW_NAMES is not None:
        return _VANILLA_DT_ROW_NAMES

    try:
        from parsers.uexp_engines_dt import _find_type_a_rows
        ua_path = os.path.join(VANILLA_BASE, 'DataTable', 'Engines.uasset')
        ue_path = os.path.join(VANILLA_BASE, 'DataTable', 'Engines.uexp')
        ua = open(ua_path, 'rb').read()
        ue = open(ue_path, 'rb').read()
        idx_to_name, _ = _parse_name_lookup(ua)
        _VANILLA_DT_ROW_NAMES = {
            idx_to_name.get(row['fname_idx'], '')
            for row in _find_type_a_rows(ue)
            if idx_to_name.get(row['fname_idx'], '')
        }
    except Exception:
        _VANILLA_DT_ROW_NAMES = set()
    return _VANILLA_DT_ROW_NAMES


def _load_custom_row_templates() -> Dict[str, Dict[str, Any]]:
    """Load optional known-good custom row templates when a private DataTable is present."""
    global _CUSTOM_ROW_TEMPLATE_CACHE
    if _CUSTOM_ROW_TEMPLATE_CACHE is not None:
        return _CUSTOM_ROW_TEMPLATE_CACHE

    _CUSTOM_ROW_TEMPLATE_CACHE = {}
    return _CUSTOM_ROW_TEMPLATE_CACHE


def _find_donor_row_with_import(ua: bytes, ue: bytes, variant: str) -> Optional[Dict[str, Any]]:
    """Pick a donor row whose hidden engine import can be retargeted."""
    from parsers.uexp_engines_dt import _find_type_a_rows, FOOTER

    custom_templates = _load_custom_row_templates()
    for preferred_donor in _CUSTOM_ROW_DONORS.get(variant, []):
        template = custom_templates.get(preferred_donor)
        if template is not None:
            return template

    variant_donor_names = {
        'diesel_hd': [
            'HeavyDuty_440HP',
            'HeavyDuty_350HP',
            'HeavyDuty_260HP',
            'HeavyDuty_540HP',
            'MediumDuty_330HP',
            'MediumDuty_250HP',
            'Truck_190HP',
            'Bus_400HP',
        ],
        'bike': [
            'Bike_I4_100HP',
            'Bike_I4_160HP',
            'Bike_I2_100HP',
            'Bike_I2_50HP',
            'Bike_I2_30HP',
            'H2_30HP',
        ],
        'ev': [
            'Electric_300HP',
            'Electric_130HP',
            'Electric_670HP',
        ],
        'ice_standard': [
            'V12_400HP',
            'SmallBlock_320HP',
            'SmallBlock_240HP',
            'SmallBlock_180HP',
            'SmallBlock_140HP',
            'V6Sport_400HP',
        ],
        'ice_compact': [
            'I4_150HP',
            'I6Sport_200HP',
            'SmallBlock_90HP',
            'I4_50HP',
            'Scooter_15HP',
            'Scooter_10HP',
            'V6Sport_400HP',
        ],
    }
    idx_to_name, _ = _parse_name_lookup(ua)
    rows = _find_type_a_rows(ue)
    preferred_donors = variant_donor_names.get(variant, [])

    def _candidate(i: int, row: dict) -> Optional[Dict[str, Any]]:
        donor_name = idx_to_name.get(row['fname_idx'], '')
        donor_ref = _find_engine_import_ref(ua, donor_name)
        if donor_ref is None:
            return None
        row_end = rows[i + 1]['row_start'] if i + 1 < len(rows) else len(ue) - len(FOOTER)
        tail = ue[row['tail_start']:row_end]
        if len(tail) < 100:
            return None
        return {**row, 'row_end': row_end, 'tail': tail, 'donor_name': donor_name, 'donor_ref': donor_ref}

    for preferred_donor in preferred_donors:
        for i, row in enumerate(rows):
            donor_name = idx_to_name.get(row['fname_idx'], '')
            if donor_name != preferred_donor:
                continue
            match = _candidate(i, row)
            if match is not None:
                return match

    for i, row in enumerate(rows):
        match = _candidate(i, row)
        if match is not None:
            return match

    return None


def _find_no_level_tail_template(variant: str) -> Optional[Dict[str, Any]]:
    """Pick an optional row tail that already omits the shop level requirement."""
    custom_templates = _load_custom_row_templates()
    for donor_name in _NO_LEVEL_TAIL_DONORS.get(variant, []):
        template = custom_templates.get(donor_name)
        if template is not None:
            return template
    return None


def _find_donor_row_by_name(ua: bytes, ue: bytes, target_name: str) -> Optional[Dict[str, Any]]:
    """Find a specific DataTable donor row by its exact FName."""
    from parsers.uexp_engines_dt import _find_type_a_rows, FOOTER

    idx_to_name, _ = _parse_name_lookup(ua)
    rows = _find_type_a_rows(ue)
    for i, row in enumerate(rows):
        name = idx_to_name.get(row['fname_idx'], '')
        if name != target_name:
            continue
        donor_ref = _find_engine_import_ref(ua, name)
        if donor_ref is None:
            continue
        row_end = rows[i + 1]['row_start'] if i + 1 < len(rows) else len(ue) - len(FOOTER)
        tail = ue[row['tail_start']:row_end]
        if len(tail) < 100:
            continue
        return {**row, 'row_end': row_end, 'tail': tail, 'donor_name': name, 'donor_ref': donor_ref}
    return None


def _get_template_price_model(include_bikes: bool = False):
    """Return the cached weighted torque-price model for template engines."""
    template_files, stamp = _template_engine_files_and_stamp()
    cache_key = (include_bikes, stamp[0], stamp[1])

    if cache_key in _ENGINE_PRICE_MODEL_CACHE:
        return _ENGINE_PRICE_MODEL_CACHE[cache_key]

    from template_engines import load_template_specs

    specs = load_template_specs(TEMPLATES_ENGINE_DIR, ENGINE_DISPLAY_NAMES)
    if not include_bikes:
        specs = [spec for spec in specs if spec.variant != 'bike']

    model = build_torque_price_model(specs)
    _ENGINE_PRICE_MODEL_CACHE[cache_key] = model
    return model


def _template_audit_summary(audit: Dict[str, Any]) -> Dict[str, Any]:
    errors = list(audit.get('errors') or [])
    warnings = list(audit.get('warnings') or [])
    legacy_bikes = list(audit.get('legacy_bike_names') or [])
    return {
        'valid': bool(audit.get('valid')),
        'checked': int(audit.get('checked', 0) or 0),
        'error_count': len(errors),
        'warning_count': len(warnings),
        'legacy_bike_count': len(legacy_bikes),
        'errors': errors[:8],
        'warnings': warnings[:8],
        'legacy_bike_names': legacy_bikes[:8],
    }


def _template_audit_preview(audit: Dict[str, Any]) -> str:
    errors = list(audit.get('errors') or [])
    if errors:
        preview = '; '.join(errors[:4])
        extra = '' if len(errors) <= 4 else f' (+{len(errors) - 4} more)'
        return f'Template audit failed: {preview}{extra}'
    warnings = list(audit.get('warnings') or [])
    if warnings:
        preview = '; '.join(warnings[:2])
        extra = '' if len(warnings) <= 2 else f' (+{len(warnings) - 2} more)'
        return f'Template audit warnings: {preview}{extra}'
    return 'Template audit passed'


def _audit_template_engines() -> Dict[str, Any]:
    """Audit the curated template engine set and cache by template directory mtime."""
    global _TEMPLATE_AUDIT_CACHE

    _, cache_key = _template_engine_files_and_stamp()

    if _TEMPLATE_AUDIT_CACHE and _TEMPLATE_AUDIT_CACHE[0] == cache_key:
        return _TEMPLATE_AUDIT_CACHE[1]

    from engine_validation import audit_engine_value_consistency

    audit = audit_engine_value_consistency(
        TEMPLATES_ENGINE_DIR,
        standard_baseline=_STANDARD_TEMPLATE_BASELINE,
        required_standard_heating_power=_STANDARD_REQUIRED_HEATING_POWER,
        forbidden_standard_format_hint=_STANDARD_FORBIDDEN_FORMAT_HINT,
        compact_baseline=_COMPACT_TEMPLATE_BASELINE,
        compact_outlier_signature=_COMPACT_TEMPLATE_OUTLIER_SIGNATURE,
        bike_baseline=_BIKE_TEMPLATE_BASELINE,
        diesel_baseline=_DIESEL_TEMPLATE_BASELINE,
        ev_baseline=_EV_TEMPLATE_BASELINE,
        min_fuel_consumption=_MIN_SAFE_TEMPLATE_FUEL_CONSUMPTION,
    )
    _TEMPLATE_AUDIT_CACHE = (cache_key, audit)
    return audit


def _compute_hp_from_curve(engine_dir: str, engine_name: str,
                           max_torque_nm: float, max_rpm: float) -> float:
    """Compute peak HP using the actual torque curve file if it exists.

    Looks for a custom torque curve at ``engine_dir/TorqueCurve/TorqueCurve_<name>.uexp``.
    Uses ``HP = MaxTorque_Nm × curve(t) × RPM / 7121`` and returns the peak.
    Returns 0 if no curve file is found.
    """
    peaks = _compute_curve_peaks(engine_dir, engine_name, max_torque_nm, max_rpm)
    return peaks.get('max_hp', 0.0) if peaks else 0.0


def _compute_curve_peaks(engine_dir: str, engine_name: str,
                         max_torque_nm: float, max_rpm: float,
                         is_ev: bool = False,
                         estimated_hp: float = 0.0) -> Dict[str, float]:
    """Derive peak-torque-RPM, peak-HP-RPM, and peak HP for an engine.

    Used to pre-fill the Engine Creator's "Max Torque @ RPM" and
    "Max HP @ RPM" fields when the user forks from a vanilla engine
    (which has no saved creation_inputs metadata).

    Strategy:
      1. If a per-engine curve file exists at
         engine_dir/TorqueCurve/TorqueCurve_<name>.uexp — sweep it
         and return the actual peaks (Frog-Mod-Editor-generated
         engines ship one of these).
      2. Otherwise, fall back to type-appropriate defaults so the
         user gets reasonable starting values instead of blank fields:
            ICE: peak torque around 50% of max RPM, peak HP around 85%
            EV:  peak torque around 0 RPM, peak HP around 60%
         Max HP comes from the engine's estimated_hp() (or the
         curve-based display HP if already computed).
    Returns an empty dict only if max_rpm or max_torque_nm are zero.
    """
    if max_torque_nm <= 0 or max_rpm <= 0:
        return {}

    # Path 1: per-engine curve (Frog-Mod-Editor-generated engines)
    tc_uexp = os.path.join(engine_dir, 'TorqueCurve', f'TorqueCurve_{engine_name}.uexp')
    if os.path.isfile(tc_uexp):
        try:
            from parsers.uexp_torquecurve import parse_torque_curve
            tc_data = open(tc_uexp, 'rb').read()
            curve = parse_torque_curve(tc_data)

            best_torque_v = 0.0
            best_torque_t = 0.5
            best_hp = 0.0
            best_hp_t = 0.5
            for i in range(1, 1001):
                t = i / 1000.0
                v = curve.evaluate(t)
                if v > best_torque_v:
                    best_torque_v = v
                    best_torque_t = t
                hp = max_torque_nm * v * (t * max_rpm) / 7121.0
                if hp > best_hp:
                    best_hp = hp
                    best_hp_t = t
            return {
                'peak_torque_rpm': round(best_torque_t * max_rpm, 0),
                'peak_hp_rpm':     round(best_hp_t * max_rpm, 0),
                'max_hp':          round(best_hp, 1),
            }
        except Exception:
            pass  # fall through to the typed-default path

    # Path 2: vanilla / shared-curve engines — type-appropriate defaults
    if is_ev:
        torque_t = 0.05  # EVs deliver peak torque from near-stall
        hp_t     = 0.60  # peak power roughly mid-rpm
    else:
        torque_t = 0.50  # ICE peak torque mid-band
        hp_t     = 0.85  # peak HP near (but not at) redline
    fallback_hp = round(estimated_hp, 1) if estimated_hp > 0 else round(
        max_torque_nm * (hp_t * max_rpm) / 7121.0, 1
    )
    return {
        'peak_torque_rpm': round(torque_t * max_rpm, 0),
        'peak_hp_rpm':     round(hp_t * max_rpm, 0),
        'max_hp':          fallback_hp,
    }


def _load_creation_meta(engine_dir: str, engine_name: str) -> Dict[str, Any]:
    """Load saved creation inputs (peak torque RPM, max HP, peak HP RPM)
    from the .creation.json file written during engine creation.

    Returns an empty dict if the file doesn't exist or can't be read.
    """
    import json as _json
    meta_path = os.path.join(engine_dir, engine_name + '.creation.json')
    if not os.path.isfile(meta_path):
        return {}
    try:
        with open(meta_path, 'r') as f:
            return _json.load(f)
    except Exception:
        return {}


def _default_shop_values_for_engine(engine_name: str, variant: str, hp: float, torque_nm: float) -> Dict[str, Any]:
    """Return consistent default shop metadata for an engine/template."""
    from template_engines import display_name_for_engine, canonical_template_name, split_shop_display

    raw_display = display_name_for_engine(engine_name, ENGINE_DISPLAY_NAMES)
    display_name, description = split_shop_display(raw_display)
    canonical_name = canonical_template_name(engine_name, ENGINE_DISPLAY_NAMES)
    weight = ENGINE_WEIGHTS.get(canonical_name) or _fallback_weight(variant, hp)
    price_model = _get_template_price_model(include_bikes=(variant == 'bike'))
    price = recommend_price_from_torque(price_model, torque_nm)

    return {
        'display_name': display_name,
        'description': description,
        'price': price,
        'weight': round(weight, 1),
        'exists': False,
    }


def _prune_datatable_rows(ua: bytes, ue: bytes, keep_names: set[str]) -> tuple[bytes, list[str]]:
    """Remove staged DataTable rows whose names are not in keep_names."""
    from parsers.uexp_engines_dt import _find_type_a_rows, FOOTER, ROW_COUNT_OFFSET

    idx_to_name, _ = _parse_name_lookup(ua)
    rows = _find_type_a_rows(ue)
    to_remove = []
    removed_names = []

    for i, row in enumerate(rows):
        row_name = idx_to_name.get(row['fname_idx'], '')
        if not row_name or row_name in keep_names:
            continue
        row_end = rows[i + 1]['row_start'] if i + 1 < len(rows) else len(ue) - len(FOOTER)
        to_remove.append((row['row_start'], row_end))
        removed_names.append(row_name)

    if not to_remove:
        return ue, removed_names

    old_count = struct.unpack_from('<i', ue, ROW_COUNT_OFFSET)[0]
    ue_buf = bytearray(ue)
    for row_start, row_end in sorted(to_remove, key=lambda item: item[0], reverse=True):
        del ue_buf[row_start:row_end]
    struct.pack_into('<i', ue_buf, ROW_COUNT_OFFSET, old_count - len(to_remove))
    return bytes(ue_buf), removed_names


def _register_engine_datatable_entry(ua: bytes, ue: bytes, engine_name: str,
                                     display_name: str, price: int, weight: float,
                                     variant: str, update_existing: bool = True,
                                     description: str = '',
                                     row_tail_variant: Optional[str] = None,
                                     tail_donor_name: Optional[str] = None,
                                     level_requirements: Optional[Dict[str, int]] = None
                                     ) -> tuple[bytes, bytes, str]:
    """Ensure an engine has a matching DataTable row and imports.

    When ``level_requirements`` is provided (as a dict mapping
    CL_* enum name -> int level), the donor's LevelRequirementToBuy
    TMap inside the row tail is rewritten to match the user's pick.
    Empty dict -> count=0 (engine unlocks at Driver level 1, vanilla
    default). Missing CL_* names are appended to the .uasset name
    table on the fly. The locator handles both populated-TMap donors
    (CL_* anchor) and empty-TMap donors (FString anchor on the
    GameplayTagQuery description); if neither anchor finds a
    plausible position, a ValueError is raised rather than silently
    dropping the user's selection.
    """
    from parsers.uasset_engines_dt import (
        get_fname_index, add_row_key, add_engine_import,
        append_names_if_missing,
    )
    from parsers.uexp_engines_dt import (read_row as read_dt_row,
                                          update_row as update_dt_row,
                                          append_row, build_row_from_template,
                                          build_level_requirement_bytes,
                                          replace_level_requirement_section)

    # CL_* names spanning EMTCharacterLevelType enum (Driver, Taxi, Bus,
    # Truck, Racer, Wrecker, Police). The locator needs to know every
    # CL_* index that might appear in a donor's existing TMap, even if
    # the user isn't selecting all of them.
    _CL_NAMES = ('CL_Driver', 'CL_Taxi', 'CL_Bus', 'CL_Truck',
                 'CL_Racer', 'CL_Wrecker', 'CL_Police')

    fname_idx = get_fname_index(ua, engine_name)
    path_idx = get_fname_index(ua, f'/Game/Cars/Parts/Engine/{engine_name}')

    if fname_idx < 0:
        ua, fname_idx, path_idx = add_row_key(ua, engine_name)
    elif path_idx < 0:
        raise ValueError(f'Missing full path FName for {engine_name}')

    existing = read_dt_row(ue, fname_idx)
    if existing is not None:
        if update_existing:
            ue = update_dt_row(ue, fname_idx, display_name, price, weight, description=description)
            return ua, ue, 'updated'
        return ua, ue, 'kept'

    donor_row = _find_donor_row_with_import(ua, ue, variant)
    if donor_row is None:
        raise ValueError(f'No donor row found for variant {variant}')

    new_asset_ref = _find_engine_import_ref(ua, engine_name)
    if new_asset_ref is None:
        new_asset_ref = -(_get_import_count(ua) + 2)
        ua = add_engine_import(ua, engine_name, path_idx, fname_idx)

    tail_donor = _find_no_level_tail_template(variant) or donor_row
    if tail_donor_name:
        named = _find_donor_row_by_name(ua, ue, tail_donor_name)
        if named is not None:
            tail_donor = named
    elif row_tail_variant:
        tail_donor = _find_donor_row_with_import(ua, ue, row_tail_variant) or tail_donor
    patched_tail, replaced = _replace_first_import_ref(
        tail_donor['tail'],
        tail_donor['donor_ref'],
        new_asset_ref,
    )
    if not replaced:
        raise ValueError(f'Could not patch donor import ref for {engine_name}')

    # Apply the user's level requirements (if provided) before building
    # the row. Adds any missing CL_* enum FNames to the .uasset name
    # table first so the FName indices we encode are valid.
    if level_requirements is not None:
        # Make sure every CL_* enum name we might need (including ones
        # in the donor's existing TMap) is present in the .uasset name
        # table. Cheap to just request all 7 — append_names_if_missing
        # is a no-op for names that already exist.
        ua, cl_indices = append_names_if_missing(ua, list(_CL_NAMES))
        # Verify all keys the user picked have valid FNames. They will
        # because we just added them, but defend against typos.
        missing = [k for k in level_requirements if k not in cl_indices]
        if missing:
            raise ValueError(f'Unknown CL_* level types in level_requirements: {missing}')
        new_lr_bytes = build_level_requirement_bytes(level_requirements, cl_indices)
        rewritten_tail, did_rewrite = replace_level_requirement_section(
            patched_tail, new_lr_bytes, cl_indices
        )
        if did_rewrite:
            patched_tail = rewritten_tail
        else:
            # The locator has two anchor strategies that together
            # cover every vanilla donor row in the Engines DataTable
            # (verified by sweep: 36/36). If we still couldn't find
            # an LR position, the donor row is exotic enough that we
            # shouldn't silently drop the user's selection — surface
            # it as an error so a bug report has actionable context.
            raise ValueError(
                f"Could not locate LevelRequirementToBuy bytes in "
                f"donor row for engine '{engine_name}'. Pick a "
                f"different donor or report this as a bug."
            )

    new_row = build_row_from_template(
        fname_idx, display_name, price, weight, patched_tail, donor_row, description=description
    )
    ue = append_row(ue, new_row)
    return ua, ue, 'created'


def _sync_engine_datatable_tree(mt_root: str, prefer_existing_shop: bool = True) -> Dict[str, Any]:
    """Sync a staged MotorTown tree so engine files and DataTable rows match."""
    from parsers.uasset_engines_dt import get_fname_index
    from parsers.uexp_engine import parse_engine, detect_variant
    from parsers.uexp_engines_dt import read_row as read_dt_row
    from template_engines import split_shop_display

    engine_dir = os.path.join(mt_root, 'Content', 'Cars', 'Parts', 'Engine')
    dt_dir = os.path.join(mt_root, 'Content', 'DataAsset', 'VehicleParts')
    dt_uasset_p = os.path.join(dt_dir, 'Engines.uasset')
    dt_uexp_p = os.path.join(dt_dir, 'Engines.uexp')

    # If there are no engine files in the mod tree, skip sync entirely.
    # This is normal when the mod only contains transmissions, economy, etc.
    if not os.path.isdir(engine_dir):
        return {'created': 0, 'updated': 0, 'kept': 0, 'removed': [], 'errors': []}
    if not os.path.isfile(dt_uasset_p) or not os.path.isfile(dt_uexp_p):
        return {'created': 0, 'updated': 0, 'kept': 0, 'removed': [], 'errors': []}

    ua = open(dt_uasset_p, 'rb').read()
    ue = open(dt_uexp_p, 'rb').read()
    engine_names = sorted(
        os.path.splitext(f)[0]
        for f in os.listdir(engine_dir)
        if f.endswith('.uexp') and os.path.isfile(os.path.join(engine_dir, f))
    )

    created = 0
    updated = 0
    kept = 0
    errors = []

    for name in engine_names:
        try:
            uexp_path = os.path.join(engine_dir, f'{name}.uexp')
            uexp_data = open(uexp_path, 'rb').read()
            engine = parse_engine(uexp_data)
            _curve_hp = _compute_hp_from_curve(
                engine_dir, name,
                engine.max_torque_nm, engine.max_rpm,
            )
            hp = _curve_hp if _curve_hp > 0 else round(engine.estimated_hp(), 1)
            variant = detect_variant(uexp_data).value

            default_shop = _default_shop_values_for_engine(
                name,
                variant,
                hp,
                round(engine.max_torque_nm, 1),
            )

            update_existing = not prefer_existing_shop
            display = default_shop['display_name']
            description = default_shop['description']
            price = default_shop['price']
            weight = default_shop['weight']

            if prefer_existing_shop:
                fname_idx = get_fname_index(ua, name)
                existing = read_dt_row(ue, fname_idx) if fname_idx >= 0 else None
                if existing:
                    display = existing['display_name']
                    description = existing.get('description', '')
                    price = existing['price']
                    weight = existing['weight']

            ua, ue, action = _register_engine_datatable_entry(
                ua, ue, name, display, price, weight, variant,
                update_existing=update_existing, description=description
            )
            if action == 'created':
                created += 1
            elif action == 'updated':
                updated += 1
            else:
                kept += 1
        except Exception as exc:
            errors.append({'name': name, 'error': str(exc)})

    keep_names = set(engine_names) | _load_vanilla_dt_row_names()
    ue, removed = _prune_datatable_rows(ua, ue, keep_names)
    ua = _patch_datatable_serial_size(ua, len(ue))

    with open(dt_uasset_p, 'wb') as f:
        f.write(ua)
    with open(dt_uexp_p, 'wb') as f:
        f.write(ue)

    return {
        'created': created,
        'updated': updated,
        'kept': kept,
        'removed': removed,
        'errors': errors,
        'engine_names': engine_names,
    }


def get_parts_list() -> Dict:
    """Return generated mod parts for the live editor workspace."""
    parts: Dict[str, List[Dict[str, Any]]] = {}
    shop_names = _build_shop_names_set()
    engine_items: List[Dict[str, Any]] = []
    tire_items: List[Dict[str, Any]] = []
    tire_catalog = _load_vehicleparts0_catalog('mod') or {}
    tire_rows_by_asset = tire_catalog.get('rows_by_asset_object', {})

    for name in sorted(_prune_site_engine_registry(), key=str.lower):
        f = os.path.join(MOD_ENGINE_DIR, name + '.uexp')
        if os.path.isfile(f):
            try:
                data = open(f, 'rb').read()
                variant = detect_variant(data).value
            except Exception:
                variant = _quick_variant(name)
            engine_items.append({
                'name': name,
                'source': 'mod',
                'path': f'mod/Engine/{name}',
                'uexp_size': os.path.getsize(f),
                'variant': variant,
                'in_shop': name in shop_names,
            })

    for name in sorted(_prune_site_tire_registry(), key=str.lower):
        f = os.path.join(MOD_TIRE_DIR, name + '.uexp')
        if not os.path.isfile(f):
            continue
        tire_items.append({
            'name': name,
            'source': 'mod',
            'path': f'mod/Tire/{name}',
            'uexp_size': os.path.getsize(f),
            'in_shop': bool(tire_rows_by_asset.get(name)),
        })

    # Scan transmissions (directory-based, no registry). The transmission
    # editor writes .uasset/.uexp pairs directly into MOD_TRANSMISSION_DIR.
    transmission_items: List[Dict[str, Any]] = []
    if os.path.isdir(MOD_TRANSMISSION_DIR):
        try:
            entries = sorted(os.listdir(MOD_TRANSMISSION_DIR), key=str.lower)
        except OSError:
            entries = []
        seen_names: set[str] = set()
        for fname in entries:
            if not fname.endswith('.uexp'):
                continue
            name = fname[:-5]
            if name in seen_names:
                continue
            seen_names.add(name)
            uasset_f = os.path.join(MOD_TRANSMISSION_DIR, name + '.uasset')
            uexp_f = os.path.join(MOD_TRANSMISSION_DIR, fname)
            if not os.path.isfile(uasset_f):
                continue
            transmission_items.append({
                'name': name,
                'source': 'mod',
                'path': f'mod/Transmission/{name}',
                'uexp_size': os.path.getsize(uexp_f),
            })

    if engine_items:
        parts['Engine'] = sorted(engine_items, key=lambda p: p['name'].lower())
    if tire_items:
        parts['Tire'] = sorted(tire_items, key=lambda p: p['name'].lower())
    if transmission_items:
        parts['Transmission'] = sorted(transmission_items, key=lambda p: p['name'].lower())
    live = _current_live_state()
    return {
        'parts': parts,
        'state_version': live['version'],
        'engine_count': live['engine_count'],
        'tire_count': live.get('tire_count', len(tire_items)),
        'transmission_count': len(transmission_items),
        'part_count': live.get('part_count', len(engine_items) + len(tire_items) + len(transmission_items)),
    }


def _resolve_part_path(part_path: str) -> tuple:
    """Resolve part_path (e.g. 'mod/Engine/lexusV10') to filesystem paths."""
    parts = part_path.split('/')
    if len(parts) < 3:
        raise ValueError(f"Invalid part path: {part_path}")

    source = parts[0]
    dir_name = '/'.join(parts[1:-1])
    name = parts[-1]

    if source == 'mod':
        base = MOD_BASE
    elif source == 'vanilla':
        base = VANILLA_BASE
    elif source == 'template':
        base = os.path.dirname(TEMPLATES_ENGINE_DIR)  # data/templates/
    else:
        raise ValueError(f"Unknown source: {source}")

    uexp_path = os.path.join(base, dir_name, f'{name}.uexp')
    uasset_path = os.path.join(base, dir_name, f'{name}.uasset')

    if not os.path.isfile(uexp_path):
        raise FileNotFoundError(f"Part not found: {uexp_path}")

    # Determine parser type from directory
    parser_type = None
    for type_name, (dt, pt) in PART_TYPES.items():
        if dir_name == dt:
            parser_type = pt
            break

    return uexp_path, uasset_path, parser_type, source


MOD_SOUND_BASE  = os.path.join(MOD_BASE, 'Engine', 'Sound')
BASE_SOUND_BASE = os.path.join(VANILLA_BASE, 'Engine', 'Sound')


_ENGINE_CUES = frozenset({
    'SC_V8Engine',
    'SC_V12Engine',
    'SC_LightDiesel',
    'SC_Truck_04',
    'SC_Truck_05',
    'SC_I4SportEngine',
    'SC_ElectricMotor',
})
_SKIP_DIRS   = frozenset({'jake', 'Backfire', 'Intake'})
_SOUND_DIR_ALIASES = {
    'I4': 'I4_1000',
}


def _sound_dir_exists(sound_dir: str) -> bool:
    """Return True when a sound dir/name is available in either base or mod sound roots."""
    sound_dir = _SOUND_DIR_ALIASES.get(sound_dir, sound_dir)
    if not sound_dir:
        return False

    for base in (MOD_SOUND_BASE, BASE_SOUND_BASE):
        if not os.path.isdir(base):
            continue
        if sound_dir == 'Electric':
            if os.path.isfile(os.path.join(base, 'Electric', 'SC_ElectricMotor.uasset')):
                return True
            continue
        if os.path.isfile(os.path.join(base, 'Bike', sound_dir + '.uasset')):
            return True
        if os.path.isdir(os.path.join(base, sound_dir)):
            return True
    return False


def _extract_sound_meta(uasset_path: str) -> Optional[Dict]:
    """Parse a .uasset name table and return engine-specific sound metadata.

    Scans all name entries containing /Cars/Parts/Engine/Sound/ and returns
    the best match: first preference is an entry whose SoundCue file actually
    exists on disk (valid), second is an entry whose cue is a known engine cue.

    Returns {'dir': str, 'cue': str, 'valid': bool} or None if no sound found.
    """
    try:
        from parsers.uasset_clone import _read_fstring, _parse_name_table
        import struct as _struct
        with open(uasset_path, 'rb') as f:
            data = f.read()
        folder_text, folder_bytes = _read_fstring(data, 32)
        folder_end = 32 + folder_bytes
        name_count = _struct.unpack_from('<i', data, folder_end + 4)[0]
        name_offset = _struct.unpack_from('<i', data, folder_end + 8)[0]
        entries, _ = _parse_name_table(data, name_offset, name_count)

        candidates = []
        for entry in entries:
            text = entry.get('text', '')
            if '/Cars/Parts/Engine/Sound/' not in text:
                continue
            parts = text.split('/Cars/Parts/Engine/Sound/')
            if len(parts) < 2:
                continue
            segs = parts[1].split('/')
            head = segs[0]
            if head in _SKIP_DIRS:
                continue
            if head == 'Bike':
                if len(segs) < 2:
                    continue
                sdir = _SOUND_DIR_ALIASES.get(segs[1], segs[1])
                cue = segs[-1] if len(segs) > 2 else sdir
            elif head == 'Electric':
                sdir = 'Electric'
                cue = segs[-1] if len(segs) > 1 else 'SC_ElectricMotor'
            else:
                sdir = _SOUND_DIR_ALIASES.get(head, head)
                cue = segs[-1] if len(segs) > 1 else head

            valid = _sound_dir_exists(sdir)
            candidates.append({'dir': sdir, 'cue': cue, 'valid': valid})

        if not candidates:
            return None
        # Prefer a valid entry whose cue is a known engine cue
        for c in candidates:
            if c['valid'] and c['cue'] in _ENGINE_CUES:
                return c
        # Fallback: any valid entry
        for c in candidates:
            if c['valid']:
                return c
        # Fallback: first known-cue entry (may be invalid/broken path)
        for c in candidates:
            if c['cue'] in _ENGINE_CUES:
                return c
        return candidates[0]
    except Exception:
        pass
    return None


def list_sounds() -> Dict:
    """Return available sound dirs from the base game,
    grouped by SoundCue type, with source attribution per entry."""
    result: Dict = {'by_cue': {}, 'bike': [], 'electric': False}
    seen_dirs: Dict[str, str] = {}  # dir_name -> source (first seen wins)

    scan_sources = [
        (BASE_SOUND_BASE, 'base'),
        (MOD_SOUND_BASE, 'mod'),
    ]
    _skip = frozenset({'Backfire', 'Intake', 'jake'})

    for sound_base, source in scan_sources:
        if not os.path.isdir(sound_base):
            continue
        try:
            for entry in sorted(os.scandir(sound_base), key=lambda e: e.name):
                if not entry.is_dir():
                    continue
                dname = entry.name
                if dname == 'Bike':
                    for f in sorted(os.scandir(entry.path), key=lambda e: e.name):
                        if f.name.endswith('.uasset') and not f.is_dir():
                            bname = f.name.replace('.uasset', '')
                            key = f'Bike/{bname}'
                            if key not in seen_dirs:
                                seen_dirs[key] = source
                                result['bike'].append({'dir': bname, 'source': source})
                    continue
                if dname == 'Electric':
                    if not result['electric']:
                        result['electric'] = {'source': source}
                    continue
                if dname in _skip:
                    continue
                if dname in seen_dirs:
                    continue  # base game takes precedence over mod duplicates
                # Find main SC_* cue; prefer a known engine cue if multiple exist
                sc_files = sorted(
                    f.name for f in os.scandir(entry.path)
                    if f.name.endswith('.uasset') and f.name.startswith('SC_') and not f.is_dir()
                )
                if not sc_files:
                    # Fallback: dirs that use EngineSoundData subdirs (e.g. V6Sport)
                    has_engine_data = any(
                        any(f2.name in ('EngineSoundData.uasset',) or f2.name.endswith('_EngineSoundData.uasset')
                            for f2 in os.scandir(sub.path) if not f2.is_dir())
                        for sub in os.scandir(entry.path) if sub.is_dir()
                    )
                    if has_engine_data:
                        seen_dirs[dname] = source
                        result['by_cue'].setdefault('SC_V8Engine', []).append({'dir': dname, 'source': source})
                    continue
                cue_file = next(
                    (f for f in sc_files if f.replace('.uasset', '') in _ENGINE_CUES),
                    sc_files[0]
                )
                cue = cue_file.replace('.uasset', '')
                seen_dirs[dname] = source
                result['by_cue'].setdefault(cue, []).append({'dir': dname, 'source': source})
        except Exception:
            pass
    return result


def get_part_detail(part_path: str) -> Dict:
    """Get detailed data for a specific part."""
    uexp_path, uasset_path, parser_type, source = _resolve_part_path(part_path)
    if source == 'mod' and parser_type == 'engine':
        engine_name = os.path.splitext(os.path.basename(uexp_path))[0]
        if not _is_site_engine(engine_name):
            return {'error': 'Only user-generated engines are shown in this editor.'}
    if source == 'mod' and parser_type == 'tire':
        tire_name = os.path.splitext(os.path.basename(uexp_path))[0]
        if not _is_site_tire(tire_name):
            return {'error': 'Only user-generated tires are shown in this editor.'}
    lock_ctx = MOD_WRITE_LOCK if source == 'mod' else nullcontext()
    with lock_ctx:
        # Read uexp data
        with open(uexp_path, 'rb') as f:
            uexp_data = f.read()

        # Parse uasset for metadata
        asset_info = {}
        if os.path.isfile(uasset_path):
            try:
                asset = parse_uasset(uasset_path)
                asset_info = {
                    'class_type': asset.class_type,
                    'asset_name': asset.asset_name,
                    'asset_path': asset.asset_path,
                    'torque_curve_name': asset.torque_curve_name,
                    'sound_refs': asset.sound_refs,
                }
            except Exception:
                pass

        # Parse uexp based on type
        properties = {}
        metadata = {}
        curve_data = None

        try:
            if parser_type == 'engine':
                engine = parse_engine(uexp_data)
                properties = _build_complete_engine_properties(engine)
                engine_field_catalog = _load_engine_field_catalog()
                supported_properties = list(engine.properties.keys())
                known_properties = list(engine_field_catalog.get('all_properties') or supported_properties)
                variant_info = (engine_field_catalog.get('variants') or {}).get(engine.variant.value, {})
                possible_properties = list(variant_info.get('properties') or supported_properties)
                missing_known_properties = [
                    key for key in known_properties
                    if key not in engine.properties
                ]
                # Compute HP from actual torque curve when available
                _eng_dir = os.path.dirname(uexp_path)
                _eng_name = os.path.splitext(os.path.basename(uexp_path))[0]
                _curve_hp = _compute_hp_from_curve(
                    _eng_dir, _eng_name,
                    engine.max_torque_nm, engine.max_rpm,
                )
                _display_hp = _curve_hp if _curve_hp > 0 else round(engine.estimated_hp(), 1)

                # Load saved creation inputs for fork persistence
                _creation_meta = _load_creation_meta(_eng_dir, _eng_name)

                # Prefer the user-entered Max HP over the curve estimate
                _user_hp = _creation_meta.get('max_hp', 0) if _creation_meta else 0
                if _user_hp and float(_user_hp) > 0:
                    _display_hp = round(float(_user_hp), 1)

                metadata = {
                    'variant': engine.variant.value,
                    'estimated_hp': _display_hp,
                    'max_torque_nm': round(engine.max_torque_nm, 1),
                    'max_rpm': round(engine.max_rpm, 0),
                    'is_ev': engine.is_ev,
                    'property_count': len(supported_properties),
                    'supported_properties': supported_properties,
                    'known_properties': known_properties,
                    'known_property_count': len(known_properties),
                    'missing_known_properties': missing_known_properties,
                    'possible_properties': possible_properties,
                    'possible_property_count': len(possible_properties),
                    'missing_possible_properties': [
                        key for key in possible_properties
                        if key not in engine.properties
                    ],
                    'tail_imports': engine.tail_imports,
                }
                if engine.is_ev:
                    metadata['motor_max_power_kw'] = round(engine.motor_max_power_kw, 1)

                if _creation_meta:
                    metadata['creation_inputs'] = _creation_meta
                else:
                    # No saved creation metadata (typical for vanilla donors and
                    # any engine not produced by Frog Mod Editor). Derive the
                    # creator-form fields from the torque curve when available,
                    # otherwise from type-appropriate defaults, so that forking
                    # pre-fills "Max Torque @ RPM" and "Max HP @ RPM" with
                    # sensible donor-derived values instead of leaving them
                    # blank.
                    _derived_peaks = _compute_curve_peaks(
                        _eng_dir, _eng_name,
                        engine.max_torque_nm, engine.max_rpm,
                        is_ev=engine.is_ev,
                        estimated_hp=_display_hp,
                    )
                    if _derived_peaks:
                        metadata['creation_inputs'] = _derived_peaks

                # Sound metadata — parse name table for engine-specific sound path
                if os.path.isfile(uasset_path):
                    sound_meta = _extract_sound_meta(uasset_path)
                    if sound_meta:
                        metadata['sound'] = sound_meta

                # Load shop entry from Engines DataTable (always set for engines)
                try:
                    from parsers.uasset_engines_dt import get_fname_index
                    from parsers.uexp_engines_dt import read_row as read_dt_row
                    engine_key = os.path.splitext(os.path.basename(uexp_path))[0]
                    dt_uasset_p = ENGINES_DT_BASE + '.uasset'
                    dt_uexp_p   = ENGINES_DT_BASE + '.uexp'
                    _shop_default = _default_shop_values_for_engine(
                        engine_key,
                        engine.variant.value,
                        _display_hp,
                        round(engine.max_torque_nm, 1),
                    )
                    if source != 'template' and os.path.isfile(dt_uasset_p) and os.path.isfile(dt_uexp_p):
                        with open(dt_uasset_p, 'rb') as _f:
                            _ua = _f.read()
                        with open(dt_uexp_p, 'rb') as _f:
                            _ue = _f.read()
                        _fidx = get_fname_index(_ua, engine_key)
                        if _fidx >= 0:
                            _shop = read_dt_row(_ue, _fidx)
                            if _shop:
                                _shop['exists'] = True
                                metadata['shop'] = _shop
                            else:
                                metadata['shop'] = _shop_default
                        else:
                            metadata['shop'] = _shop_default
                    else:
                        metadata['shop'] = _shop_default
                except Exception:
                    pass  # shop data is optional; never crash part load

            elif parser_type == 'tire':
                tire = parse_tire(uexp_data)
                properties = _build_complete_tire_properties(tire)
                file_name = os.path.splitext(os.path.basename(uexp_path))[0]
                tire_field_catalog = _load_tire_field_catalog()
                supported_properties = list(tire.property_order)
                known_properties = list(tire_field_catalog.get('all_properties') or supported_properties)
                missing_known_properties = [
                    key for key in known_properties
                    if key not in tire.properties
                ]
                metadata = {
                    'family': f'{len(tire.property_order)}-float',
                    'property_count': len(tire.property_order),
                    'supported_properties': supported_properties,
                    'known_properties': known_properties,
                    'known_property_count': len(known_properties),
                    'missing_known_properties': missing_known_properties,
                }
                group_key, group_label = _classify_tire_group(file_name)
                group_info = tire_field_catalog.get('groups', {}).get(group_key)
                if source == 'vanilla' and group_info:
                    possible_properties = list(group_info.get('properties') or supported_properties)
                    metadata.update({
                        'group_key': group_key,
                        'group_label': group_label,
                        'possible_properties': possible_properties,
                        'possible_property_count': len(possible_properties),
                        'missing_possible_properties': [
                            key for key in possible_properties
                            if key not in tire.properties
                        ],
                    })
                else:
                    metadata.update({
                        'possible_properties': known_properties,
                        'possible_property_count': len(known_properties),
                        'missing_possible_properties': missing_known_properties,
                    })
                # Load saved creation inputs for persistence
                if source == 'mod':
                    _tire_creation_meta = _load_creation_meta(
                        os.path.dirname(uexp_path), file_name,
                    )
                    if _tire_creation_meta:
                        metadata['creation_inputs'] = _tire_creation_meta

                if os.path.isfile(uasset_path):
                    try:
                        asset_name = asset_info.get('asset_name', '') if asset_info else ''
                        vp_rows = _lookup_tire_vehicleparts_rows(source, asset_name, file_name)
                        if vp_rows:
                            metadata['vehicle_parts'] = vp_rows
                            preferred = vp_rows.get('preferred_row') or _select_preferred_tire_vehicleparts_row(vp_rows.get('rows', []), file_name)
                            if preferred:
                                defaults = _default_tire_shop_values(file_name, preferred, preferred.get('weight'))
                                metadata['shop'] = {
                                    'exists': True,
                                    **defaults,
                                    'row_name': preferred.get('row_name', ''),
                                    'row_number': preferred.get('fname_number', 0),
                                }
                        else:
                            metadata['shop'] = {
                                'exists': False,
                                **_default_tire_shop_values(file_name, None, 10.0),
                            }
                    except Exception:
                        pass

            elif parser_type == 'transmission':
                trans = parse_transmission(uexp_data)
                properties = trans.to_display_dict()
                metadata = {
                    'num_forward_gears': trans.num_forward_gears,
                    'total_gears': len(trans.gears),
                    'description': trans.description,
                }

            elif parser_type == 'lsd':
                lsd = parse_lsd(uexp_data)
                properties = lsd.to_display_dict()

            elif parser_type == 'torquecurve':
                curve = parse_torque_curve(uexp_data)
                properties = curve.to_display_dict()
                curve_data = {
                    'points': [{'time': k.time, 'value': k.value} for k in curve.keys],
                    'peak_factor': round(curve.find_peak_power_factor(), 4),
                }

        except Exception as e:
            properties = {'_error': {'raw': str(e), 'display': str(e), 'unit': ''}}

    return {
        'path': part_path,
        'name': os.path.splitext(os.path.basename(uexp_path))[0],
        'type': parser_type,
        'source': source,
        'can_delete': (
            source == 'mod' and (
                (parser_type == 'engine' and _is_site_engine(os.path.splitext(os.path.basename(uexp_path))[0]))
                or (parser_type == 'tire' and _is_site_tire(os.path.splitext(os.path.basename(uexp_path))[0]))
            )
        ),
        'uexp_size': len(uexp_data),
        'asset_info': asset_info,
        'properties': properties,
        'metadata': metadata,
        'curve_data': curve_data,
        'state_version': _current_live_state()['version'],
    }


def save_part(part_path: str, data: Dict) -> Dict:
    """Save modified property values for a part."""
    uexp_path, uasset_path, parser_type, source = _resolve_part_path(part_path)
    if source != 'mod':
        return {'error': 'Only generated mod assets can be edited from this site.'}
    if parser_type == 'engine':
        engine_name = os.path.splitext(os.path.basename(uexp_path))[0]
        if not _is_site_engine(engine_name):
            return {'error': 'Only user-generated engines can be edited from this site.'}
    if parser_type == 'tire':
        tire_name = os.path.splitext(os.path.basename(uexp_path))[0]
        if not _is_site_tire(tire_name):
            return {'error': 'Only user-generated tires can be edited from this site.'}

    expected_version = (data.get('expected_version') or '').strip()

    with MOD_WRITE_LOCK:
        live_conflict = _check_live_version(expected_version)
        if live_conflict:
            return {
                'error': 'Live data changed. Reload and try again.',
                'conflict': True,
                'state_version': live_conflict['version'],
            }

        # Read current data
        with open(uexp_path, 'rb') as f:
            uexp_data = f.read()

        # Keep a persistent user-visible backup plus per-save rollback backups.
        os.makedirs(BACKUP_DIR, exist_ok=True)
        backup_name = part_path.replace('/', '_') + '.uexp.bak'
        backup_path = os.path.join(BACKUP_DIR, backup_name)
        if not os.path.exists(backup_path):
            shutil.copy2(uexp_path, backup_path)
        rollback_uexp = os.path.join(BACKUP_DIR, part_path.replace('/', '_') + '.uexp.current.bak')
        shutil.copy2(uexp_path, rollback_uexp)

        rollback_uasset = None
        if os.path.isfile(uasset_path):
            rollback_uasset = os.path.join(BACKUP_DIR, part_path.replace('/', '_') + '.uasset.current.bak')
            shutil.copy2(uasset_path, rollback_uasset)

        dt_uasset_p = ENGINES_DT_BASE + '.uasset'
        dt_uexp_p = ENGINES_DT_BASE + '.uexp'
        vp_uasset_p = MOD_VEHICLEPARTS0_BASE + '.uasset'
        vp_uexp_p = MOD_VEHICLEPARTS0_BASE + '.uexp'
        rollback_dt_ua = None
        rollback_dt_ue = None
        if parser_type == 'engine' and os.path.isfile(dt_uasset_p) and os.path.isfile(dt_uexp_p):
            rollback_dt_ua = os.path.join(BACKUP_DIR, 'Engines_dt.uasset.current.bak')
            rollback_dt_ue = os.path.join(BACKUP_DIR, 'Engines_dt.uexp.current.bak')
            shutil.copy2(dt_uasset_p, rollback_dt_ua)
            shutil.copy2(dt_uexp_p, rollback_dt_ue)
        if parser_type == 'tire':
            try:
                vp_uasset_p, vp_uexp_p = _ensure_mod_vehicleparts0_files()
            except Exception as exc:
                return {'error': f'Failed to prepare VehicleParts0: {exc}'}
            rollback_dt_ua = os.path.join(BACKUP_DIR, 'VehicleParts0_dt.uasset.current.bak')
            rollback_dt_ue = os.path.join(BACKUP_DIR, 'VehicleParts0_dt.uexp.current.bak')
            shutil.copy2(vp_uasset_p, rollback_dt_ua)
            shutil.copy2(vp_uexp_p, rollback_dt_ue)

        # Apply changes based on type
        modified_props = data.get('properties', {})
        new_data = None
        applied_property_changes = len(modified_props)

        try:
            if parser_type == 'engine':
                engine = parse_engine(uexp_data)
                for key, value in modified_props.items():
                    if _is_blank_optional_value(value):
                        continue
                    if key in engine.properties:
                        # Convert from display value back to raw
                        if key == 'MaxTorque':
                            engine.properties[key] = float(value) * 10000
                        elif key == 'MotorMaxPower':
                            engine.properties[key] = float(value) * 10000
                        elif key == 'MotorMaxVoltage':
                            engine.properties[key] = float(value) * 10000
                        elif key in ('FuelType', 'EngineType', 'MaxJakeBrakeStep', 'TorqueCurve'):
                            engine.properties[key] = int(value)
                        else:
                            engine.properties[key] = float(value)
                new_data = serialize_engine(engine)

            elif parser_type == 'tire':
                tire = parse_tire(uexp_data)
                new_data, applied_property_changes = _apply_tire_property_changes(
                    tire,
                    modified_props,
                    tire_field_catalog=_load_tire_field_catalog(),
                )
                if applied_property_changes == 0:
                    new_data = None

            elif parser_type == 'transmission':
                from parsers.uexp_transmission import GearRecord, _get_property_names
                trans = parse_transmission(uexp_data)
                prop_names = _get_property_names(len(trans.tail_floats))
                name_to_idx = {name: i for i, (name, _) in enumerate(prop_names)}

                for key, value in modified_props.items():
                    if key.endswith('_Ratio') and key.startswith('Gear_'):
                        idx = int(key.split('_')[1])
                        if idx < len(trans.gears):
                            trans.gears[idx].ratio = float(value)
                    elif key.endswith('_Label') and key.startswith('Gear_'):
                        idx = int(key.split('_')[1])
                        if idx < len(trans.gears):
                            new_label = str(value).strip()
                            trans.gears[idx].label = new_label
                            trans.gears[idx].gear_type = len(new_label) + 1
                    elif key in name_to_idx:
                        idx = name_to_idx[key]
                        if idx < len(trans.tail_floats):
                            trans.tail_floats[idx] = float(value)
                    elif key.startswith('Property_'):
                        idx = int(key.split('_')[1])
                        if idx < len(trans.tail_floats):
                            trans.tail_floats[idx] = float(value)
                    elif key == 'DefaultGearIndex':
                        trans.default_gear_index = int(value)
                    elif key == 'Description':
                        trans.description = str(value)
                        trans.description_length = len(trans.description) + 1
                    elif key == 'GearCount':
                        target = max(1, int(value))
                        current = len(trans.gears)
                        delta = target - current
                        if delta > 0:
                            last = trans.gears[-1] if trans.gears else None
                            for i in range(delta):
                                new_num = current + i + 1
                                label = str(new_num)
                                gtype = len(label) + 1
                                ratio = round(last.ratio * 0.85, 4) if last else 1.0
                                new_gear = GearRecord(label=label, ratio=ratio, efficiency=100.0, gear_type=gtype)
                                trans.gears.append(new_gear)
                                last = new_gear
                        elif delta < 0:
                            trans.gears = trans.gears[:target]
                        hdr = bytearray(trans.header_bytes)
                        hdr[-1] = len(trans.gears)
                        trans.header_bytes = bytes(hdr)
                new_data = serialize_transmission(trans)

            elif parser_type == 'lsd':
                lsd = parse_lsd(uexp_data)
                for key, value in modified_props.items():
                    if key in lsd.properties:
                        lsd.properties[key] = float(value)
                new_data = serialize_lsd(lsd)

            elif parser_type == 'torquecurve':
                curve = parse_torque_curve(uexp_data)
                for key, value in modified_props.items():
                    if key.startswith('Key_') and key.endswith('_Time'):
                        idx = int(key.split('_')[1])
                        if idx < len(curve.keys):
                            curve.keys[idx].time = float(value)
                    elif key.startswith('Key_') and key.endswith('_Value'):
                        idx = int(key.split('_')[1])
                        if idx < len(curve.keys):
                            curve.keys[idx].value = float(value)
                new_data = serialize_torque_curve(curve)

        except Exception as e:
            return {'error': f'Failed to apply changes: {str(e)}'}

        shop = data.get('shop') or {}
        new_sound_dir = data.get('sound_dir') or ''
        if new_data is None and not shop and not new_sound_dir:
            return {'error': 'No changes applied'}

        saved_msg = ''

        if new_data is not None:
            if parser_type not in ('transmission', 'tire') and len(new_data) != len(uexp_data):
                return {'error': f'Size mismatch! Original={len(uexp_data)}, New={len(new_data)}. Aborting.'}

            if parser_type == 'tire' and os.path.isfile(uasset_path):
                with open(uasset_path, 'rb') as f:
                    current_uasset = f.read()
                patched_uasset = _patch_uasset_serial_size(current_uasset, len(new_data))
                if patched_uasset != current_uasset:
                    with open(uasset_path, 'wb') as f:
                        f.write(patched_uasset)

            with open(uexp_path, 'wb') as f:
                f.write(new_data)

            saved_msg = f'Saved {applied_property_changes} change(s) to {os.path.basename(uexp_path)}'
        else:
            saved_msg = f'No property changes to {os.path.basename(uexp_path)}'

        if new_sound_dir and parser_type == 'engine' and os.path.isfile(uasset_path):
            try:
                from parsers.uasset_clone import update_sound_in_uasset
                uasset_bak = os.path.join(BACKUP_DIR, uasset_path.replace('/', '_').replace('\\', '_') + '.bak')
                if not os.path.exists(uasset_bak):
                    shutil.copy2(uasset_path, uasset_bak)
                update_sound_in_uasset(uasset_path, new_sound_dir)
                saved_msg += f'; sound updated to {new_sound_dir}'
            except Exception as _snd_err:
                saved_msg += f' [sound update skipped: {_snd_err}]'

        if shop and parser_type == 'engine':
            try:
                engine_key = os.path.splitext(os.path.basename(uexp_path))[0]

                dt_backup = os.path.join(BACKUP_DIR, 'Engines_dt.uexp.bak')
                if not os.path.exists(dt_backup) and os.path.isfile(dt_uexp_p):
                    shutil.copy2(dt_uexp_p, dt_backup)
                dt_ua_backup = os.path.join(BACKUP_DIR, 'Engines_dt.uasset.bak')
                if not os.path.exists(dt_ua_backup) and os.path.isfile(dt_uasset_p):
                    shutil.copy2(dt_uasset_p, dt_ua_backup)

                if os.path.isfile(dt_uasset_p) and os.path.isfile(dt_uexp_p):
                    with open(dt_uasset_p, 'rb') as _f:
                        _ua = _f.read()
                    with open(dt_uexp_p, 'rb') as _f:
                        _ue = _f.read()

                    raw_display = str(shop.get('display_name', engine_key) or '').strip() or engine_key
                    raw_description = str(shop.get('description') or '').strip()
                    new_display = raw_display
                    new_description = raw_description
                    try:
                        from template_engines import split_shop_display as _split_shop_display
                        split_display, split_description = _split_shop_display(raw_display)
                        new_display = split_display
                        new_description = raw_description or split_description
                    except Exception:
                        pass
                    new_price = max(0, int(float(shop.get('price', 5000))))
                    new_weight = max(0.0, float(shop.get('weight', 50.0)))
                    try:
                        from parsers.uexp_engine import detect_variant as _detect_variant
                        _variant_data = new_data if new_data is not None else uexp_data
                        _variant = _detect_variant(_variant_data).value
                    except Exception:
                        _variant = 'ice_standard'

                    _ua, _ue, _action = _register_engine_datatable_entry(
                        _ua, _ue, engine_key, new_display, new_price, new_weight, _variant,
                        update_existing=True, description=new_description
                    )
                    _ua = _patch_datatable_serial_size(_ua, len(_ue))
                    with open(dt_uasset_p, 'wb') as _f:
                        _f.write(_ua)
                    with open(dt_uexp_p, 'wb') as _f:
                        _f.write(_ue)
                    verb = 'updated' if _action == 'updated' else 'created'
                    saved_msg += f'; shop {verb} ({new_display}, ${new_price}, {new_weight}kg)'
            except Exception as _shop_err:
                saved_msg += f' [shop update skipped: {_shop_err}]'

        if shop and parser_type == 'tire':
            try:
                tire_key = os.path.splitext(os.path.basename(uexp_path))[0]
                with open(vp_uasset_p, 'rb') as _f:
                    _ua = _f.read()
                with open(vp_uexp_p, 'rb') as _f:
                    _ue = _f.read()

                raw_display = str(shop.get('display_name') or tire_key).strip() or tire_key
                raw_code = str(shop.get('code') or '').strip()
                new_price = max(0, int(float(shop.get('price', 500))))
                new_weight = max(0.0, float(shop.get('weight', 10.0)))

                _ua, _ue, _action = _register_tire_vehicleparts_entry(
                    _ua,
                    _ue,
                    tire_key,
                    display_name=raw_display,
                    code=raw_code,
                    price=new_price,
                    weight=new_weight,
                )
                _ua = _patch_uasset_serial_size(_ua, len(_ue))
                with open(vp_uasset_p, 'wb') as _f:
                    _f.write(_ua)
                with open(vp_uexp_p, 'wb') as _f:
                    _f.write(_ue)
                _invalidate_vehicleparts0_catalog(MOD_VEHICLEPARTS0_BASE)
                verb = 'updated' if _action == 'updated' else 'created'
                saved_msg += f'; shop {verb} ({raw_display}, ${new_price}, {new_weight}kg)'
            except Exception as _shop_err:
                saved_msg += f' [shop update skipped: {_shop_err}]'

        if parser_type == 'engine':
            try:
                from engine_validation import validate_engine_asset_pair, validate_engine_datatable
                validation_errors = validate_engine_asset_pair(uasset_path, uexp_path, expected_name=os.path.splitext(os.path.basename(uexp_path))[0])
                validation_errors.extend(validate_engine_datatable(dt_uasset_p, dt_uexp_p, [os.path.splitext(os.path.basename(uexp_path))[0]]))
                if validation_errors:
                    raise ValueError('; '.join(validation_errors[:6]))
            except Exception as exc:
                _restore_backup(rollback_uexp, uexp_path)
                _restore_backup(rollback_uasset, uasset_path)
                _restore_backup(rollback_dt_ua, dt_uasset_p)
                _restore_backup(rollback_dt_ue, dt_uexp_p)
                return {'error': f'Save failed validation: {exc}'}
        elif parser_type == 'tire':
            try:
                _validate_tire_generation(uasset_path, uexp_path, os.path.splitext(os.path.basename(uexp_path))[0], vp_uasset_p, vp_uexp_p)
            except Exception as exc:
                _restore_backup(rollback_uexp, uexp_path)
                _restore_backup(rollback_uasset, uasset_path)
                _restore_backup(rollback_dt_ua, vp_uasset_p)
                _restore_backup(rollback_dt_ue, vp_uexp_p)
                _invalidate_vehicleparts0_catalog(MOD_VEHICLEPARTS0_BASE)
                return {'error': f'Save failed validation: {exc}'}

        return {
            'success': True,
            'message': saved_msg,
            'backup': backup_path,
            'state_version': _current_live_state()['version'],
        }


def delete_engine(data: Dict) -> Dict:
    """Delete a generated mod engine and prune its shop row."""
    part_path = (data.get('path') or '').strip()
    expected_version = (data.get('expected_version') or '').strip()
    if not part_path:
        return {'error': 'No engine path specified'}

    try:
        uexp_path, uasset_path, parser_type, source = _resolve_part_path(part_path)
    except Exception as exc:
        return {'error': str(exc)}

    if source != 'mod' or parser_type != 'engine':
        return {'error': 'Only generated mod engines can be deleted from this site.'}

    engine_name = os.path.splitext(os.path.basename(uexp_path))[0]
    if not _is_site_engine(engine_name):
        return {'error': 'Only user-generated engines can be deleted from this site.'}
    mt_root = os.path.join(MOD_ROOT, 'MotorTown')
    dt_uasset_path = ENGINES_DT_BASE + '.uasset'
    dt_uexp_path = ENGINES_DT_BASE + '.uexp'

    with MOD_WRITE_LOCK:
        live_conflict = _check_live_version(expected_version)
        if live_conflict:
            return {
                'error': 'Live data changed. Reload and try again.',
                'conflict': True,
                'state_version': live_conflict['version'],
            }

        missing = [path for path in (uasset_path, uexp_path) if not os.path.isfile(path)]
        if missing:
            return {'error': f'Engine files not found for {engine_name}'}

        os.makedirs(BACKUP_DIR, exist_ok=True)
        rollback_uasset = os.path.join(BACKUP_DIR, f'delete_{engine_name}.uasset.current.bak')
        rollback_uexp = os.path.join(BACKUP_DIR, f'delete_{engine_name}.uexp.current.bak')
        shutil.copy2(uasset_path, rollback_uasset)
        shutil.copy2(uexp_path, rollback_uexp)

        rollback_dt_ua = None
        rollback_dt_ue = None
        if os.path.isfile(dt_uasset_path) and os.path.isfile(dt_uexp_path):
            rollback_dt_ua = os.path.join(BACKUP_DIR, 'delete_Engines_dt.uasset.current.bak')
            rollback_dt_ue = os.path.join(BACKUP_DIR, 'delete_Engines_dt.uexp.current.bak')
            shutil.copy2(dt_uasset_path, rollback_dt_ua)
            shutil.copy2(dt_uexp_path, rollback_dt_ue)

        try:
            for path in (uasset_path, uexp_path):
                os.remove(path)
            # Clean up creation metadata
            _creation_json = os.path.join(os.path.dirname(uexp_path), engine_name + '.creation.json')
            if os.path.isfile(_creation_json):
                os.remove(_creation_json)
            sync_result = _sync_engine_datatable_tree(mt_root, prefer_existing_shop=True)
            from engine_validation import validate_engine_generation_tree
            validation = validate_engine_generation_tree(mt_root)
            if not validation['valid']:
                preview = '; '.join(validation['errors'][:6])
                extra = '' if len(validation['errors']) <= 6 else f' (+{len(validation["errors"]) - 6} more)'
                raise ValueError(f'Delete validation failed: {preview}{extra}')
        except Exception as exc:
            _restore_backup(rollback_uasset, uasset_path)
            _restore_backup(rollback_uexp, uexp_path)
            _restore_backup(rollback_dt_ua, dt_uasset_path)
            _restore_backup(rollback_dt_ue, dt_uexp_path)
            return {'error': f'Failed to resync engine list after delete: {exc}'}

        _unregister_site_engine(engine_name)
        return {
            'success': True,
            'deleted': engine_name,
            'sync': sync_result,
            'message': f'Deleted {engine_name}',
            'state_version': _current_live_state()['version'],
        }


def get_torque_curve(curve_name: str) -> Dict:
    """Get torque curve data by name for visualization."""
    # Search in vanilla (curves are in base game)
    tc_dir = os.path.join(VANILLA_BASE, 'Engine', 'TorqueCurve')
    uexp_path = os.path.join(tc_dir, f'{curve_name}.uexp')

    if not os.path.isfile(uexp_path):
        return {'error': f'Torque curve not found: {curve_name}'}

    with open(uexp_path, 'rb') as f:
        data = f.read()

    curve = parse_torque_curve(data)
    return {
        'name': curve_name,
        'points': [{'time': k.time, 'value': k.value} for k in curve.keys],
        'peak_factor': round(curve.find_peak_power_factor(), 4),
    }


def _get_all_part_paths() -> set:
    """Get set of all known part paths (for comparing against selection)."""
    all_paths = set()
    for type_name, (dir_name, parser_type) in PART_TYPES.items():
        for source, base in [('mod', MOD_BASE), ('vanilla', VANILLA_BASE)]:
            part_dir = os.path.join(base, dir_name)
            if os.path.isdir(part_dir):
                for f in glob.glob(os.path.join(part_dir, '*.uexp')):
                    name = os.path.splitext(os.path.basename(f))[0]
                    all_paths.add(f'{source}/{dir_name}/{name}')
    return all_paths


def _pak_output_path(raw: str) -> str:
    """Normalise an output path: strip .pak, ensure _P suffix, re-add .pak."""
    p = raw.strip()
    if p.lower().endswith('.pak'):
        p = p[:-4]
    if not p.endswith('_P'):
        p += '_P'
    return p + '.pak'


def pack_mod(output_path: str = '', parts_to_include: List[str] = None) -> Dict:
    """Pack modified files into a .pak, optionally filtering to selected parts.

    Pak paths are rooted at MotorTown/ (matching the game's content directory).
    """
    import tempfile

    if not output_path or not output_path.strip():
        return {'error': 'No output path provided'}

    output_path = _pak_output_path(output_path)

    # Source is data/mod/MotorTown  →  pak paths become MotorTown/Content/...
    motortow_dir = os.path.join(MOD_ROOT, 'MotorTown')
    if not os.path.isdir(motortow_dir):
        return {'error': f'Mod directory not found: {motortow_dir}'}

    # Always stage a temp tree so pack-time sync never mutates the working copy.
    temp_dir = None
    pack_source = None
    included_set = set(parts_to_include) if parts_to_include else None
    all_parts = _get_all_part_paths()
    excluded = (all_parts - included_set) if included_set is not None else set()

    try:
        temp_dir = tempfile.mkdtemp(prefix='mte_pack_')
        temp_motortow = os.path.join(temp_dir, 'MotorTown')
        shutil.copytree(motortow_dir, temp_motortow)
        pack_source = temp_motortow

        if excluded:
            temp_parts_base = os.path.join(temp_motortow, 'Content', 'Cars', 'Parts')
            for part_path in excluded:
                parts = part_path.split('/')
                if len(parts) >= 3 and parts[0] == 'mod':
                    name = parts[-1]
                    dir_name = '/'.join(parts[1:-1])
                    for ext in ['.uexp', '.uasset']:
                        fpath = os.path.join(temp_parts_base, dir_name, name + ext)
                        if os.path.isfile(fpath):
                            os.remove(fpath)
    except Exception as e:
        if temp_dir and os.path.isdir(temp_dir):
            shutil.rmtree(temp_dir)
        return {'error': f'Failed to prepare pack staging: {str(e)}'}

    try:
        # Remove .creation.json metadata files — not game assets
        import glob as _glob
        for _cj in _glob.glob(os.path.join(pack_source, '**', '*.creation.json'), recursive=True):
            os.remove(_cj)

        # Keep Config/ in the pak (the game reads some INI fields from it)
        # AND also deploy as a loose file below (some fields need that).

        sync_result = _sync_engine_datatable_tree(pack_source, prefer_existing_shop=True)
        staged_vp_uasset = os.path.join(pack_source, 'Content', 'DataAsset', 'VehicleParts', 'VehicleParts0.uasset')
        staged_vp_uexp = os.path.join(pack_source, 'Content', 'DataAsset', 'VehicleParts', 'VehicleParts0.uexp')
        if os.path.isfile(staged_vp_uasset) and os.path.isfile(staged_vp_uexp):
            _sync_uasset_serial_size_file(staged_vp_uasset, staged_vp_uexp)
            _validate_uasset_serial_size(staged_vp_uasset, staged_vp_uexp, 'VehicleParts0')
        from engine_validation import validate_engine_generation_tree
        validation = validate_engine_generation_tree(pack_source)
        if not validation['valid']:
            preview = '; '.join(validation['errors'][:6])
            extra = '' if len(validation['errors']) <= 6 else f' (+{len(validation["errors"]) - 6} more)'
            return {'error': f'Pack validation failed: {preview}{extra}', 'validation': validation}
        from parsers.pak_writer import write_pak
        result = write_pak(pack_source, output_path)

        # Deploy the modified INI as a loose file in the game's Config
        # directory.  UE4 does not load .ini from pak archives.
        # Balance.json stays in the pak — the game reads it fine from there.
        ini_deploy = {}
        try:
            from economy_editor import deploy_ini_to_game_only
            ini_deploy = deploy_ini_to_game_only(output_path)
        except Exception as ini_err:
            ini_deploy = {'error': str(ini_err)}

        pack_msg = (f'Packed to {output_path} '
                    f'({sync_result["created"]} created, {sync_result["updated"]} updated, '
                    f'{len(sync_result["removed"])} removed)')
        if ini_deploy.get('deployed_to'):
            pack_msg += f'\nEconomy INI → {ini_deploy["deployed_to"]}'
        elif ini_deploy.get('error'):
            pack_msg += f'\nINI deploy warning: {ini_deploy["error"]}'

        return {
            'success': True,
            'message': pack_msg,
            'pak_size': result['pak_size'],
            'file_count': result['file_count'],
            'sync': sync_result,
            'ini_deploy': ini_deploy,
        }
    except Exception as e:
        return {'error': f'Pack failed: {str(e)}'}
    finally:
        if temp_dir and os.path.isdir(temp_dir):
            shutil.rmtree(temp_dir)


def _patch_uasset_serial_size(uasset_data: bytes, uexp_size: int) -> bytes:
    """Patch SerialSize in a .uasset export table to match the .uexp file size.

    UE reads exactly SerialSize bytes from the .uexp. If this doesn't match
    the actual file size, the engine reads past the end or stops short.
    """
    import struct as _s
    from parsers.uasset_clone import _read_fstring
    data = bytearray(uasset_data)
    _, fb = _read_fstring(bytes(data), 32)
    fe = 32 + fb
    export_count = _s.unpack_from('<i', data, fe + 28)[0]
    export_offset = _s.unpack_from('<i', data, fe + 32)[0]
    depends_offset = _s.unpack_from('<i', data, fe + 44)[0]
    if export_count <= 0 or export_offset <= 0:
        return bytes(data)
    entry_size = (depends_offset - export_offset) // export_count if depends_offset > export_offset else 96
    # Original relationship: SerialSize = uexp_size - overhead
    # For Engines DataTable: overhead = 4 (the uexp has 4 extra bytes vs SerialSize)
    # Detect overhead from current values
    old_serial_size = _s.unpack_from('<q', data, export_offset + 28)[0]
    old_serial_offset = _s.unpack_from('<q', data, export_offset + 36)[0]
    # overhead = old_uexp_size - old_serial_size (we don't know old_uexp_size directly)
    # But we know: new_serial_size should scale proportionally
    # Safest: SerialSize = uexp_size - (TotalHeaderSize - SerialOffset) ... no
    # Actually from our data: orig uexp=64601, SerialSize=64597, diff=4
    # The 4-byte diff is consistent: it's the UObject None-property terminator
    # that's outside the counted serial data. Let's use uexp_size - 4.
    new_serial_size = uexp_size - 4
    _s.pack_into('<q', data, export_offset + 28, new_serial_size)
    # Also update SerialOffset to match TotalHeaderSize (for consistency)
    total_hdr = _s.unpack_from('<i', data, 28)[0]
    _s.pack_into('<q', data, export_offset + 36, total_hdr)
    # Update BulkDataStartOffset (field[35]) = TotalHeaderSize + SerialSize
    bulk_data_start = total_hdr + new_serial_size
    _s.pack_into('<i', data, fe + 35 * 4, bulk_data_start)
    return bytes(data)


def _patch_datatable_serial_size(uasset_data: bytes, uexp_size: int) -> bytes:
    """Backward-compatible wrapper for DataTable callers."""
    return _patch_uasset_serial_size(uasset_data, uexp_size)


def _sync_uasset_serial_size_file(uasset_path: str, uexp_path: str) -> bool:
    """Patch one on-disk .uasset SerialSize to match its sibling .uexp."""
    if not os.path.isfile(uasset_path) or not os.path.isfile(uexp_path):
        raise FileNotFoundError(f'Missing asset pair: {uasset_path} / {uexp_path}')
    with open(uasset_path, 'rb') as f:
        uasset_data = f.read()
    uexp_size = os.path.getsize(uexp_path)
    patched = _patch_uasset_serial_size(uasset_data, uexp_size)
    if patched != uasset_data:
        with open(uasset_path, 'wb') as f:
            f.write(patched)
        return True
    return False


def _validate_uasset_serial_size(uasset_path: str, uexp_path: str, label: str) -> None:
    """Raise when a .uasset export table disagrees with the .uexp size."""
    from parsers.uasset_clone import _read_fstring
    import struct as _s

    if not os.path.isfile(uasset_path) or not os.path.isfile(uexp_path):
        raise FileNotFoundError(f'Missing asset pair for {label}')

    uasset_data = open(uasset_path, 'rb').read()
    uexp_size = os.path.getsize(uexp_path)
    _folder_text, folder_bytes = _read_fstring(uasset_data, 32)
    folder_end = 32 + folder_bytes
    export_offset = _s.unpack_from('<i', uasset_data, folder_end + 32)[0]
    if export_offset <= 0 or export_offset + 44 > len(uasset_data):
        raise ValueError(f'{label}: invalid export table in uasset')
    serial_size = _s.unpack_from('<q', uasset_data, export_offset + 28)[0]
    expected_serial = uexp_size - 4
    if serial_size != expected_serial:
        raise ValueError(f'{label}: SerialSize {serial_size} != expected {expected_serial}')


def _template_engine_pair_names(templates_dir: str = TEMPLATES_ENGINE_DIR) -> set[str]:
    """Return template stems that have both .uasset and .uexp source files."""
    if not os.path.isdir(templates_dir):
        return set()
    uassets = {
        os.path.splitext(os.path.basename(path))[0]
        for path in glob.glob(os.path.join(templates_dir, '*.uasset'))
    }
    uexps = {
        os.path.splitext(os.path.basename(path))[0]
        for path in glob.glob(os.path.join(templates_dir, '*.uexp'))
    }
    return uassets & uexps


def _expected_template_pack_specs(specs: Optional[List[Any]] = None) -> List[Any]:
    """Return specs that correspond to complete template source pairs."""
    if specs is None:
        from template_engines import load_template_specs, sort_key
        specs = sorted(load_template_specs(TEMPLATES_ENGINE_DIR, ENGINE_DISPLAY_NAMES), key=sort_key)
    pair_names = _template_engine_pair_names(TEMPLATES_ENGINE_DIR)
    return [spec for spec in specs if spec.name in pair_names]


def _count_materialized_template_pairs(engine_dir: str, expected_asset_names: set[str]) -> int:
    return sum(
        1
        for name in expected_asset_names
        if os.path.isfile(os.path.join(engine_dir, name + '.uasset'))
        and os.path.isfile(os.path.join(engine_dir, name + '.uexp'))
    )


def _verify_template_pack_contents(pak: Dict[str, Any], expected_specs: List[Any]) -> Dict[str, Any]:
    """Inspect a template pak against the authoritative template source inventory."""
    from parsers.uexp_engines_dt import _find_type_a_rows, get_row_count

    expected_asset_names = {str(spec.asset_name) for spec in expected_specs}
    expected_titles = {str(spec.asset_name): _pack_shop_title_for_spec(spec) for spec in expected_specs}
    title_to_asset = {title: asset for asset, title in expected_titles.items()}

    entries = list(pak.get('entries') or [])
    pak_paths = {str(entry.get('path') or '') for entry in entries}
    engine_prefix = 'MotorTown/Content/Cars/Parts/Engine/'
    dt_uasset_path = 'MotorTown/Content/DataAsset/VehicleParts/Engines.uasset'
    dt_uexp_path = 'MotorTown/Content/DataAsset/VehicleParts/Engines.uexp'

    pak_uasset_assets = {
        Path(path).stem
        for path in pak_paths
        if path.startswith(engine_prefix) and path.endswith('.uasset')
    }
    pak_uexp_assets = {
        Path(path).stem
        for path in pak_paths
        if path.startswith(engine_prefix) and path.endswith('.uexp')
    }
    pak_engine_assets = pak_uasset_assets & pak_uexp_assets

    missing_pak_templates = sorted(expected_asset_names - pak_engine_assets)
    missing_pak_uassets = sorted(expected_asset_names - pak_uasset_assets)
    missing_pak_uexps = sorted(expected_asset_names - pak_uexp_assets)

    datatable_uasset_data = None
    datatable_uexp_data = None
    for entry in entries:
        path = str(entry.get('path') or '')
        if path == dt_uasset_path:
            datatable_uasset_data = entry.get('data')
        elif path == dt_uexp_path:
            datatable_uexp_data = entry.get('data')

    row_count = 0
    parsed_row_count = 0
    registered_assets: set[str] = set()
    preloaded_assets: set[str] = set()
    last_registered_template = ''
    if isinstance(datatable_uexp_data, (bytes, bytearray)):
        row_count = get_row_count(bytes(datatable_uexp_data))
        rows = _find_type_a_rows(bytes(datatable_uexp_data))
        parsed_row_count = len(rows)
        idx_to_name: Dict[int, str] = {}
        preloaded_import_refs: set[int] = set()
        if isinstance(datatable_uasset_data, (bytes, bytearray)):
            idx_to_name, _imports = _parse_name_lookup(bytes(datatable_uasset_data))
            try:
                from parsers.uasset_clone import _read_fstring
                _folder_text, folder_bytes = _read_fstring(bytes(datatable_uasset_data), 32)
                folder_end = 32 + folder_bytes
                export_offset = struct.unpack_from('<i', datatable_uasset_data, folder_end + 32)[0]
                preload_count = struct.unpack_from('<i', datatable_uasset_data, folder_end + 156)[0]
                preload_offset = struct.unpack_from('<i', datatable_uasset_data, folder_end + 160)[0]
                sbs = struct.unpack_from('<i', datatable_uasset_data, export_offset + 76)[0]
                cbs = struct.unpack_from('<i', datatable_uasset_data, export_offset + 80)[0]
                sbc = struct.unpack_from('<i', datatable_uasset_data, export_offset + 84)[0]
                for idx in range(sbs + cbs, min(preload_count, sbs + cbs + sbc)):
                    preloaded_import_refs.add(struct.unpack_from('<i', datatable_uasset_data, preload_offset + idx * 4)[0])
            except Exception:
                preloaded_import_refs = set()
        for row in rows:
            display = str(row.get('display') or '')
            asset = idx_to_name.get(int(row.get('fname_idx') or -1)) or title_to_asset.get(display)
            if asset in expected_asset_names:
                registered_assets.add(asset)
                last_registered_template = display
        if isinstance(datatable_uasset_data, (bytes, bytearray)):
            for asset in expected_asset_names:
                asset_ref = _find_engine_import_ref(bytes(datatable_uasset_data), asset)
                if asset_ref in preloaded_import_refs:
                    preloaded_assets.add(asset)

    missing_registered_templates = sorted(expected_asset_names - registered_assets)
    missing_preloaded_templates = sorted(expected_asset_names - preloaded_assets)
    missing_templates = sorted(
        set(missing_pak_templates)
        | set(missing_registered_templates)
        | set(missing_preloaded_templates)
    )
    errors: list[str] = []
    if missing_pak_templates:
        errors.append('Missing template engine pak pairs: ' + ', '.join(missing_pak_templates[:8]))
    if missing_registered_templates:
        errors.append('Missing template DataTable rows: ' + ', '.join(missing_registered_templates[:8]))
    if missing_preloaded_templates:
        errors.append('Missing template preload dependencies: ' + ', '.join(missing_preloaded_templates[:8]))
    if datatable_uasset_data is None:
        errors.append('Missing Engines.uasset DataTable entry')
    if datatable_uexp_data is None:
        errors.append('Missing Engines.uexp DataTable entry')

    return {
        'valid': not errors,
        'errors': errors,
        'expected_template_count': len(expected_asset_names),
        'pak_engine_count': len(pak_engine_assets),
        'pak_file_count': int(pak.get('file_count') or len(entries)),
        'registered_template_count': len(registered_assets),
        'preloaded_template_count': len(preloaded_assets),
        'datatable_row_count': row_count,
        'parsed_datatable_row_count': parsed_row_count,
        'missing_templates': missing_templates,
        'missing_pak_templates': missing_pak_templates,
        'missing_pak_uassets': missing_pak_uassets,
        'missing_pak_uexps': missing_pak_uexps,
        'missing_registered_templates': missing_registered_templates,
        'missing_preloaded_templates': missing_preloaded_templates,
        'last_registered_template': last_registered_template,
        'pak_engine_assets': sorted(pak_engine_assets),
    }


def inspect_template_pack(pak_path: str = '') -> Dict[str, Any]:
    """Inspect a generated template pak without mutating it."""
    if not pak_path or not str(pak_path).strip():
        return {'error': 'No pak path provided'}
    pak_path = str(pak_path).strip()
    if not os.path.isfile(pak_path):
        return {'error': f'Pak file not found: {pak_path}'}
    try:
        from template_engines import load_template_specs, sort_key
        from parsers.pak_reader import read_pak

        specs = sorted(load_template_specs(TEMPLATES_ENGINE_DIR, ENGINE_DISPLAY_NAMES), key=sort_key)
        expected_specs = _expected_template_pack_specs(specs)
        pak = read_pak(pak_path)
        result = _verify_template_pack_contents(pak, expected_specs)
        result['pak_path'] = pak_path
        return result
    except Exception as e:
        return {'error': f'Failed to inspect template pak: {e}'}


def pack_templates(output_path: str = '') -> Dict:
    """Pack all template engines using the same curated rules as the stable builder."""
    import tempfile
    from template_engines import load_template_specs, sort_key
    from parsers.vanilla_engine_builder import materialize_template_files

    if not output_path or not output_path.strip():
        return {'error': 'No output path provided'}

    output_path = _pak_output_path(output_path)

    if not os.path.isdir(TEMPLATES_ENGINE_DIR):
        return {'error': f'Templates directory not found: {TEMPLATES_ENGINE_DIR}'}
    if not os.path.isfile(VANILLA_DT_BASE + '.uasset') or not os.path.isfile(VANILLA_DT_BASE + '.uexp'):
        return {'error': 'Vanilla Engines DataTable not found'}

    audit = _audit_template_engines()
    audit_summary = _template_audit_summary(audit)
    if not audit['valid']:
        return {'error': _template_audit_preview(audit), 'template_audit': audit_summary}

    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix='mte_tpl_')
        temp_mt = os.path.join(temp_dir, 'MotorTown')
        tpl_engine_dst = os.path.join(temp_mt, 'Content', 'Cars', 'Parts', 'Engine')
        tpl_dt_dst = os.path.join(temp_mt, 'Content', 'DataAsset', 'VehicleParts')
        os.makedirs(tpl_engine_dst, exist_ok=True)
        os.makedirs(tpl_dt_dst, exist_ok=True)

        specs = load_template_specs(TEMPLATES_ENGINE_DIR, ENGINE_DISPLAY_NAMES)
        specs = sorted(specs, key=sort_key)
        expected_specs = _expected_template_pack_specs(specs)
        if not specs:
            return {'error': 'No template engines found to pack'}
        if len(expected_specs) != len(specs):
            missing_pair_names = sorted({spec.name for spec in specs} - _template_engine_pair_names(TEMPLATES_ENGINE_DIR))
            return {
                'error': 'Template source inventory is incomplete: ' + ', '.join(missing_pair_names[:8]),
                'expected_template_count': len(expected_specs),
                'template_count': len(specs),
                'missing_templates': missing_pair_names,
                'template_audit': audit_summary,
            }

        copied = 0
        donor_counts: Dict[str, int] = {}
        vanilla_engine_dir = os.path.join(VANILLA_BASE, 'Engine')
        for spec in expected_specs:
            resolved_sound_dir = resolve_sound_dir_override(
                spec.name,
                default_sound_dir=(spec.sound_dir or None),
            )
            materialize_template_files(
                spec.name,
                spec.asset_name,
                spec.variant,
                TEMPLATES_ENGINE_DIR,
                vanilla_engine_dir,
                tpl_engine_dst,
                donor_name=spec.donor_name,
                sound_dir=resolved_sound_dir,
            )
            donor_counts[spec.donor_name] = donor_counts.get(spec.donor_name, 0) + 1
            copied += 1

        shutil.copy2(VANILLA_DT_BASE + '.uasset', os.path.join(tpl_dt_dst, 'Engines.uasset'))
        shutil.copy2(VANILLA_DT_BASE + '.uexp', os.path.join(tpl_dt_dst, 'Engines.uexp'))

        ua = open(os.path.join(tpl_dt_dst, 'Engines.uasset'), 'rb').read()
        ue = open(os.path.join(tpl_dt_dst, 'Engines.uexp'), 'rb').read()
        price_model = build_torque_price_model(specs)

        for spec in expected_specs:
            price = recommend_price_from_torque(price_model, spec.torque_nm)
            weight = ENGINE_WEIGHTS.get(spec.name) or _fallback_weight(spec.variant, spec.hp)
            ua, ue, _ = _register_engine_datatable_entry(
                ua,
                ue,
                spec.asset_name,
                _pack_shop_title_for_spec(spec),
                price,
                weight,
                spec.variant,
                update_existing=False,
                description=spec.shop_subtitle,
                row_tail_variant='ice_standard',
            )

        ua = _patch_datatable_serial_size(ua, len(ue))
        with open(os.path.join(tpl_dt_dst, 'Engines.uasset'), 'wb') as f:
            f.write(ua)
        with open(os.path.join(tpl_dt_dst, 'Engines.uexp'), 'wb') as f:
            f.write(ue)

        from engine_validation import validate_engine_generation_tree
        validation = validate_engine_generation_tree(temp_mt)
        if not validation['valid']:
            preview = '; '.join(validation['errors'][:6])
            extra = '' if len(validation['errors']) <= 6 else f' (+{len(validation["errors"]) - 6} more)'
            return {'error': f'Pack validation failed: {preview}{extra}', 'validation': validation}
        from parsers.pak_writer import write_pak
        result = write_pak(temp_mt, output_path)
        from parsers.pak_reader import read_pak
        materialized_count = _count_materialized_template_pairs(
            tpl_engine_dst,
            {str(spec.asset_name) for spec in expected_specs},
        )
        pack_verification = _verify_template_pack_contents(read_pak(output_path), expected_specs)
        pack_verification['materialized_template_count'] = materialized_count
        if not pack_verification['valid']:
            preview = '; '.join(pack_verification['errors'][:3])
            extra = '' if len(pack_verification['missing_templates']) <= 8 else f' (+{len(pack_verification["missing_templates"]) - 8} more)'
            return {
                'error': (
                    f'Template pack verification failed: {preview}{extra}. '
                    f'Last registered template: {pack_verification.get("last_registered_template") or "none"}'
                ),
                **pack_verification,
                'template_count': copied,
                'donor_counts': donor_counts,
                'template_audit': audit_summary,
            }
        logging.info(
            'template pack verified: expected=%s materialized=%s pak_engines=%s registered=%s preloaded=%s files=%s last=%s',
            pack_verification['expected_template_count'],
            materialized_count,
            pack_verification['pak_engine_count'],
            pack_verification['registered_template_count'],
            pack_verification['preloaded_template_count'],
            pack_verification['pak_file_count'],
            pack_verification['last_registered_template'],
        )
        msg = (f'Packed {result["file_count"]} files '
               f'({copied} engines, {pack_verification["registered_template_count"]} registered templates, '
               f'{pack_verification["preloaded_template_count"]} preloaded templates) '
               f'to {output_path}')
        return {
            'success': True,
            'message': msg,
            'pak_size': result['pak_size'],
            'file_count': result['file_count'],
            'pak_file_count': pack_verification['pak_file_count'],
            'template_count': copied,
            'expected_template_count': pack_verification['expected_template_count'],
            'materialized_template_count': materialized_count,
            'registered_template_count': pack_verification['registered_template_count'],
            'preloaded_template_count': pack_verification['preloaded_template_count'],
            'pak_engine_count': pack_verification['pak_engine_count'],
            'missing_templates': pack_verification['missing_templates'],
            'last_registered_template': pack_verification['last_registered_template'],
            'donor_counts': donor_counts,
            'template_audit': audit_summary,
            'pack_verification': pack_verification,
            'shop_tail_policy': 'universal_ice_standard',
        }
    except Exception as e:
        return {'error': f'Pack failed: {str(e)}', 'template_audit': audit_summary}
    finally:
        if temp_dir and os.path.isdir(temp_dir):
            shutil.rmtree(temp_dir)


def restore_datatable(pak_path: str = '') -> Dict:
    """Extract the Engines DataTable from an existing pak and restore it.

    Replaces the mod's Engines.uasset/uexp with the pristine versions
    from the given pak file, undoing any accumulated corruption.
    """
    import struct as _struct
    if not pak_path:
        pak_path = os.path.join(DEFAULT_PAKS_DIR, DEFAULT_CUSTOM_PAK_FILENAME)

    if not os.path.isfile(pak_path):
        return {'error': f'Pak file not found: {pak_path}'}

    try:
        from parsers.pak_reader import read_pak
        pak = read_pak(pak_path)
    except Exception as e:
        return {'error': f'Failed to read pak: {e}'}

    dt_dir = os.path.join(MOD_ROOT, 'MotorTown', 'Content', 'DataAsset', 'VehicleParts')
    os.makedirs(dt_dir, exist_ok=True)

    restored = []
    for e in pak['entries']:
        if 'DataAsset/VehicleParts/Engines.' in e['path']:
            fname = os.path.basename(e['path'])
            out_path = os.path.join(dt_dir, fname)
            with open(out_path, 'wb') as f:
                f.write(e['data'])
            restored.append(f'{fname} ({len(e["data"])} bytes)')

    if not restored:
        return {'error': 'No Engines DataTable found in pak'}

    ue_path = os.path.join(dt_dir, 'Engines.uexp')
    ue_data = open(ue_path, 'rb').read()
    row_count = _struct.unpack_from('<i', ue_data, 0x0a)[0]

    return {
        'success': True,
        'message': f'Restored DataTable from pak ({row_count} rows)',
        'restored': restored,
        'row_count': row_count,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CRITICAL: MOTOR TOWN BASE-GAME ENGINE NAMES
# These engine files ship with the base game or are reserved built-in template keys.
# They must NEVER appear in the "Create New Engine" template picker — templates
# should contain only fresh, original engines that don't exist in vanilla MT.
# If you scrape new engine names from the web, check them against this set first
# and refuse to add any match. This list must stay in sync with the template
# source definitions in scripts/create_templates.py.
# ─────────────────────────────────────────────────────────────────────────────
GAME_ENGINE_NAMES: frozenset = frozenset({
    # ICE Standard (base game / reserved)
    '13b', '26b', '73amg', '81bb', '81bbt', 'F120A', 'F120Att',
    'GM572', 'GM632', 'HONDAV10F1', 'L86', 'LT7',
    'P60B40', 'S54B32', 'S63B44B', 'S85V10505HP', 'SR20DET',
    'V10ACR', 'V10ACRt', 'V12_789HP', 'laferrariV12', 'lamboV12', 'lexusV10',
    # ICE Compact (base game)
    '20hyundai', '20tfsi', '2JZ320HP', '50coyote',
    'C63AMG671HP', 'Hemi392_525HP', 'HemiHellcat_707HP',
    'KoenigseggHV8tt2300HP', 'KoenigseggV8tt1280HP',
    'RB26DET276HP', 'RB26DET350HP', 'RB26DET440HP',
    'S58', 'S58comp', 'bugattiW16',
    # Diesel HD (base game)
    '30tdi', '59cummins', '65detroit', '66duramax', '73powerstroke',
    'CATC12490HP',
    'CumminsX15x565', 'CumminsX15x605', 'CumminsX15x675',
    'DV27K1500HP', 'DetroidDD16_600HP',
    'PACCARxMXx13x455', 'PACCARxMXx13x510',
    'R10', 'Scania770HP',
    'ScaniaDC16_530HP', 'ScaniaDC16_590HP', 'ScaniaDC16_660HP', 'ScaniaDC16_770HP',
    'VW19TDI150HP',
    'VolvoD13', 'VolvoD17_600HP', 'VolvoD17_700HP', 'VolvoD17_780HP', 'VolvoD17_780HPs',
    'WeichaiWP17H_800HP', 'WeichaiWP17H_800HPs', 'benzI6',
    # Motorcycle (base game)
    '999r_150HP',
    'Bike_i4_250HP',
    'bandit1250145HP',
    'cbr600rr120HP',
    'gpproto240HP',
    'harley_120HP',
    'hayabusa_200HP',
    'panigale1199170HP',
    'r750140HP',
    'sportster120065HP',
    'sv65070HP',
    'zzr1400200HP',
    # EV (base game — all EV* prefix names)
    'EVAlpineA290', 'EVAsparkOwl', 'EVAudiRSetronGTPerformance',
    'EVChevroletBoltEV', 'EVChevroletSilveradoEVWT',
    'EVDrakoDragon', 'EVElationFreedom', 'EVFiskerOceanUltra',
    'EVGACAionHyperSSR', 'EVGMCHummerEV', 'EVHyundaiIoniq9',
    'EVLotusEvija', 'EVLucidAirSapphire',
    'EVLucidGravityDreamEdition', 'EVMGMG4EV', 'EVMHero917',
    'EVMercedesAMGGTXXConcept', 'EVMercedesEQS450Plus',
    'EVNIOEP9', 'EVNIOET5', 'EVNetGainHyper9',
    'EVPininfarinaBattista', 'EVPolestar2DualMotor', 'EVPolestar3LongRangeSingleMotor',
    'EVPorscheTaycanTurboS', 'EVRimacNeveraR',
    'EVRivianR1TQuadMotorGen1', 'EVTataTiagoEV',
    'EVTeslaModelSPlaid', 'EVTeslaSemi',
    'EVVinFastVFe34', 'EVVolvoEX30', 'EVWulingHongguangMiniEV',
    'EVYangwangU9TrackEdition',
})

ENGINE_DISPLAY_NAMES = {
    # ICE Standard
    '13b':           'Mazda 13B-REW Twin-Turbo Rotary (RX-7 FD)',
    '26b':           'Mazda 26B Quad-Rotor (787B Le Mans)',
    '73amg':         'Mercedes-AMG M297 7.3L V12 (Pagani Zonda F)',
    '81bb':          'Chevrolet 8.1L Vortec V8 (Silverado HD)',
    '81bbt':         'Chevrolet 8.1L Vortec V8 Turbocharged',
    'F120A':         'Ferrari F140EF 6.2L V12 (F12berlinetta)',
    'F120Att':       'Ferrari F140EF 6.2L V12 Twin-Turbo (Custom)',
    'GM572':         'Chevrolet ZZ572/620 9.4L V8 Crate Engine',
    'GM632':         'Chevrolet ZZ632/1000 10.3L V8 Crate Engine',
    'HONDAV10F1':    'Honda RA001E 3.0L V10 F1 (BAR 2001)',
    'L86':           'GM L86 EcoTec3 6.2L V8 (Silverado/Tahoe)',
    'LT7':           'GM LT7 5.5L Flat-Plane V8 (C8 Corvette ZR1)',
    'P60B40':        'BMW S65-Derived 4.4L V8 (E92 M3 GTS)',
    'S54B32':        'BMW S54B32 3.2L I6 (E46 M3)',
    'S63B44B':       'BMW S63B44T4 4.4L Twin-Turbo V8 (M5 CS)',
    'S85V10505HP':   'BMW S85B50 5.0L V10 (E60/E61 M5)',
    'SR20DET':       'Nissan SR20DET 2.0L Turbo I4 (Silvia S15)',
    'V10ACR':        'Dodge Viper 8.4L V10 (SRT ACR 2013-2017)',
    'V10ACRt':       'Dodge Viper 8.4L V10 Turbocharged (Custom)',
    'V12_789HP':     'Ferrari F140GA 6.5L V12 (812 Superfast)',
    'laferrariV12':  'Ferrari F140FE 6.3L V12 (LaFerrari)',
    'lamboV12':      'Lamborghini L539 6.5L V12 (Aventador SVJ)',
    'lexusV10':      'Lexus/Yamaha 1LR-GUE 4.8L V10 (LFA)',
    # ICE Compact
    '20hyundai':             'Hyundai Theta II 2.0L Turbo I4 (Genesis G70)',
    '20tfsi':                'Audi EA888 Gen 3B 2.0L TFSI (TTS)',
    '2JZ320HP':              'Toyota 2JZ-GTE 3.0L Twin-Turbo I6 (Supra A80 JDM)',
    '50coyote':              'Ford Coyote Gen 4 5.0L V8 (Mustang GT 2024)',
    'C63AMG671HP':           'Mercedes-AMG M178 4.0L Twin-Turbo V8 (AMG GT Black Series)',
    'Hemi392_525HP':         'Dodge 6.4L HEMI 392 V8 (Challenger SRT 392)',
    'HemiHellcat_707HP':     'Dodge 6.2L Supercharged V8 (Challenger SRT Hellcat)',
    'KoenigseggHV8tt2300HP': 'Koenigsegg 5.0L Twin-Turbo V8 (Jesko - E85)',
    'KoenigseggV8tt1280HP':  'Koenigsegg 5.0L Twin-Turbo V8 (Agera RS)',
    'RB26DET276HP':          'Nissan RB26DETT 2.6L Twin-Turbo I6 (GT-R R34 Stock)',
    'RB26DET350HP':          'Nissan RB26DETT 2.6L Twin-Turbo I6 (GT-R Stage 1)',
    'RB26DET440HP':          'Nissan RB26DETT 2.6L Twin-Turbo I6 (GT-R Stage 2)',
    'S58':                   'BMW S58B30 3.0L Twin-Turbo I6 (M3/M4 Competition)',
    'S58comp':               'BMW S58B30 3.0L Twin-Turbo I6 (M3/M4 Competition xDrive)',
    'bugattiW16':            'Bugatti W16 8.0L Quad-Turbo (Chiron Super Sport)',
    # ICE Standard — new templates (round 1)
    'dodge_viper_gen1':   'Dodge Viper 8.0L V10 GTS (1996-2002)',
    'am_one77_v12':       'Aston Martin 7.3L V12 (One-77)',
    'alfa_8c_v8':         'Alfa Romeo 4.7L V8 (8C Competizione)',
    'ssc_tuatara_e85':    'SSC Tuatara 5.9L TT V8 (E85)',
    'hennessey_venom_gt': 'Hennessey Venom GT 7.0L TT V8',
    'am_db11_amr_v12':    'Aston Martin DB11 AMR 5.2L TT V12',
    'amg_m178_gtr_pro':   'Mercedes-AMG M178 4.0L TT V8 (AMG GT R Pro)',
    'ferrari_f8_v8':      'Ferrari F154CG 3.9L TT V8 (F8 Tributo)',
    'mclaren_m840t':      'McLaren M840T 4.0L TT V8 (720S)',
    'porsche_9a2_gt2rs':  'Porsche 9A2 Evo 3.8L TT Flat-6 (991 GT2 RS)',
    # ICE Standard — new templates (round 2)
    'ls6_454_chevelle':         'Chevrolet 454 LS6 7.4L V8 (1970 Chevelle SS)',
    'ford_427_fe_gt40':         'Ford 427 FE 7.0L V8 (Ford GT40 Mk II Le Mans)',
    'chrysler_426_hemi':        'Chrysler 426 HEMI 7.0L V8 (1968 Dodge Charger R/T)',
    'pontiac_ramairiv_400':     'Pontiac 400 Ram Air IV 6.6L V8 (1969 GTO The Judge)',
    'ls7_c6_corvette_z06':      'Chevrolet LS7 7.0L V8 NA (C6 Corvette Z06)',
    'lt6_c8_corvette_z06':      'Chevrolet LT6 5.5L Flat-Plane V8 NA (C8 Corvette Z06)',
    'ferrari_enzo_f140b':       'Ferrari F140B 6.0L V12 NA (Ferrari Enzo)',
    'ferrari_599gto_v12':       'Ferrari F140CE 6.0L V12 NA (Ferrari 599 GTO)',
    'lambo_murcielago_sv':      'Lamborghini 6.5L V12 NA (Murcielago LP670-4 SuperVeloce)',
    'maserati_mc12_v12':        'Ferrari/Maserati F140 6.0L V12 NA (Maserati MC12)',
    'am_db9_v12':               'Aston Martin 5.9L V12 NA (DB9 Sportpack)',
    'gma_t50_cosworth_v12':     'Cosworth GMA 4.0L V12 NA (Gordon Murray T.50)',
    'pagani_zonda_r_v12':       'Mercedes-AMG M120 6.0L V12 NA (Pagani Zonda R)',
    'jaguar_xj220_v6tt':        'Jaguar/TWR JV6 3.5L Twin-Turbo V6 (Jaguar XJ220)',
    'bentley_contgt_w12':       'Bentley 6.0L Twin-Turbo W12 (Continental GT Speed)',
    'ferrari_488pista_f154':    'Ferrari F154 3.9L Twin-Turbo V8 (488 Pista)',
    'amg_gtbs_m178ls2':         'Mercedes-AMG M178 LS2 4.0L Twin-Turbo V8 (AMG GT Black Series)',
    'porsche_carrera_gt_v10':   'Porsche 5.7L V10 NA (Carrera GT)',
    'ford_gt05_54sc':           'Ford 5.4L Supercharged DOHC V8 (2005 Ford GT)',
    'shelby_gt500_07_54sc':     'Ford 5.4L Supercharged DOHC V8 (2007 Shelby GT500)',
    'am_valkyrie_cosworth_v12': 'Cosworth 6.5L V12 NA (Aston Martin Valkyrie)',
    'ferrari_360_f131':         'Ferrari F131 3.6L V8 NA (Ferrari 360 Modena)',
    # Diesel HD — new templates
    'cat_c15':              'Caterpillar C15 15.2L I6 (On-Highway)',
    'cat_c18':              'Caterpillar C18 18.1L I6 (Industrial/Marine)',
    'navistar_maxxforce13': 'International MaxxForce 13 12.4L I6 (ProStar)',
    'cummins_isx15':        'Cummins ISX15 15.0L I6 (Signature Series)',
    'man_d3876':            'MAN D3876 12.4L I6 (TGX Euro 6)',
    'mercedes_om473':       'Mercedes-Benz OM473 15.6L I6 (Actros SLT)',
    'john_deere_9l':        'John Deere PowerTech 9.0L I6 (9R Tractor)',
    'deutz_tcd16_v8':       'Deutz TCD 16.0L V8 (Liebherr Construction)',
    'detroit_series60':     'Detroit Diesel Series 60 12.7L I6',
    'mtu_16v2000':          'MTU 16V 2000 Series 32.0L V16 (Marine/Rail)',
    'cat_c32':              'Caterpillar C32 32.0L V12 (Industrial/Mining)',
    'liebherr_d9508':       'Liebherr D9508 15.0L I8 (Heavy Construction)',
    'liebherr_d9512':       'Liebherr D9512 30.0L V12 (Mining Haul Truck)',
    'perkins_2806':         'Perkins 2806J-E18TA 18.1L I6 (Industrial)',
    'iveco_cursor13':       'Iveco Cursor 13 12.9L I6 (Stralis/S-Way)',
    # Diesel HD — round 2
    'paccar_mx11_445':      'PACCAR MX-11 10.8L I6 (On-Highway Regional)',
    'daf_mx13_530':         'DAF/PACCAR MX-13 12.9L I6 530 HP (Long-Haul)',
    'scania_dc13_500':      'Scania DC13 Super 13.0L I6 493 HP (On-Highway)',
    'scania_dc13_450':      'Scania DC13 13.0L I6 444 HP (On-Highway)',
    'man_d2676_500':        'MAN D2676 12.4L I6 493 HP (TGX Long-Haul)',
    'volvo_d16g700':        'Volvo D16G 16.1L I6 690 HP (Heavy-Haul Truck)',
    'volvo_d13_500':        'Volvo D13 12.8L I6 493 HP (On-Highway Long-Haul)',
    'cummins_x12_500':      'Cummins X12 11.4L I6 500 HP (On-Highway Coach)',
    'cummins_qsk19_800':    'Cummins QSK19 19.0L I6 800 HP (Mining/Industrial)',
    'cummins_qsk23_950':    'Cummins QSK23 23.0L I6 950 HP (Mining/Oil & Gas)',
    'cummins_qsk38_1600':   'Cummins QSK38 37.7L V12 1600 HP (Heavy Mining)',
    'cummins_qsk60_2300':   'Cummins QSK60 60.2L V16 2300 HP (Ultra-Class Mining)',
    'cummins_qsk78_3500':   'Cummins QSK78 77.6L V18 3500 HP (Rail/Mining)',
    'cat_3516_2000':        'Caterpillar 3516 69.0L V16 2000 HP (Industrial/Mining)',
    'cat_3608_3300':        'Caterpillar 3608 Inline Diesel 3300 HP (Oil & Gas/Marine)',
    'cat_3616_6600':        'Caterpillar 3616 Inline Diesel 6600 HP (Marine/Mining)',
    'mtu_16v4000_2935':     'MTU 16V4000 76.3L V16 2935 HP (Industrial/Marine)',
    'mtu_16v2000_2600':     'MTU 16V2000 32.0L V16 2600 HP (Fast Vessel)',
    'wartsila_32_12500':    'Wartsila 32 18-Cyl 4-Stroke 12475 HP (Marine/Offshore)',
    'wartsila_46f_20000':   'Wartsila 46F 16V Medium-Speed 20000 HP (Large Vessel)',
    'bergen_b3240_v16':     'Bergen B32:40 V16 Diesel 8000 HP (Marine/Industrial)',
    # Motorcycle — new templates
    'bmw_s1000rr':          'BMW S1000RR 999cc Inline-4 (M Sport)',
    'honda_cbr1000rr_r':    'Honda CBR1000RR-R Fireblade SP 1000cc I4',
    'kawasaki_h2':          'Kawasaki Ninja H2 998cc Supercharged I4',
    'kawasaki_h2r':         'Kawasaki Ninja H2R 998cc Supercharged I4 (Track)',
    'yamaha_r1m':           'Yamaha YZF-R1M 998cc Crossplane I4',
    'aprilia_rsv4':         'Aprilia RSV4 Factory 1099cc V4',
    'mv_agusta_f4rr':       'MV Agusta F4 RR 998cc Inline-4',
    'ducati_panigale_v4r':  'Ducati Panigale V4 R 998cc Desmosedici V4',
    'ktm_1290_super_duke':  'KTM 1290 Super Duke R 1301cc V-Twin',
    'triumph_rocket3':      'Triumph Rocket 3 2458cc Triple',
    'norton_v4cr':          'Norton V4 CR 1200cc V4',
    'indian_ftr1200':       'Indian FTR 1200 S 1203cc V-Twin',
    # Motorcycle — round 2
    'kawasaki_zx10r':               'Kawasaki Ninja ZX-10R 998cc I4 (Supersport)',
    'kawasaki_zx6r_636':            'Kawasaki Ninja ZX-6R 636cc I4 (Supersport)',
    'kawasaki_z900':                'Kawasaki Z900 948cc I4 (Supernaked)',
    'ducati_panigale_v2':           'Ducati Panigale V2 955cc V-Twin (Supersport)',
    'yamaha_r7':                    'Yamaha YZF-R7 689cc CP2 (Middleweight Supersport)',
    'yamaha_mt10':                  'Yamaha MT-10 998cc CP4 (Hypernaked)',
    'yamaha_tracer9':               'Yamaha Tracer 9 GT+ 890cc CP3 (Sport Tourer)',
    'honda_cbr600rr_2024':          'Honda CBR600RR 599cc I4 (2024 Supersport)',
    'triumph_daytona660':           'Triumph Daytona 660 659cc I3 (Middleweight Supersport)',
    'triumph_speed_triple_1200':    'Triumph Speed Triple 1200 RR 1160cc I3 (Hypernaked)',
    'bmw_k1600':                    'BMW K1600 GT 1649cc I6 (Sport Tourer)',
    'bmw_r18':                      'BMW R18 1802cc Boxer (Heritage Cruiser)',
    'bmw_f900r':                    'BMW F900R 895cc Parallel-Twin (Roadster)',
    'suzuki_gsx_s1000':             'Suzuki GSX-S1000 999cc I4 (Supernaked)',
    'suzuki_vstrom1050':            'Suzuki V-Strom 1050 1037cc V-Twin (Adventure)',
    'ktm_890_duke':                 'KTM 890 Duke R 889cc Parallel-Twin (Supernaked)',
    'ktm_rc390':                    'KTM RC 390 373cc Single (Entry Supersport)',
    'harley_pan_america':           'Harley-Davidson Pan America 1250 Revolution Max 1252cc V-Twin',
    'moto_guzzi_v100':              'Moto Guzzi V100 Mandello 1042cc V-Twin (Sport Tourer)',
    'indian_scout_1250':            'Indian Scout 1250 SpeedPlus 1250cc V-Twin (Cruiser)',
    'royal_enfield_interceptor650': 'Royal Enfield Interceptor 650 648cc Parallel-Twin (Classic)',
    'royal_enfield_himalayan450':   'Royal Enfield Himalayan 450 452cc Single (Adventure)',
    # ICE Compact — new templates
    'subaru_ej257':       'Subaru EJ257 2.5L Flat-4 Turbo (WRX STI)',
    'honda_k20c1':        'Honda K20C1 2.0L Turbo I4 (Civic Type R FK8)',
    'mitsubishi_4g63t':   'Mitsubishi 4G63T 2.0L Turbo I4 (Evo IX MR)',
    'ford_23_ecoboost':   'Ford 2.3L EcoBoost I4 (Focus RS)',
    'porsche_992_cs':     'Porsche MA1.01 3.0L TT Flat-6 (992 Carrera S)',
    'toyota_gr_yaris':    'Toyota G16E-GTS 1.6L Turbo I3 (GR Yaris)',
    'bmw_n54b30':         'BMW N54B30 3.0L TT I6 (135i / 335i)',
    'nissan_vr38dett':    'Nissan VR38DETT 3.8L TT V6 (GT-R R35)',
    'porsche_991_gt3':    'Porsche MA1.76 3.8L NA Flat-6 (991.1 GT3)',
    # ICE Compact — new templates (round 2)
    'honda_f20c_s2000ap1':       'Honda F20C 2.0L I4 NA VTEC (S2000 AP1)',
    'honda_f22c_s2000ap2':       'Honda F22C 2.2L I4 NA VTEC (S2000 AP2)',
    'honda_k20a_dc5_itr':        'Honda K20A 2.0L I4 NA i-VTEC (Integra Type R DC5)',
    'honda_k20a2_ep3_ctr':       'Honda K20A2 2.0L I4 NA i-VTEC (Civic Type R EP3)',
    'honda_c30a_nsx':            'Honda C30A 3.0L V6 NA VTEC (Acura NSX)',
    'honda_c32b_nsxr':           'Honda C32B 3.2L V6 NA VTEC (Honda NSX-R)',
    'toyota_3sgte_g3_mr2':       'Toyota 3S-GTE Gen3 2.0L Turbo I4 (MR2 SW20 JDM)',
    'lotus_exige_s_2grfze':      'Toyota 2GR-FZE 3.5L Supercharged V6 (Lotus Exige S)',
    'bmw_s65_e92_m3':            'BMW S65 4.0L V8 NA (E92 M3)',
    'bmw_s55_f80_m3m4':          'BMW S55 3.0L Twin-Turbo I6 (F80 M3 / F82 M4)',
    'bmw_s14_e30_m3':            'BMW S14 2.3L I4 NA (E30 M3)',
    'audi_ea855_rs3_ttrs':       'Audi EA855 2.5L Turbo I5 (RS3 Sportback / TT RS)',
    'renault_f4rt_megane_rs250': 'Renault F4Rt 2.0L Turbo I4 (Megane RS 250)',
    'peugeot_ep6fdt_308gti270':  'Peugeot EP6FDT 1.6L Turbo I4 (308 GTI 270)',
    'mazda_l3vdt_mps3':          'Mazda MZR L3-VDT 2.3L Turbo I4 (Mazdaspeed3)',
    'vw_ea888_golf_r_mk75':      'VW EA888 Gen3 2.0L TSI Turbo I4 (Golf R Mk7.5)',
    'ford_23eb_focus_rs_mk3':    'Ford EcoBoost 2.3L Turbo I4 (Focus RS Mk3)',
    'ferrari_california_f136ib': 'Ferrari F136IB 4.3L V8 NA (Ferrari California)',
    'porsche_718gt4rs_ma120':    'Porsche MA1.20 4.0L Flat-6 NA (718 Cayman GT4 RS)',
    'alfa_4c_1750tbi':           'Alfa Romeo 1750 TBi 1.75L Turbo I4 (4C)',
    # Diesel HD
    '30tdi':              'Audi 3.0 TDI V6 (SQ5/SQ7/Q8)',
    '59cummins':          'Cummins 5.9L ISB 24-Valve (Ram 2500/3500)',
    '65detroit':          'Detroit Diesel 6.5L V8 Turbo (HMMWV)',
    '66duramax':          'GM 6.6L Duramax L5P V8 (Silverado HD)',
    '73powerstroke':      'Ford 7.3L Power Stroke V8 (Super Duty)',
    'CATC12490HP':        'Caterpillar C12 12.0L I6 (On-Highway)',
    'CumminsX15x565':     'Cummins X15 15.0L I6 (565 HP)',
    'CumminsX15x605':     'Cummins X15 15.0L I6 (605 HP)',
    'CumminsX15x675':     'Cummins X15 15.0L I6 Efficiency (675 HP)',
    'DV27K1500HP':        'MAN D2868 V8 27.0L (Race Spec)',
    'DetroidDD16_600HP':  'Detroit DD16 15.6L I6 (600 HP)',
    'PACCARxMXx13x455':   'PACCAR MX-13 12.9L I6 (455 HP)',
    'PACCARxMXx13x510':   'PACCAR MX-13 12.9L I6 (510 HP)',
    'R10':                'Audi R10 TDI 5.5L V12 (Le Mans 2006-08)',
    'Scania770HP':        'Scania DC16 16.4L V8 (770 HP)',
    'ScaniaDC16_530HP':   'Scania DC16 16.4L V8 (530 HP)',
    'ScaniaDC16_590HP':   'Scania DC16 16.4L V8 (590 HP)',
    'ScaniaDC16_660HP':   'Scania DC16 16.4L V8 (660 HP)',
    'ScaniaDC16_770HP':   'Scania DC16 16.4L V8 (770 HP)',
    'VW19TDI150HP':       'Volkswagen 1.9L TDI I4 (Golf/Jetta/Passat)',
    'VolvoD13':           'Volvo D13TC 12.8L I6 (FH Series)',
    'VolvoD17_600HP':     'Volvo D17 16.1L I6 (600 HP)',
    'VolvoD17_700HP':     'Volvo D17 16.1L I6 (700 HP)',
    'VolvoD17_780HP':     'Volvo D17 16.1L I6 (780 HP)',
    'VolvoD17_780HPs':    'Volvo D17 16.1L I6 Stage Tune (780 HP)',
    'WeichaiWP17H_800HP': 'Weichai WP17H 17.0L I6 (800 HP)',
    'WeichaiWP17H_800HPs':'Weichai WP17H 17.0L I6 Stage Tune (800 HP)',
    'benzI6':             'Mercedes-Benz OM471 12.8L I6 (Actros)',
    # Bike
    '999r_150HP':           'Ducati 999R 998cc L-Twin Testastretta (2003-06)',
    'Bike_i4_250HP':        'Sport Inline-4 Superbike (250 HP)',
    'bandit1250145HP':      'Suzuki Bandit GSF1250 1255cc I4 (Tuned)',
    'gpproto240HP':         'MotoGP Prototype 1000cc I4 (RC213V-S-class)',
    'harley_120HP':         'Harley-Davidson Milwaukee-Eight 117 (Tuned)',
    'hayabusa_200HP':       'Suzuki Hayabusa GSX1300R 1340cc I4 (Gen 2)',
    'panigale1199170HP':    'Ducati 1199 Panigale 1198cc L-Twin (2012-14)',
    'r750140HP':            'Suzuki GSX-R750 750cc I4 (2011+)',
    'sportster120065HP':    'Harley-Davidson Sportster XL1200 (Stock)',
    'sv65070HP':            'Suzuki SV650 645cc V-Twin (Stock)',
    'zzr1400200HP':         'Kawasaki Ninja ZZR1400 ZX-14R 1441cc I4 (2012+)',
    # EV - derive from name (already descriptive)
    'EVAlpineA290': 'Alpine A290',
    'EVAsparkOwl': 'Aspark Owl',
    'EVAudiRSetronGTPerformance': 'Audi RS e-tron GT Performance',
    'EVChevroletBoltEV': 'Chevrolet Bolt EV',
    'EVChevroletSilveradoEVWT': 'Chevrolet Silverado EV WT',
    'EVDrakoDragon': 'Drako Dragon',
    'EVElationFreedom': 'Elation Freedom',
    'EVFiskerOceanUltra': 'Fisker Ocean Ultra',
    'EVGACAionHyperSSR': 'GAC Aion Hyper SSR',
    'EVGMCHummerEV': 'GMC Hummer EV',
    'EVHyundaiIoniq9': 'Hyundai Ioniq 9',
    'EVLotusEvija': 'Lotus Evija',
    'EVLucidAirSapphire': 'Lucid Air Sapphire',
    'EVLucidGravityDreamEdition': 'Lucid Gravity Dream Edition',
    'EVMGMG4EV': 'MG MG4 EV',
    'EVMHero917': 'McMurtry Speirling / Hero 917',
    'EVMercedesAMGGTXXConcept': 'Mercedes-AMG GT XX Concept',
    'EVMercedesEQS450Plus': 'Mercedes EQS 450+',
    'EVNIOEP9': 'NIO EP9',
    'EVNIOET5': 'NIO ET5',
    'EVNetGainHyper9': 'NetGain HyPer 9 Motor',
    'EVPininfarinaBattista': 'Pininfarina Battista',
    'EVPolestar2DualMotor': 'Polestar 2 Dual Motor',
    'EVPolestar3LongRangeSingleMotor': 'Polestar 3 Long Range',
    'EVPorscheTaycanTurboS': 'Porsche Taycan Turbo S',
    'EVRimacNeveraR': 'Rimac Nevera R',
    'EVRivianR1TQuadMotorGen1': 'Rivian R1T Quad Motor',
    'EVTataTiagoEV': 'Tata Tiago EV',
    'EVTeslaModelSPlaid': 'Tesla Model S Plaid',
    'EVTeslaSemi': 'Tesla Semi',
    'EVVinFastVFe34': 'VinFast VF e34',
    'EVVolvoEX30': 'Volvo EX30',
    'EVWulingHongguangMiniEV': 'Wuling Hongguang Mini EV',
    'EVYangwangU9TrackEdition': 'Yangwang U9 Track Edition',
}


# ── Engine weights (kg, engine-only dry weight — published figures or best estimate) ─
ENGINE_WEIGHTS: dict = {
    # ICE Standard — stock
    # 13B-REW: 105 kg (Mazda published ~232 lbs); 26B quad-rotor race: ~94 kg
    # M297 V12: ~285 kg; Vortec 8100: ~285 kg (629 lbs cast iron)
    # F140EF V12: ~215 kg; ZZ572: ~294 kg (648 lbs); ZZ632: ~324 kg (714 lbs)
    # RA001E F1: ~90 kg; L86 EcoTec3: ~196 kg; LT7 flat-plane: ~152 kg (335 lbs GM published)
    # S65 M3 GTS: ~200 kg; S54B32: ~184 kg (405 lbs); S63B44T4: ~218 kg (481 lbs)
    # S85 V10: ~232 kg (511 lbs); SR20DET: ~143 kg (315 lbs); Viper 8.4 V10: ~281 kg (620 lbs)
    # F140GA V12 (812): ~218 kg; LaFerrari V12: ~200 kg; L539 V12: ~236 kg; LFA V10: ~216 kg
    '13b': 122.0, '26b': 180.0, '73amg': 250.0, '81bb': 345.0,
    'F120A': 225.0, 'GM572': 282.0, 'GM632': 349.0,
    'HONDAV10F1': 108.0, 'L86': 249.0, 'LT7': 220.0, 'P60B40': 202.0,
    'S54B32': 217.0, 'S63B44B': 230.0, 'S85V10505HP': 277.0, 'SR20DET': 145.0,
    'V10ACR': 227.0, 'V12_789HP': 225.0,
    'laferrariV12': 225.0, 'lamboV12': 235.0, 'lexusV10': 160.0,
    # ICE Standard — templates round 1
    # Viper Gen1 8.0L V10: ~262 kg (577 lbs); One-77 7.3L V12: ~275 kg
    # Alfa 8C 4.7L V8 (Ferrari F136): ~196 kg; SSC Tuatara: ~175 kg (385 lbs SSC published)
    # Venom GT 7.0L TT V8 (LS-derived): ~250 kg; DB11 AMR 5.2L TT V12: ~258 kg
    # M178 4.0L TT V8: ~209 kg (461 lbs AMG published); F154CG F8: ~185 kg
    # M840T 720S: ~200 kg; 9A2 Evo GT2 RS flat-6: ~228 kg (503 lbs Porsche)
    'dodge_viper_gen1': 235.0, 'am_one77_v12': 260.0, 'alfa_8c_v8': 185.0,
    'ssc_tuatara_e85': 194.0, 'hennessey_venom_gt': 200.0, 'am_db11_amr_v12': 235.0,
    'amg_m178_gtr_pro': 209.0, 'ferrari_f8_v8': 200.0, 'mclaren_m840t': 200.0,
    'porsche_9a2_gt2rs': 200.0,
    # ICE Standard — templates round 2
    # 454 LS6 cast iron: ~308 kg (680 lbs); Ford 427 FE cast iron: ~308 kg
    # 426 HEMI cast iron: ~304 kg (670 lbs); Pontiac 400 RAiv cast iron: ~280 kg
    # LS7 aluminum: ~201 kg (443 lbs Corvette published); LT6 flat-plane: ~181 kg (399 lbs GM published)
    # Ferrari Enzo F140B V12: ~202 kg; 599 GTO F140CE V12: ~205 kg
    # Murciélago L539 V12: ~236 kg; Maserati MC12 F140 6.0L V12: ~202 kg
    # DB9 5.9L V12: ~195 kg; Cosworth GMA 4.0L V12: 178 kg (Gordon Murray published)
    # Pagani Zonda R AMG M120 V12 cast iron: ~272 kg (600 lbs); XJ220 JV6 TT V6: ~185 kg
    # Bentley 6.0 TT W12: ~291 kg (642 lbs); F154 488 Pista 3.9 V8: ~182 kg
    # M178 LS2 GT Black Series: ~209 kg; Porsche 5.7L V10 (Carrera GT): ~223 kg (492 lbs Porsche)
    # Ford 5.4L SC DOHC (2005 GT): ~230 kg; GT500 5.4L SC: ~220 kg
    # Cosworth 6.5L V12 (Valkyrie): 206 kg (Cosworth published); Ferrari F131 3.6L V8: ~185 kg
    'ls6_454_chevelle': 295.0, 'ford_427_fe_gt40': 258.0, 'chrysler_426_hemi': 347.0,
    'pontiac_ramairiv_400': 288.0, 'ls7_c6_corvette_z06': 195.0, 'lt6_c8_corvette_z06': 240.0,
    'ferrari_enzo_f140b': 225.0, 'ferrari_599gto_v12': 228.0, 'lambo_murcielago_sv': 250.0,
    'maserati_mc12_v12': 232.0, 'am_db9_v12': 235.0, 'gma_t50_cosworth_v12': 178.0,
    'pagani_zonda_r_v12': 210.0, 'jaguar_xj220_v6tt': 155.0, 'bentley_contgt_w12': 260.0,
    'porsche_carrera_gt_v10': 210.0,
    'ford_gt05_54sc': 200.0, 'shelby_gt500_07_54sc': 270.0,
    'am_valkyrie_cosworth_v12': 206.0, 'ferrari_360_f131': 188.0,
    # ICE Compact — stock
    # Theta II 2.0T: ~130 kg; EA888 Gen3B 2.0T: ~147 kg; 2JZ-GTE cast iron: ~200 kg (441 lbs)
    # Coyote Gen4 5.0L: ~196 kg (432 lbs); Bugatti W16: ~400 kg (882 lbs)
    # M178 4.0TT V8 (GT Black Series): ~209 kg; HEMI 392 6.4L: ~221 kg (488 lbs)
    # Hellcat 6.2L SC: ~243 kg (536 lbs); Koenigsegg V8 TT: ~191 kg (421 lbs Koenigsegg published)
    # Agera RS V8: ~188 kg; RB26DETT: ~168 kg (370 lbs); S58: ~183 kg (403 lbs BMW published)
    '20hyundai': 145.0, '20tfsi': 150.0, '2JZ320HP': 215.0, '50coyote': 220.0,
    'bugattiW16': 400.0, 'C63AMG671HP': 209.0, 'Hemi392_525HP': 227.0,
    'HemiHellcat_707HP': 227.0, 'KoenigseggHV8tt2300HP': 197.0, 'KoenigseggV8tt1280HP': 197.0,
    'RB26DET276HP': 252.0, 'RB26DET440HP': 258.0,
    'S58': 185.0,
    # ICE Compact — templates
    # EJ257 flat-4: ~132 kg (291 lbs); K20C1: ~118 kg; 4G63T: ~140 kg (308 lbs)
    # 2.3 EcoBoost: ~138 kg; MA1.01 992 Carrera S flat-6: ~214 kg (472 lbs Porsche)
    # G16E-GTS GR Yaris I3: ~95 kg (Toyota published); N54B30: ~162 kg (357 lbs BMW)
    # VR38DETT: ~205 kg (452 lbs Nissan); MA1.76 991 GT3 flat-6: ~228 kg
    # F20C S2000: ~120 kg; F22C: ~122 kg; K20A DC5: ~115 kg; K20A2 EP3: ~115 kg
    # C30A NSX V6: ~178 kg; C32B NSX-R V6: ~182 kg; 3S-GTE Gen3: ~152 kg (335 lbs Toyota)
    # 2GR-FZE SC V6 (Lotus Exige S): ~208 kg; S65 4.0L V8: ~202 kg (445 lbs BMW)
    # S55 3.0TT I6: ~155 kg (342 lbs BMW); S14 2.3L I4: ~112 kg (247 lbs BMW)
    # EA855 2.5T I5: ~148 kg (326 lbs Audi); F4Rt Megane RS250: ~122 kg
    # EP6FDT 1.6T: ~112 kg; L3-VDT Mazdaspeed3: ~138 kg
    # EA888 2.0T Golf R: ~147 kg; EcoBoost 2.3T Focus RS Mk3: ~138 kg
    # F136IB California 4.3L V8: ~195 kg; MA1.20 718 GT4 RS flat-6: ~214 kg
    # Alfa 1750 TBi 1.75T I4: ~107 kg (236 lbs)
    'subaru_ej257': 175.0, 'honda_k20c1': 135.0, 'mitsubishi_4g63t': 160.0,
    'ford_23_ecoboost': 141.0, 'porsche_992_cs': 210.0, 'toyota_gr_yaris': 109.0,
    'bmw_n54b30': 191.0, 'nissan_vr38dett': 276.0, 'porsche_991_gt3': 200.0,
    'honda_f20c_s2000ap1': 148.0, 'honda_f22c_s2000ap2': 150.0,
    'honda_k20a_dc5_itr': 130.0,
    'honda_c30a_nsx': 155.0, 'honda_c32b_nsxr': 153.0, 'toyota_3sgte_g3_mr2': 165.0,
    'lotus_exige_s_2grfze': 180.0, 'bmw_s65_e92_m3': 202.0, 'bmw_s55_f80_m3m4': 185.0,
    'bmw_s14_e30_m3': 106.0, 'audi_ea855_rs3_ttrs': 183.0,
    'renault_f4rt_megane_rs250': 149.0, 'peugeot_ep6fdt_308gti270': 136.0,
    'mazda_l3vdt_mps3': 145.0, 'vw_ea888_golf_r_mk75': 150.0,
    'ferrari_california_f136ib': 188.0,
    'porsche_718gt4rs_ma120': 183.0, 'alfa_4c_1750tbi': 135.0,
    # Diesel HD — stock
    # Audi 3.0 TDI V6: ~168 kg (370 lbs); Cummins 5.9L ISB: ~430 kg (948 lbs)
    # Detroit 6.5L V8: ~380 kg (838 lbs); Duramax L5P: ~417 kg (919 lbs)
    # Power Stroke 7.3L: ~430 kg (948 lbs); CAT C12: ~907 kg (2000 lbs)
    # Cummins X15: ~1349 kg (2975 lbs); DV27K race V8: ~2400 kg
    # Detroit DD16: ~1350 kg (2975 lbs); PACCAR MX-13: ~1020 kg (2250 lbs)
    # Audi R10 TDI V12 race: ~295 kg (651 lbs); Scania DC16 V8: ~1950 kg
    # VW 1.9 TDI: ~160 kg; Volvo D13: ~1050 kg; Volvo D17: ~1280 kg
    # Weichai WP17H: ~1350 kg; Mercedes OM471: ~1050 kg
    '30tdi': 219.0, '59cummins': 499.0, '65detroit': 300.0, '66duramax': 418.0,
    '73powerstroke': 417.0, 'CATC12490HP': 939.0,
    'CumminsX15x565': 1370.0,
    'DV27K1500HP': 1860.0, 'DetroidDD16_600HP': 1287.0,
    'PACCARxMXx13x510': 1185.0,
    'R10': 220.0, 'Scania770HP': 1340.0,
    'VW19TDI150HP': 160.0, 'VolvoD13': 1190.0, 'VolvoD17_780HP': 1345.0,
    'WeichaiWP17H_800HP': 1350.0, 'benzI6': 1150.0,
    # Diesel HD — templates round 1
    # CAT C15: ~1102 kg (2430 lbs); C18: ~1451 kg (3200 lbs); MaxxForce 13: ~1043 kg (2300 lbs)
    # Cummins ISX15: ~1349 kg; MAN D3876: ~1100 kg (2425 lbs); OM473: ~1380 kg (3042 lbs)
    # John Deere 9L: ~720 kg; Deutz TCD 16: ~1400 kg; Detroit Series 60: ~1089 kg (2401 lbs)
    # MTU 16V2000: ~4200 kg; CAT C32: ~4536 kg (10000 lbs); Liebherr D9508: ~1300 kg
    'cat_c15': 1666.0, 'cat_c18': 1673.0, 'navistar_maxxforce13': 1043.0,
    'man_d3876': 1345.0, 'mercedes_om473': 1350.0,
    'john_deere_9l': 720.0, 'deutz_tcd16_v8': 1400.0, 'detroit_series60': 1199.0,
    'mtu_16v2000': 4200.0, 'cat_c32': 4536.0, 'liebherr_d9508': 1300.0,
    'liebherr_d9512': 2800.0, 'perkins_2806': 1420.0, 'iveco_cursor13': 985.0,
    # Diesel HD — templates round 2
    'paccar_mx11_445': 870.0, 'daf_mx13_530': 1030.0, 'scania_dc13_500': 960.0,
    'man_d2676_500': 1010.0, 'volvo_d16g700': 1280.0,
    'cummins_x12_500': 900.0, 'cummins_qsk19_800': 2100.0,
    'cummins_qsk23_950': 2600.0, 'cummins_qsk38_1600': 5000.0,
    'cummins_qsk60_2300': 9200.0, 'cummins_qsk78_3500': 13500.0,
    'cat_3516_2000': 8500.0, 'cat_3608_3300': 18000.0, 'cat_3616_6600': 33000.0,
    'mtu_16v4000_2935': 15000.0, 'mtu_16v2000_2600': 4500.0,
    'wartsila_32_12500': 90000.0, 'wartsila_46f_20000': 300000.0, 'bergen_b3240_v16': 35000.0,
    # Motorcycle — stock  (engine-only dry weight kg)
    # Ducati 999R L-Twin Testastretta: ~57 kg; Fictional I4 superbike: ~65 kg
    # Suzuki Bandit 1250 I4: ~65 kg; Honda CBR600RR I4: ~47 kg
    # MotoGP prototype: ~66 kg; Harley Milwaukee-Eight 117: ~88 kg (194 lbs)
    # Hayabusa 1340cc I4: ~56 kg (123 lbs); Ducati 1199 L-Twin: ~55 kg (121 lbs)
    # GSX-R750: ~52 kg (115 lbs); Sportster XL1200: ~78 kg; SV650: ~50 kg; ZZR1400: ~62 kg
    '999r_150HP': 65.0,
    'Bike_i4_250HP': 68.0,
    'bandit1250145HP': 68.0,
    'gpproto240HP': 66.0,
    'harley_120HP': 88.0,
    'hayabusa_200HP': 75.0,
    'panigale1199170HP': 63.0,
    'r750140HP': 64.0,
    'sportster120065HP': 78.0,
    'sv65070HP': 42.0,
    'zzr1400200HP': 75.0,
    # Motorcycle — templates round 1
    # BMW S1000RR: ~64 kg (141 lbs BMW); CBR1000RR-R: ~64 kg
    # Kawasaki H2 SC I4: ~72 kg (supercharger); H2R: ~70 kg
    # Yamaha R1M: ~65 kg; Aprilia RSV4 V4: ~63 kg; MV Agusta F4 RR: ~67 kg
    # Ducati V4 R: ~64 kg; KTM 1290 SD R V-Twin: ~75 kg
    # Triumph Rocket 3 2458cc: ~110 kg (243 lbs); Norton V4 CR: ~65 kg
    # Indian FTR 1200: ~78 kg; Bimota Tesi H2: same as H2 ~72 kg
    'bmw_s1000rr': 60.0, 'honda_cbr1000rr_r': 64.0, 'kawasaki_h2': 90.0,
    'kawasaki_h2r': 88.0, 'yamaha_r1m': 65.0, 'aprilia_rsv4': 63.0,
    'mv_agusta_f4rr': 67.0, 'ducati_panigale_v4r': 63.0, 'ktm_1290_super_duke': 75.0,
    'triumph_rocket3': 120.0, 'norton_v4cr': 65.0, 'indian_ftr1200': 78.0,
    # Motorcycle — templates round 2
    # ZX-10R: ~64 kg; ZX-6R 636: ~52 kg; Z900: ~60 kg; SF V4: ~63 kg
    # Panigale V2: ~52 kg; R7 689cc: ~48 kg; MT-10: ~66 kg; Tracer 9: ~55 kg
    # CBR600RR 2024: ~47 kg; Daytona 660: ~52 kg; Speed Triple 1200: ~78 kg
    # Tuono V4: ~63 kg; BMW K1600: ~95 kg (I6); R18 Boxer: ~94 kg
    # F900R Parallel-Twin: ~52 kg; GSX-S1000: ~65 kg; V-Strom 1050: ~70 kg
    # KTM 890 Duke: ~58 kg; KTM 1290 Super Adv: ~75 kg; KTM RC390: ~32 kg
    # Pan America 1252cc: ~92 kg; Moto Guzzi V100: ~80 kg
    # Indian Scout 1250: ~80 kg; RE Interceptor 650: ~52 kg; Himalayan 450: ~32 kg
    'kawasaki_zx10r': 64.0, 'kawasaki_zx6r_636': 52.0, 'kawasaki_z900': 60.0,
    'ducati_panigale_v2': 52.0, 'yamaha_r7': 48.0,
    'yamaha_mt10': 66.0, 'yamaha_tracer9': 55.0, 'honda_cbr600rr_2024': 47.0,
    'triumph_daytona660': 52.0, 'triumph_speed_triple_1200': 78.0,
    'bmw_k1600': 95.0, 'bmw_r18': 94.0, 'bmw_f900r': 52.0, 'suzuki_gsx_s1000': 65.0,
    'suzuki_vstrom1050': 70.0, 'ktm_890_duke': 58.0,
    'ktm_rc390': 32.0, 'harley_pan_america': 92.0, 'moto_guzzi_v100': 80.0,
    'indian_scout_1250': 80.0, 'royal_enfield_interceptor650': 52.0,
    'royal_enfield_himalayan450': 32.0,
    # EV — motor system weight (motors + inverters, no battery, kg)
    # Alpine A290 single motor: ~88 kg; Aspark Owl 4-motor: ~95 kg
    # Audi RS e-tron GT dual PSM: ~165 kg; Bolt EV single: ~75 kg
    # Silverado EV quad: ~200 kg; Drako Dragon quad: ~90 kg
    # Elation Freedom dual: ~85 kg; Fisker Ocean Ultra dual: ~160 kg
    # GAC Aion Hyper SSR dual: ~92 kg; GMC Hummer EV quad Ultium: ~200 kg
    # Hyundai Ioniq 9 dual: ~175 kg; Lotus Evija 4-motor: ~84 kg
    # Lucid Air GTP tri-motor: ~145 kg; Lucid Air Sapphire tri-motor: ~150 kg
    # Lucid Gravity Dream dual: ~175 kg; MG MG4 single: ~72 kg; McMurtry Speirling: ~60 kg
    # Mercedes AMG GT XX concept dual: ~95 kg; Mercedes EQS 450+ single: ~155 kg
    # NIO EP9 quad: ~92 kg; NIO ET5 dual: ~118 kg; NetGain HyPer9 single: ~55 kg
    # Pininfarina Battista quad: ~88 kg; Polestar 2 Dual: ~140 kg
    # Polestar 3 LR Single: ~105 kg; Porsche Taycan Turbo S dual PSM: ~125 kg
    # Rimac Nevera quad: ~97 kg; Rimac Nevera R quad: ~98 kg
    # Rivian R1T Quad Gen1: ~200 kg; Tata Tiago EV single: ~55 kg
    # Tesla Model S Plaid tri-motor: ~90 kg; Model X Plaid: ~90 kg
    # Tesla Semi quad: ~220 kg; VinFast VF e34 single: ~72 kg; Volvo EX30 single: ~80 kg
    # Wuling Mini EV single: ~35 kg; Yangwang U9 quad: ~92 kg
    'EVAlpineA290': 88.0, 'EVAsparkOwl': 110.0, 'EVAudiRSetronGTPerformance': 165.0,
    'EVChevroletBoltEV': 40.0, 'EVChevroletSilveradoEVWT': 200.0, 'EVDrakoDragon': 90.0,
    'EVElationFreedom': 85.0, 'EVFiskerOceanUltra': 160.0, 'EVGACAionHyperSSR': 92.0,
    'EVGMCHummerEV': 130.0, 'EVHyundaiIoniq9': 175.0, 'EVLotusEvija': 100.0,
    'EVLucidAirSapphire': 85.0,
    'EVLucidGravityDreamEdition': 175.0, 'EVMGMG4EV': 72.0, 'EVMHero917': 60.0,
    'EVMercedesAMGGTXXConcept': 95.0, 'EVMercedesEQS450Plus': 155.0,
    'EVNIOEP9': 92.0, 'EVNIOET5': 118.0, 'EVNetGainHyper9': 55.0,
    'EVPininfarinaBattista': 115.0, 'EVPolestar2DualMotor': 140.0,
    'EVPolestar3LongRangeSingleMotor': 105.0, 'EVPorscheTaycanTurboS': 70.0,
    'EVRimacNeveraR': 125.0, 'EVRivianR1TQuadMotorGen1': 200.0,
    'EVTataTiagoEV': 35.0, 'EVTeslaModelSPlaid': 90.0,
    'EVTeslaSemi': 220.0, 'EVVinFastVFe34': 72.0, 'EVVolvoEX30': 80.0,
    'EVWulingHongguangMiniEV': 25.0, 'EVYangwangU9TrackEdition': 92.0,
}


def _fallback_weight(variant: str, hp: float) -> float:
    """Estimate engine weight when not in ENGINE_WEIGHTS."""
    if variant == 'bike':
        if hp < 80:   return 35.0
        if hp < 150:  return 50.0
        if hp < 250:  return 65.0
        return 85.0
    if variant == 'diesel_hd':
        if hp < 200:   return 200.0
        if hp < 400:   return 450.0
        if hp < 700:   return 900.0
        if hp < 1200:  return 1400.0
        if hp < 2000:  return 2500.0
        return max(5000.0, hp * 4.0)
    if variant == 'ev':
        return round(max(60.0, hp * 0.15), 1)
    # ICE standard / compact
    if hp < 150:  return 120.0
    if hp < 250:  return 145.0
    if hp < 400:  return 170.0
    if hp < 600:  return 200.0
    if hp < 900:  return 240.0
    return 275.0

def _fuel_prefix_for_spec(spec: object) -> str:
    variant = getattr(spec, 'variant', '')
    fuel_type = int(getattr(spec, 'fuel_type', 1) or 1)
    if variant == 'ev' or fuel_type == 3:
        return '[E]'
    if variant == 'diesel_hd' or fuel_type == 2:
        return '[D]'
    return '[G]'


def _pack_shop_title_for_spec(spec: object) -> str:
    return f'{_fuel_prefix_for_spec(spec)} {getattr(spec, "shop_title", "").strip()}'.strip()


def batch_register_engines() -> Dict:
    """Register / update every mod engine in the Engines DataTable with accurate values."""
    engine_dir = os.path.join(MOD_BASE, 'Engine')
    if not os.path.isdir(engine_dir):
        return {'error': 'Engine directory not found'}
    dt_uasset_p = ENGINES_DT_BASE + '.uasset'
    dt_uexp_p = ENGINES_DT_BASE + '.uexp'
    if not os.path.isfile(dt_uasset_p) or not os.path.isfile(dt_uexp_p):
        return {'error': 'Engines DataTable not found'}

    os.makedirs(BACKUP_DIR, exist_ok=True)
    for src, dst in [(dt_uasset_p, os.path.join(BACKUP_DIR, 'Engines_dt.uasset.batch_bak')),
                     (dt_uexp_p,   os.path.join(BACKUP_DIR, 'Engines_dt.uexp.batch_bak'))]:
        if not os.path.isfile(dst):
            shutil.copy2(src, dst)
    try:
        result = _sync_engine_datatable_tree(os.path.join(MOD_ROOT, 'MotorTown'), prefer_existing_shop=False)
    except Exception as exc:
        return {'error': str(exc)}

    return {
        'success': True,
        'created': result['created'],
        'updated': result['updated'],
        'removed': len(result['removed']),
        'errors': result['errors'],
        'message': (f'Registered {result["created"]} new, updated {result["updated"]} existing, '
                    f'removed {len(result["removed"])} stale rows'
                    + (f', {len(result["errors"])} errors' if result['errors'] else '')),
    }


def _classify_tire_group(file_name: str) -> tuple[str, str]:
    """Return a UI grouping for tire templates."""
    low = file_name.lower()
    if 'motorcycle' in low:
        return ('motorcycle', 'Motorcycle')
    if 'heavymachine' in low:
        return ('heavy_machine', 'Heavy Machine')
    if 'heavyduty' in low:
        return ('heavy_duty', 'Heavy Duty')
    if any(x in low for x in ('offroad', 'rally', 'baja')):
        return ('offroad', 'Offroad')
    if any(x in low for x in ('drift', 'performance', 'police')):
        return ('performance', 'Performance')
    if 'basic' in low:
        return ('street', 'Street')
    return ('special', 'Special')


def _register_tire_vehicleparts_entry(ua: bytes, ue: bytes, tire_name: str, *,
                                      display_name: str, code: str,
                                      price: int, weight: float,
                                      donor_row: Optional[Dict[str, Any]] = None,
                                      update_existing: bool = True) -> tuple[bytes, bytes, str]:
    """Ensure one tire has a matching VehicleParts0 row and asset import."""
    from parsers.uasset_vehicleparts_dt import get_fname_index as get_vp_fname_index
    from parsers.uasset_vehicleparts_dt import append_name_entries, add_part_import, parse_imports
    from parsers.uexp_vehicleparts_dt import build_row_from_template, append_row, find_row_by_key, update_row

    ua, indexes = append_name_entries(ua, [tire_name])
    fname_idx = indexes.get(tire_name, get_vp_fname_index(ua, tire_name))
    if fname_idx < 0:
        raise ValueError(f'Failed to allocate VehicleParts0 FName for {tire_name}')

    imports = parse_imports(ua)
    existing = find_row_by_key(ue, fname_idx=fname_idx, fname_number=0, imports=imports)
    primary_text = str(code or '').strip() or str(display_name or '').strip() or tire_name
    secondary_text = str(display_name or '').strip()

    if existing is not None:
        if update_existing:
            if existing.get('secondary_field') is None:
                secondary_text = ''
            ue = update_row(
                ue,
                fname_idx=fname_idx,
                fname_number=0,
                primary_text=primary_text,
                secondary_text=secondary_text,
                price=price,
                weight=weight,
                imports=imports,
            )
            return ua, ue, 'updated'
        return ua, ue, 'kept'

    if donor_row is None:
        raise ValueError(f'No VehicleParts0 donor row available for {tire_name}')

    ua, new_asset_ref, _new_pkg_ref = add_part_import(
        ua,
        package_path=f'/Game/Cars/Parts/Tire/{tire_name}',
        object_name=tire_name,
        class_name='MTTirePhysicsDataAsset',
    )

    donor_tire_refs = [
        ref['negative_ref']
        for ref in donor_row.get('asset_refs', [])
        if ref.get('class_name') == 'MTTirePhysicsDataAsset'
    ]
    if not donor_tire_refs:
        raise ValueError(f'Donor row has no tire asset ref for {tire_name}')

    import_ref_map = {old_ref: new_asset_ref for old_ref in donor_tire_refs}
    if donor_row.get('secondary_field') is None:
        secondary_text = ''

    row_bytes = build_row_from_template(
        donor_row,
        fname_idx=fname_idx,
        fname_number=0,
        primary_text=primary_text,
        secondary_text=secondary_text,
        price=price,
        weight=weight,
        import_ref_map=import_ref_map,
    )
    ue = append_row(ue, row_bytes)
    return ua, ue, 'created'


def _remove_tire_vehicleparts_entries(ua: bytes, ue: bytes, tire_name: str) -> tuple[bytes, int]:
    """Remove every VehicleParts0 row tied to one generated tire."""
    from parsers.uasset_vehicleparts_dt import get_fname_index as get_vp_fname_index
    from parsers.uexp_vehicleparts_dt import build_vehicleparts_catalog, remove_row

    catalog = build_vehicleparts_catalog(ua, ue)
    targets: Dict[tuple[int, int], Dict[str, Any]] = {}
    fname_idx = get_vp_fname_index(ua, tire_name)
    if fname_idx >= 0:
        for row in catalog.get('rows', []):
            if row.get('fname_idx') == fname_idx:
                targets[(row['fname_idx'], row['fname_number'])] = row
    for row in catalog.get('rows_by_asset_object', {}).get(tire_name, []):
        targets[(row['fname_idx'], row['fname_number'])] = row

    removed = 0
    new_ue = ue
    for row_key in sorted(targets.keys(), reverse=True):
        new_ue = remove_row(
            new_ue,
            fname_idx=row_key[0],
            fname_number=row_key[1],
            idx_to_name=catalog['idx_to_name'],
            imports=catalog['imports'],
        )
        catalog = build_vehicleparts_catalog(ua, new_ue)
        removed += 1
    return new_ue, removed


def _validate_tire_generation(uasset_path: str, uexp_path: str, expected_name: str,
                              vp_uasset_path: str, vp_uexp_path: str) -> None:
    """Fail fast when a generated tire asset pair or VehicleParts0 row is invalid."""
    from parsers.uasset_vehicleparts_dt import get_fname_index as get_vp_fname_index
    from parsers.uexp_vehicleparts_dt import build_vehicleparts_catalog, find_row_by_key

    if not os.path.isfile(uasset_path) or not os.path.isfile(uexp_path):
        raise FileNotFoundError(f'Missing tire asset files for {expected_name}')
    if not os.path.isfile(vp_uasset_path) or not os.path.isfile(vp_uexp_path):
        raise FileNotFoundError('VehicleParts0 files are missing')

    asset = parse_uasset(uasset_path)
    if str(asset.class_type).lower() != 'tire':
        raise ValueError(f'{expected_name} is not a Tire asset (got {asset.class_type})')
    if asset.asset_name != expected_name:
        raise ValueError(f'Tire asset name mismatch: {asset.asset_name} vs {expected_name}')

    with open(uexp_path, 'rb') as f:
        tire_bytes = f.read()
    tire = parse_tire(tire_bytes)
    rebuilt = serialize_tire(tire)
    if len(rebuilt) != len(tire_bytes):
        raise ValueError(f'Tire serialization size mismatch: {len(rebuilt)} vs {len(tire_bytes)}')

    with open(vp_uasset_path, 'rb') as f:
        vp_ua = f.read()
    with open(vp_uexp_path, 'rb') as f:
        vp_ue = f.read()
    _validate_uasset_serial_size(vp_uasset_path, vp_uexp_path, 'VehicleParts0')
    catalog = build_vehicleparts_catalog(vp_ua, vp_ue)
    if not catalog.get('rows_by_asset_object', {}).get(expected_name):
        raise ValueError(f'No VehicleParts0 row references {expected_name}')

    fname_idx = get_vp_fname_index(vp_ua, expected_name)
    if fname_idx < 0:
        raise ValueError(f'No VehicleParts0 FName exists for {expected_name}')
    row = find_row_by_key(
        vp_ue,
        fname_idx=fname_idx,
        fname_number=0,
        idx_to_name=catalog['idx_to_name'],
        imports=catalog['imports'],
    )
    if row is None:
        raise ValueError(f'No VehicleParts0 row key exists for {expected_name}')


def _load_tire_template_catalog() -> Dict[str, Any]:
    global _TIRE_TEMPLATE_CATALOG_CACHE

    source_files, cache_key = _tire_template_files_and_stamp()
    if _TIRE_TEMPLATE_CATALOG_CACHE and _TIRE_TEMPLATE_CATALOG_CACHE[0] == cache_key:
        return _TIRE_TEMPLATE_CATALOG_CACHE[1]

    tire_field_catalog = _load_tire_field_catalog()
    known_properties = list(tire_field_catalog.get('all_properties') or [])
    templates: Dict[str, Dict[str, Any]] = {}

    for source, files in source_files.items():
        for file_path in files:
            name = os.path.splitext(os.path.basename(file_path))[0]
            template_path = f'{source}/Tire/{name}'
            try:
                detail = get_part_detail(template_path)
                if detail.get('error'):
                    continue
                group_key, group_label = _classify_tire_group(name)
                group_info = tire_field_catalog.get('groups', {}).get(group_key, {})
                group_properties = list(group_info.get('properties') or detail.get('properties', {}).keys())
                group = templates.setdefault(group_key, {
                    'label': group_label,
                    'properties': group_properties,
                    'known_properties': known_properties,
                    'tires': [],
                })
                shop = detail.get('metadata', {}).get('shop', {})
                props = detail.get('properties', {})
                current_properties = list(tire_field_catalog.get('templates', {}).get(template_path) or props.keys())
                from native_services import estimate_tire_grip_g as _estimate_grip
                grip_g = _estimate_grip(detail)
                group['tires'].append({
                    'name': name,
                    'path': template_path,
                    'title': shop.get('display_name') or name,
                    'code': shop.get('code', ''),
                    'price': shop.get('price', 500),
                    'weight': shop.get('weight', 10.0),
                    'source': source,
                    'property_count': detail.get('metadata', {}).get('property_count', len(current_properties)),
                    'properties': current_properties,
                    'possible_properties': group_properties,
                    'missing_possible_properties': [
                        key for key in group_properties
                        if key not in current_properties
                    ],
                    'missing_known_properties': [
                        key for key in known_properties
                        if key not in current_properties
                    ],
                    'grip_g': grip_g,
                })
            except Exception:
                continue

    for group in templates.values():
        group['tires'].sort(key=lambda item: (item['title'].lower(), item['name'].lower()))

    ordered = {}
    for key in ('street', 'performance', 'offroad', 'heavy_duty', 'heavy_machine', 'motorcycle', 'special'):
        if key in templates:
            ordered[key] = templates[key]
    catalog = {'templates': ordered or templates}
    _TIRE_TEMPLATE_CATALOG_CACHE = (cache_key, catalog)
    return catalog


def get_tire_templates() -> Dict:
    """Return available tire templates grouped by family."""
    return _load_tire_template_catalog()


_re = __import__('re')
_CYL_RE    = _re.compile(r'\b[IVWF](\d+)\b')        # I4, V8, W12, F6 …
_FLAT_RE   = _re.compile(r'[Ff]lat[-\s]?(\d+)')     # Flat-4, Flat 6
_BOXER_RE  = _re.compile(r'[Bb]oxer[-\s]?(\d+)')    # Boxer-4, Boxer 6

def _cylinder_group(title: str):
    """Return (group_key, group_label) for an ICE engine based on its display name."""
    t = title.upper()
    # Rotary engines
    if any(x in t for x in ('ROTARY', 'ROTOR', 'REW', '13B', '26B', 'WANKEL')):
        return ('cyl_rotary', 'Rotary')
    # Flat / Boxer engines (Flat-4, Flat-6, etc.)
    m = _FLAT_RE.search(title) or _BOXER_RE.search(title)
    if m:
        n = int(m.group(1))
        if n <= 4:  return ('cyl_4',  '4 Cylinder')
        if n <= 6:  return ('cyl_6',  '6 Cylinder')
        if n <= 8:  return ('cyl_8',  '8 Cylinder')
        if n <= 10: return ('cyl_10', '10 Cylinder')
        return ('cyl_12', '12+ Cylinder')
    # Standard configs: I4, V8, W12, F6 …
    m = _CYL_RE.search(title)
    if m:
        n = int(m.group(1))
        if n <= 4:  return ('cyl_4',  '4 Cylinder')
        if n <= 6:  return ('cyl_6',  '6 Cylinder')
        if n <= 8:  return ('cyl_8',  '8 Cylinder')
        if n <= 10: return ('cyl_10', '10 Cylinder')
        return ('cyl_12', '12+ Cylinder')
    # Known 4-cylinder engines whose names don't follow standard patterns
    if 'EA888' in title or 'TFSI' in t or 'TSI' in t:
        return ('cyl_4', '4 Cylinder')
    return ('cyl_4', '4 Cylinder')   # safe fallback — unknown ICE → 4 Cyl


def _load_engine_template_catalog() -> Dict[str, Any]:
    global _ENGINE_TEMPLATE_CATALOG_CACHE

    _, cache_key = _template_engine_files_and_stamp()
    if _ENGINE_TEMPLATE_CATALOG_CACHE and _ENGINE_TEMPLATE_CATALOG_CACHE[0] == cache_key:
        return _ENGINE_TEMPLATE_CATALOG_CACHE[1]

    from parsers.uexp_engine import VARIANT_SCHEMAS
    from template_engines import canonical_template_name, load_template_specs

    audit_summary = _template_audit_summary(_audit_template_engines())
    specs = load_template_specs(TEMPLATES_ENGINE_DIR, ENGINE_DISPLAY_NAMES)
    if not specs:
        catalog = {'error': 'No engine templates found', 'audit': audit_summary}
        _ENGINE_TEMPLATE_CATALOG_CACHE = (cache_key, catalog)
        return catalog

    templates: Dict[str, Dict[str, Any]] = {}
    ice_variants = {'ice_standard', 'ice_compact'}
    non_ice_labels = {'diesel_hd': 'Diesel HD', 'bike': 'Bike', 'ev': 'EV'}
    fuel_map = {0: 'Gas', 1: 'Gas', 2: 'Diesel', 3: 'Electric'}
    variant_schema_map = {variant.value: variant for variant in VARIANT_SCHEMAS}
    engine_field_catalog = _load_engine_field_catalog()
    known_properties = list(engine_field_catalog.get('all_properties') or [])
    variant_property_map = {
        key: list(value.get('properties') or [])
        for key, value in (engine_field_catalog.get('variants') or {}).items()
    }
    template_property_map = {
        key: list(value)
        for key, value in (engine_field_catalog.get('templates') or {}).items()
    }
    price_models = {
        False: _get_template_price_model(include_bikes=False),
        True: _get_template_price_model(include_bikes=True),
    }

    for spec in specs:
        vname = spec.variant
        if vname in ice_variants:
            group_key, group_label = _cylinder_group(spec.shop_title)
        else:
            group_key = vname
            group_label = non_ice_labels.get(vname, vname.replace('_', ' ').title())

        if group_key not in templates:
            variant = variant_schema_map.get(vname)
            possible_properties = list(
                variant_property_map.get(vname)
                or ([p[0] for p in VARIANT_SCHEMAS[variant] if p[0] != 'TorqueCurve'] if variant else [])
            )
            templates[group_key] = {
                'variant': vname,
                'label': group_label,
                'properties': possible_properties,
                'known_properties': known_properties,
                'engines': [],
            }

        canonical_name = canonical_template_name(spec.name, ENGINE_DISPLAY_NAMES)
        weight = ENGINE_WEIGHTS.get(canonical_name) or _fallback_weight(vname, spec.hp)
        price_model = price_models[vname == 'bike']
        price = recommend_price_from_torque(price_model, spec.torque_nm)
        current_properties = list(template_property_map.get(spec.name) or [])
        possible_properties = list(templates[group_key]['properties'])
        templates[group_key]['engines'].append({
            'name': spec.name,
            'title': spec.shop_title,
            'description': spec.shop_subtitle,
            'hp': spec.hp,
            'torque': spec.torque_nm,
            'rpm': spec.max_rpm,
            'weight': weight,
            'price': price,
            'fuel': fuel_map.get(spec.fuel_type, 'Gas'),
            'fuel_raw': spec.fuel_type,
            'property_count': len(current_properties),
            'properties': current_properties,
            'possible_properties': possible_properties,
            'missing_possible_properties': [
                key for key in possible_properties
                if key not in current_properties
            ],
            'missing_known_properties': [
                key for key in known_properties
                if key not in current_properties
            ],
        })

    for vdata in templates.values():
        vdata['engines'].sort(key=lambda e: e['hp'])

    cyl_keys = {'cyl_4', 'cyl_6', 'cyl_8', 'cyl_10', 'cyl_12', 'cyl_rotary', 'cyl_other'}
    gas_engines = []
    gas_props = None
    for key in cyl_keys:
        if key in templates:
            gas_engines.extend(templates[key]['engines'])
            if gas_props is None:
                gas_props = templates[key]['properties']
    if gas_engines:
        gas_engines.sort(key=lambda e: e['hp'])
        templates['gas'] = {
            'variant': 'ice_standard',
            'label': 'Gas',
            'properties': gas_props or [],
            'known_properties': known_properties,
            'engines': gas_engines,
        }

    tab_order = ['cyl_4', 'cyl_6', 'cyl_8', 'cyl_10', 'cyl_12',
                 'cyl_rotary', 'gas', 'diesel_hd', 'bike', 'ev']
    ordered_templates = {key: templates[key] for key in tab_order if key in templates}
    catalog = {'templates': ordered_templates, 'audit': audit_summary}
    _ENGINE_TEMPLATE_CATALOG_CACHE = (cache_key, catalog)
    return catalog


def get_engine_templates() -> Dict:
    """Return available engine templates grouped by cylinder count (ICE) or variant (Diesel/Bike/EV)."""
    return _load_engine_template_catalog()


def recommend_engine_price(data: Dict) -> Dict:
    """Recommend a weighted torque-based shop price for the create-engine UI."""
    raw_torque = data.get('torque_nm')
    try:
        torque_nm = float(raw_torque)
    except (TypeError, ValueError):
        return {'error': 'A valid torque value is required'}

    if torque_nm <= 0:
        return {'error': 'Torque must be greater than zero'}

    include_bikes = bool(data.get('include_bikes', False))
    model = _get_template_price_model(include_bikes=include_bikes)
    price = recommend_price_from_torque(model, torque_nm)

    return {
        'success': True,
        'price': price,
        'torque_nm': round(torque_nm, 1),
        'formula': 'weighted_torque_percentile',
        'reference_engine': model.reference_engine,
        'reference_torque_nm': round(model.reference_torque_nm, 1),
        'reference_price': model.reference_price,
        'min_price': model.min_price,
        'max_price': model.max_price,
        'include_bikes': include_bikes,
    }


def create_engine(data: Dict) -> Dict:
    """Create a new engine from a template."""
    from engine_audio import load_engine_audio_overrides, update_primary_engine_sound_asset
    from parsers.uasset_clone import clone_uasset, update_sound_in_uasset
    from parsers.uexp_engine import parse_engine, serialize_engine, detect_variant
    from parsers.vanilla_engine_builder import (
        build_donor_backed_uexp_bytes,
        rebuild_template,
        resolve_structure_donor_name,
    )
    from template_engines import load_template_specs, split_shop_display

    template_name = data.get('template', '')
    new_name = data.get('name', '').strip()
    properties = data.get('properties', {})
    raw_display_name = str(data.get('display_name') or '').strip() or ENGINE_DISPLAY_NAMES.get(new_name, new_name)
    raw_description = str(data.get('description') or '').strip()
    display_name, split_description = split_shop_display(raw_display_name)
    description = raw_description or split_description
    raw_price = data.get('price')
    raw_weight = data.get('weight')
    sound_dir = data.get('sound_dir', '').strip() or None
    vehicle_type = str(data.get('vehicle_type') or '').strip() or None
    expected_version = (data.get('expected_version') or '').strip()

    # If no template was named explicitly, fall back to the vehicle_type
    # selection (already a vanilla engine name like 'HeavyDuty_440HP').
    # Final fallback to a sane default so the form is never blocked
    # waiting for an explicit pick.
    if not template_name:
        template_name = (vehicle_type or '').strip() or 'HeavyDuty_440HP'
    if not new_name:
        return {'error': 'No name specified for new engine'}

    # Validate name
    import re
    if not re.match(r'^[a-zA-Z0-9]+$', new_name):
        return {'error': 'Name must contain only letters and numbers. Underscores are blocked because they can freeze engines in-game.'}

    engine_dir = MOD_ENGINE_DIR
    os.makedirs(engine_dir, exist_ok=True)

    # Source-of-property-values lookup order:
    #   1. Curated template set (data/templates/Engine/) — historical;
    #      empty by default since v6.x cleanup.
    #   2. User's previously-generated mod engines (engine_dir).
    #   3. Vanilla base-game engines (VANILLA_BASE/Engine/) — used as
    #      the default starting point for new creations now that the
    #      curated template set has been emptied.
    template_uexp = os.path.join(TEMPLATES_ENGINE_DIR, template_name + '.uexp')
    template_uasset = os.path.join(TEMPLATES_ENGINE_DIR, template_name + '.uasset')
    if not os.path.isfile(template_uexp) or not os.path.isfile(template_uasset):
        template_uexp = os.path.join(engine_dir, template_name + '.uexp')
        template_uasset = os.path.join(engine_dir, template_name + '.uasset')
    if not os.path.isfile(template_uexp) or not os.path.isfile(template_uasset):
        vanilla_engine_dir = os.path.join(VANILLA_BASE, 'Engine')
        template_uexp = os.path.join(vanilla_engine_dir, template_name + '.uexp')
        template_uasset = os.path.join(vanilla_engine_dir, template_name + '.uasset')
    if not os.path.isfile(template_uexp) or not os.path.isfile(template_uasset):
        return {'error': f'Template "{template_name}" not found in templates/, mod/, or vanilla/'}

    template_audit = None
    if os.path.dirname(os.path.abspath(template_uexp)) == os.path.abspath(TEMPLATES_ENGINE_DIR):
        template_audit = _audit_template_engines()
        if not template_audit['valid']:
            return {
                'error': _template_audit_preview(template_audit),
                'template_audit': _template_audit_summary(template_audit),
            }

    with open(template_uexp, 'rb') as f:
        uexp_data = f.read()

    try:
        engine = parse_engine(uexp_data)
    except Exception as e:
        return {'error': f'Failed to parse template: {e}'}

    # Detect variant for DataTable tail selection
    try:
        variant = detect_variant(uexp_data).value
    except Exception:
        variant = 'ice_standard'

    donor_name = None
    override_sound_asset = None
    if os.path.dirname(os.path.abspath(template_uexp)) == os.path.abspath(TEMPLATES_ENGINE_DIR):
        template_specs = {spec.name: spec for spec in load_template_specs(TEMPLATES_ENGINE_DIR, ENGINE_DISPLAY_NAMES)}
        template_spec = template_specs.get(template_name)
        if template_spec is not None:
            donor_name = template_spec.donor_name
            override_row = load_engine_audio_overrides().get(template_name) or {}
            if override_row.get('enabled'):
                override_sound_asset = override_row.get('override_sound_asset') or None
            if not sound_dir:
                sound_dir = template_spec.sound_dir or None

    # Extract and validate peak torque/HP RPM and Max HP (required fields).
    # Strip thousands-separator commas so "12,000" parses identically to
    # "12000" — UX nicety: users can type either form.
    def _strip_commas(s: str) -> str:
        return s.replace(',', '') if isinstance(s, str) else s

    peak_torque_rpm_str = _strip_commas(properties.pop('_peak_torque_rpm', ''))
    peak_hp_rpm_str = _strip_commas(properties.pop('_peak_hp_rpm', ''))
    max_hp_str = _strip_commas(properties.pop('_max_hp', ''))
    # Apply the same stripping to every other property value so the
    # downstream float()/int() conversions don't choke on commas.
    properties = {k: _strip_commas(v) for k, v in properties.items()}
    try:
        peak_torque_rpm = float(peak_torque_rpm_str)
    except (TypeError, ValueError):
        return {'error': 'Peak Torque @ RPM is required. Enter the RPM where peak torque occurs.'}
    try:
        peak_hp_rpm = float(peak_hp_rpm_str)
    except (TypeError, ValueError):
        return {'error': 'Max HP @ RPM is required. Enter the RPM where peak horsepower occurs.'}
    if peak_torque_rpm <= 0:
        return {'error': 'Peak Torque @ RPM must be greater than 0.'}
    if peak_hp_rpm <= 0:
        return {'error': 'Max HP @ RPM must be greater than 0.'}
    if peak_hp_rpm <= peak_torque_rpm:
        return {'error': 'Max HP @ RPM must be higher than Peak Torque @ RPM.'}
    try:
        max_hp = float(max_hp_str)
    except (TypeError, ValueError):
        return {'error': 'Max HP is required. Enter the peak horsepower value.'}
    if max_hp <= 0:
        return {'error': 'Max HP must be greater than 0.'}

    # Apply property modifications
    for key, value in properties.items():
        if _is_blank_optional_value(value):
            continue
        if key in engine.properties:
            prop_type = type(engine.properties[key])
            if key == 'MaxTorque':
                engine.properties[key] = float(value) * 10000
            elif key == 'MotorMaxPower':
                engine.properties[key] = float(value) * 10000
            elif prop_type == float:
                engine.properties[key] = float(value)
            elif prop_type == int:
                engine.properties[key] = int(value)

    # Validate peak RPM values against MaxRPM
    max_rpm = engine.properties.get('MaxRPM', 0)
    if max_rpm > 0:
        if peak_torque_rpm >= max_rpm:
            return {'error': f'Peak Torque RPM ({peak_torque_rpm:.0f}) must be less than Max RPM ({max_rpm:.0f}).'}
        if peak_hp_rpm > max_rpm:
            return {'error': f'Max HP RPM ({peak_hp_rpm:.0f}) must not exceed Max RPM ({max_rpm:.0f}).'}
        # Validate HP is physically achievable: HP = Torque × RPM / 7121
        max_torque_nm = engine.properties.get('MaxTorque', 0) / 10000.0
        if max_torque_nm > 0 and peak_hp_rpm > 0:
            max_achievable_hp = max_torque_nm * peak_hp_rpm / 7121.0
            if max_hp > max_achievable_hp * 1.01:  # 1% tolerance
                return {'error': f'Max HP ({max_hp:.0f}) exceeds what is physically possible '
                        f'with {max_torque_nm:.0f} Nm at {peak_hp_rpm:.0f} RPM '
                        f'(max ~{max_achievable_hp:.0f} HP). '
                        f'Increase torque or HP RPM.'}

    # Use the user's Max HP when provided (curve is shaped to match it);
    # fall back to generic estimate for legacy/EV engines.
    hp = round(max_hp, 1) if max_hp > 0 else round(engine.estimated_hp(), 1)
    torque_nm = round(engine.max_torque_nm, 1)
    default_shop = _default_shop_values_for_engine(template_name, variant, hp, torque_nm)
    try:
        price = max(0, int(raw_price))
    except (TypeError, ValueError):
        price = int(default_shop['price'])
    try:
        weight = max(0.0, float(raw_weight))
    except (TypeError, ValueError):
        weight = float(default_shop['weight'])

    # Generate new .uexp
    serialized_template_data = serialize_engine(engine)
    if donor_name:
        structure_donor_name = resolve_structure_donor_name(variant, donor_name, hp)
        donor_uexp_path = os.path.join(VANILLA_BASE, 'Engine', structure_donor_name + '.uexp')
        if not os.path.isfile(donor_uexp_path):
            return {'error': f'Vanilla donor "{structure_donor_name}" not found'}
        new_uexp_data = build_donor_backed_uexp_bytes(
            serialized_template_data,
            open(donor_uexp_path, 'rb').read(),
        )
    else:
        new_uexp_data = serialized_template_data

    if not donor_name and len(new_uexp_data) != len(uexp_data):
        return {'error': f'Serialization size mismatch: {len(new_uexp_data)} vs {len(uexp_data)}'}

    new_uasset_path = os.path.join(engine_dir, new_name + '.uasset')
    new_uexp_path = os.path.join(engine_dir, new_name + '.uexp')
    dt_uasset_path = ENGINES_DT_BASE + '.uasset'
    dt_uexp_path = ENGINES_DT_BASE + '.uexp'

    with MOD_WRITE_LOCK:
        live_conflict = _check_live_version(expected_version)
        if live_conflict:
            return {
                'error': 'Live data changed. Reload and try again.',
                'conflict': True,
                'state_version': live_conflict['version'],
            }

        if os.path.isfile(new_uexp_path) or os.path.isfile(new_uasset_path):
            return {'error': f'Engine "{new_name}" already exists'}

        dt_result = {}
        dt_uasset_bak = None
        dt_uexp_bak = None

        try:
            if donor_name:
                rebuild_template(
                    new_name,
                    variant,
                    os.path.join(VANILLA_BASE, 'Engine'),
                    engine_dir,
                    len(new_uexp_data),
                    donor_name=donor_name,
                    sound_dir=sound_dir,
                )
            else:
                clone_uasset(template_uasset, new_name, new_uasset_path, sound_dir=sound_dir)

            if override_sound_asset and os.path.isfile(new_uasset_path):
                update_primary_engine_sound_asset(Path(new_uasset_path), override_sound_asset)

            with open(new_uexp_path, 'wb') as f:
                f.write(new_uexp_data)

            # Clone and reshape torque curve (always — both fields are required)
            if True:
                max_rpm = engine.properties.get('MaxRPM', 0)
                if max_rpm > 0:
                    from parsers.uexp_torquecurve import build_shifted_curve
                    from parsers.uasset import parse_uasset
                    # Find the template's torque curve
                    tc_asset = parse_uasset(template_uasset)
                    tc_name = tc_asset.torque_curve_name
                    if tc_name:
                        tc_uexp_src = os.path.join(VANILLA_BASE, 'Engine', 'TorqueCurve', tc_name + '.uexp')
                        tc_uasset_src = os.path.join(VANILLA_BASE, 'Engine', 'TorqueCurve', tc_name + '.uasset')
                        if os.path.isfile(tc_uexp_src) and os.path.isfile(tc_uasset_src):
                            new_tc_name = f'TorqueCurve_{new_name}'
                            tc_out_dir = os.path.join(engine_dir, 'TorqueCurve')
                            os.makedirs(tc_out_dir, exist_ok=True)
                            new_tc_uasset = os.path.join(tc_out_dir, new_tc_name + '.uasset')
                            new_tc_uexp = os.path.join(tc_out_dir, new_tc_name + '.uexp')
                            # Clone the .uasset with new name
                            clone_uasset(tc_uasset_src, new_tc_name, new_tc_uasset)
                            # Build shifted .uexp with both peak torque and peak HP targets
                            tc_data = open(tc_uexp_src, 'rb').read()
                            max_torque_nm = engine.properties.get('MaxTorque', 0) / 10000.0
                            shifted_tc = build_shifted_curve(
                                tc_data, peak_torque_rpm, max_rpm,
                                peak_hp_rpm=peak_hp_rpm,
                                max_hp=max_hp,
                                max_torque_nm=max_torque_nm,
                            )
                            with open(new_tc_uexp, 'wb') as tcf:
                                tcf.write(shifted_tc)
                            # Update the engine .uasset to reference the new curve
                            from parsers.uasset_clone import update_torque_curve_ref
                            if os.path.isfile(new_uasset_path):
                                update_torque_curve_ref(new_uasset_path, new_tc_name)

            # Save creation inputs so they persist for fork/re-edit
            import json as _json
            _creation_meta_path = os.path.join(engine_dir, new_name + '.creation.json')
            _fuel_type = str(data.get('fuel_type') or '').strip()
            # level_requirements_json arrives as a JSON-encoded string
            # like '{"Driver": 5, "Truck": 3}' (or '{}' for unlock-by-
            # default). Decoded here for two purposes:
            #   1) saved to the .creation.json sidecar so fork
            #      populates the widget cleanly on re-edit.
            #   2) passed to _register_engine_datatable_entry() so
            #      LevelRequirementToBuy in the Engines DataTable row
            #      tail is rewritten to match the user's selection
            #      (Phase 2). Donors with empty TMaps fall back to
            #      donor's value — see helper docstring.
            _level_requirements: Dict[str, int] = {}
            _lr_raw = str(data.get('level_requirements_json') or '').strip()
            if _lr_raw:
                try:
                    decoded = _json.loads(_lr_raw)
                    if isinstance(decoded, dict):
                        for k, v in decoded.items():
                            try:
                                _level_requirements[str(k)] = max(1, int(v))
                            except (TypeError, ValueError):
                                pass
                except Exception:
                    pass
            try:
                _json.dump({
                    'peak_torque_rpm': peak_torque_rpm,
                    'max_hp': max_hp,
                    'peak_hp_rpm': peak_hp_rpm,
                    'vehicle_type': vehicle_type or '',
                    'fuel_type': _fuel_type,
                    'level_requirements': _level_requirements,
                }, open(_creation_meta_path, 'w'))
            except Exception:
                pass  # Non-critical; fork will fall back to empty fields

            if os.path.isfile(dt_uasset_path) and os.path.isfile(dt_uexp_path):
                dt_uasset_bak = dt_uasset_path + '.bak'
                dt_uexp_bak = dt_uexp_path + '.bak'
                shutil.copy2(dt_uasset_path, dt_uasset_bak)
                shutil.copy2(dt_uexp_path, dt_uexp_bak)

                uasset_bytes = open(dt_uasset_path, 'rb').read()
                uexp_bytes = open(dt_uexp_path, 'rb').read()
                new_uasset_dt, new_uexp_dt, action = _register_engine_datatable_entry(
                    uasset_bytes, uexp_bytes, new_name, display_name, price, weight, variant,
                    update_existing=True, description=description,
                    tail_donor_name=vehicle_type,
                    level_requirements=_level_requirements,
                )
                new_uasset_dt = _patch_datatable_serial_size(new_uasset_dt, len(new_uexp_dt))

                with open(dt_uasset_path, 'wb') as f:
                    f.write(new_uasset_dt)
                with open(dt_uexp_path, 'wb') as f:
                    f.write(new_uexp_dt)

                dt_result = {
                    'dt_row': new_name,
                    'dt_price': price,
                    'dt_weight': weight,
                    'dt_description': description,
                    'dt_action': action,
                }

            from engine_validation import validate_engine_asset_pair, validate_engine_datatable
            validation_errors = validate_engine_asset_pair(new_uasset_path, new_uexp_path, expected_name=new_name)
            if os.path.isfile(dt_uasset_path) and os.path.isfile(dt_uexp_path):
                validation_errors.extend(validate_engine_datatable(dt_uasset_path, dt_uexp_path, [new_name]))
            if validation_errors:
                raise ValueError('; '.join(validation_errors[:6]))
        except Exception as exc:
            if os.path.isfile(new_uasset_path):
                os.remove(new_uasset_path)
            if os.path.isfile(new_uexp_path):
                os.remove(new_uexp_path)
            _restore_backup(dt_uasset_bak, dt_uasset_path)
            _restore_backup(dt_uexp_bak, dt_uexp_path)
            return {'error': f'Generated engine failed validation: {exc}'}

    _register_site_engine(new_name)
    result = {
        'success': True,
        'message': f'Created engine "{new_name}" from template "{template_name}"',
        'path': f'mod/Engine/{new_name}',
        'uasset_size': os.path.getsize(new_uasset_path),
        'uexp_size': os.path.getsize(new_uexp_path),
        'state_version': _current_live_state()['version'],
    }
    if template_audit is not None:
        result['template_audit'] = _template_audit_summary(template_audit)
    result.update(dt_result)
    return result


def create_tire(data: Dict) -> Dict:
    """Create a new tire from a vanilla or generated donor tire."""
    from parsers.uasset_clone import clone_uasset

    template_path = str(data.get('template_path') or '').strip()
    new_name = str(data.get('name') or '').strip()
    properties = data.get('properties', {}) or {}
    raw_display_name = str(data.get('display_name') or '').strip()
    raw_code = str(data.get('code') or '').strip()
    raw_price = data.get('price')
    raw_weight = data.get('weight')
    vehicle_type = str(data.get('vehicle_type') or '').strip() or None
    expected_version = (data.get('expected_version') or '').strip()

    if not template_path:
        return {'error': 'No template tire specified'}
    if not new_name:
        return {'error': 'No name specified for new tire'}
    if not _re.match(r'^[a-zA-Z0-9]+$', new_name):
        return {'error': 'Name must contain only letters and numbers.'}

    try:
        template_uexp, template_uasset, parser_type, source = _resolve_part_path(template_path)
    except Exception as exc:
        return {'error': str(exc)}

    if parser_type != 'tire':
        return {'error': 'Template path is not a tire'}
    if source not in ('vanilla', 'mod'):
        return {'error': 'Unsupported tire template source'}

    with open(template_uexp, 'rb') as f:
        template_uexp_data = f.read()
    try:
        tire = parse_tire(template_uexp_data)
    except Exception as exc:
        return {'error': f'Failed to parse template tire: {exc}'}

    template_name = os.path.splitext(os.path.basename(template_uexp))[0]
    preferred_group_key, _preferred_group_label = _classify_tire_group(template_name)
    try:
        new_tire_data, _property_changes = _apply_tire_property_changes(
            tire,
            properties,
            tire_field_catalog=_load_tire_field_catalog(),
            preferred_group_key=preferred_group_key,
        )
    except Exception as exc:
        return {'error': f'Failed to prepare tire properties: {exc}'}

    detail = get_part_detail(template_path)
    if detail.get('error'):
        return {'error': detail['error']}
    donor_shop = detail.get('metadata', {}).get('shop', {}) or {}
    donor_row = _lookup_raw_tire_vehicleparts_row(
        source,
        detail.get('asset_info', {}).get('asset_name', ''),
        os.path.splitext(os.path.basename(template_uasset))[0],
    )
    if donor_row is None:
        return {'error': f'Template "{template_path}" has no usable VehicleParts0 donor row'}

    # Override donor row with user-selected vehicle type if specified
    if vehicle_type:
        vt_donor = _lookup_tire_vehicleparts_row_by_name(vehicle_type)
        if vt_donor is not None:
            donor_row = vt_donor
        else:
            logger.warning("Vehicle type donor '%s' not found, using template donor.", vehicle_type)

    display_name = raw_display_name or donor_shop.get('display_name') or new_name
    code = raw_code or donor_shop.get('code') or ''
    try:
        price = max(0, int(float(raw_price)))
    except (TypeError, ValueError):
        price = int(donor_shop.get('price', 500))
    try:
        weight = max(0.0, float(raw_weight))
    except (TypeError, ValueError):
        weight = float(donor_shop.get('weight', 10.0))

    os.makedirs(MOD_TIRE_DIR, exist_ok=True)
    new_uasset_path = os.path.join(MOD_TIRE_DIR, new_name + '.uasset')
    new_uexp_path = os.path.join(MOD_TIRE_DIR, new_name + '.uexp')

    with MOD_WRITE_LOCK:
        live_conflict = _check_live_version(expected_version)
        if live_conflict:
            return {
                'error': 'Live data changed. Reload and try again.',
                'conflict': True,
                'state_version': live_conflict['version'],
            }

        if os.path.isfile(new_uasset_path) or os.path.isfile(new_uexp_path):
            return {'error': f'Tire "{new_name}" already exists'}

        try:
            vp_uasset_path, vp_uexp_path = _ensure_mod_vehicleparts0_files()
        except Exception as exc:
            return {'error': f'Failed to prepare VehicleParts0: {exc}'}

        vp_uasset_bak = vp_uasset_path + '.bak'
        vp_uexp_bak = vp_uexp_path + '.bak'
        shutil.copy2(vp_uasset_path, vp_uasset_bak)
        shutil.copy2(vp_uexp_path, vp_uexp_bak)

        try:
            clone_uasset(template_uasset, new_name, new_uasset_path)
            with open(new_uexp_path, 'wb') as f:
                f.write(new_tire_data)
            with open(new_uasset_path, 'rb') as f:
                new_uasset_data = f.read()
            patched_uasset = _patch_uasset_serial_size(new_uasset_data, len(new_tire_data))
            if patched_uasset != new_uasset_data:
                with open(new_uasset_path, 'wb') as f:
                    f.write(patched_uasset)

            vp_ua = open(vp_uasset_path, 'rb').read()
            vp_ue = open(vp_uexp_path, 'rb').read()
            vp_ua, vp_ue, action = _register_tire_vehicleparts_entry(
                vp_ua,
                vp_ue,
                new_name,
                display_name=display_name,
                code=code,
                price=price,
                weight=weight,
                donor_row=donor_row,
                update_existing=True,
            )
            vp_ua = _patch_uasset_serial_size(vp_ua, len(vp_ue))
            with open(vp_uasset_path, 'wb') as f:
                f.write(vp_ua)
            with open(vp_uexp_path, 'wb') as f:
                f.write(vp_ue)
            _invalidate_vehicleparts0_catalog(MOD_VEHICLEPARTS0_BASE)

            _validate_tire_generation(new_uasset_path, new_uexp_path, new_name, vp_uasset_path, vp_uexp_path)

            # Save creation inputs so they persist for re-inspection
            import json as _json
            _creation_meta_path = os.path.join(MOD_TIRE_DIR, new_name + '.creation.json')
            try:
                _json.dump({
                    'vehicle_type': vehicle_type or '',
                    'template_path': template_path,
                }, open(_creation_meta_path, 'w'))
            except Exception:
                pass  # Non-critical

        except Exception as exc:
            if os.path.isfile(new_uasset_path):
                os.remove(new_uasset_path)
            if os.path.isfile(new_uexp_path):
                os.remove(new_uexp_path)
            _restore_backup(vp_uasset_bak, vp_uasset_path)
            _restore_backup(vp_uexp_bak, vp_uexp_path)
            _invalidate_vehicleparts0_catalog(MOD_VEHICLEPARTS0_BASE)
            return {'error': f'Generated tire failed validation: {exc}'}

    _register_site_tire(new_name)
    return {
        'success': True,
        'message': f'Created tire "{new_name}" from template "{os.path.basename(template_uexp)}"',
        'path': f'mod/Tire/{new_name}',
        'uasset_size': os.path.getsize(new_uasset_path),
        'uexp_size': os.path.getsize(new_uexp_path),
        'dt_row': new_name,
        'dt_price': price,
        'dt_weight': weight,
        'dt_action': action,
        'state_version': _current_live_state()['version'],
    }


def delete_tire(data: Dict) -> Dict:
    """Delete a generated mod tire and prune its VehicleParts0 row."""
    part_path = (data.get('path') or '').strip()
    expected_version = (data.get('expected_version') or '').strip()
    if not part_path:
        return {'error': 'No tire path specified'}

    try:
        uexp_path, uasset_path, parser_type, source = _resolve_part_path(part_path)
    except Exception as exc:
        return {'error': str(exc)}

    if source != 'mod' or parser_type != 'tire':
        return {'error': 'Only generated mod tires can be deleted from this site.'}

    tire_name = os.path.splitext(os.path.basename(uexp_path))[0]
    if not _is_site_tire(tire_name):
        return {'error': 'Only user-generated tires can be deleted from this site.'}

    with MOD_WRITE_LOCK:
        live_conflict = _check_live_version(expected_version)
        if live_conflict:
            return {
                'error': 'Live data changed. Reload and try again.',
                'conflict': True,
                'state_version': live_conflict['version'],
            }

        missing = [path for path in (uasset_path, uexp_path) if not os.path.isfile(path)]
        if missing:
            return {'error': f'Tire files not found for {tire_name}'}

        try:
            vp_uasset_path, vp_uexp_path = _ensure_mod_vehicleparts0_files()
        except Exception as exc:
            return {'error': f'Failed to prepare VehicleParts0: {exc}'}

        os.makedirs(BACKUP_DIR, exist_ok=True)
        rollback_uasset = os.path.join(BACKUP_DIR, f'delete_{tire_name}.uasset.current.bak')
        rollback_uexp = os.path.join(BACKUP_DIR, f'delete_{tire_name}.uexp.current.bak')
        rollback_vp_ua = os.path.join(BACKUP_DIR, 'delete_VehicleParts0_dt.uasset.current.bak')
        rollback_vp_ue = os.path.join(BACKUP_DIR, 'delete_VehicleParts0_dt.uexp.current.bak')
        shutil.copy2(uasset_path, rollback_uasset)
        shutil.copy2(uexp_path, rollback_uexp)
        shutil.copy2(vp_uasset_path, rollback_vp_ua)
        shutil.copy2(vp_uexp_path, rollback_vp_ue)

        try:
            for path in (uasset_path, uexp_path):
                os.remove(path)
            # Clean up creation metadata if present
            creation_meta = uexp_path.replace('.uexp', '.creation.json')
            if os.path.isfile(creation_meta):
                os.remove(creation_meta)
            vp_ua = open(vp_uasset_path, 'rb').read()
            vp_ue = open(vp_uexp_path, 'rb').read()
            vp_ue, removed_rows = _remove_tire_vehicleparts_entries(vp_ua, vp_ue, tire_name)
            vp_ua = _patch_uasset_serial_size(vp_ua, len(vp_ue))
            with open(vp_uasset_path, 'wb') as f:
                f.write(vp_ua)
            with open(vp_uexp_path, 'wb') as f:
                f.write(vp_ue)
            _invalidate_vehicleparts0_catalog(MOD_VEHICLEPARTS0_BASE)

            from parsers.uexp_vehicleparts_dt import build_vehicleparts_catalog
            catalog = build_vehicleparts_catalog(vp_ua, vp_ue)
            if catalog.get('rows_by_asset_object', {}).get(tire_name):
                raise ValueError(f'VehicleParts0 still references {tire_name}')
        except Exception as exc:
            _restore_backup(rollback_uasset, uasset_path)
            _restore_backup(rollback_uexp, uexp_path)
            _restore_backup(rollback_vp_ua, vp_uasset_path)
            _restore_backup(rollback_vp_ue, vp_uexp_path)
            _invalidate_vehicleparts0_catalog(MOD_VEHICLEPARTS0_BASE)
            return {'error': f'Failed to delete tire: {exc}'}

    _unregister_site_tire(tire_name)
    return {
        'success': True,
        'deleted': tire_name,
        'removed_rows': removed_rows,
        'message': f'Deleted {tire_name}',
        'state_version': _current_live_state()['version'],
    }

