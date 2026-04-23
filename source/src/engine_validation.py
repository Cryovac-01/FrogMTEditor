"""Validation helpers for generated engine assets and shop DataTable rows."""
from __future__ import annotations

import math
import os
import struct
from typing import Any, Dict, List, Optional

from parsers.uasset_clone import _parse_engine_sound_ref, _parse_name_table, _read_fstring, verify_clone
from parsers.uasset_engines_dt import get_fname_index
from parsers.uexp_engine import is_generator_safe_layout, parse_engine, serialize_engine
from parsers.uexp_engines_dt import find_row_by_fname_idx, read_row


def _parse_name_lookup(uasset_data: bytes) -> tuple[dict[int, str], dict[str, int]]:
    """Return FName index/name lookups for a .uasset name table."""
    _folder_text, folder_bytes = _read_fstring(uasset_data, 32)
    folder_end = 32 + folder_bytes
    name_count = struct.unpack_from('<i', uasset_data, folder_end + 4)[0]
    name_offset = struct.unpack_from('<i', uasset_data, folder_end + 8)[0]
    entries, _ = _parse_name_table(uasset_data, name_offset, name_count)
    idx_to_name = {i: entry['text'] for i, entry in enumerate(entries)}
    name_to_idx = {entry['text']: i for i, entry in enumerate(entries)}
    return idx_to_name, name_to_idx


def _find_engine_import_ref(uasset_data: bytes, engine_name: str) -> Optional[int]:
    """Return the negative import ID for a row's MHEngineDataAsset import."""
    idx_to_name, name_to_idx = _parse_name_lookup(uasset_data)
    name_fidx = name_to_idx.get(engine_name)
    if name_fidx is None:
        return None

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


def validate_engine_asset_pair(uasset_path: str, uexp_path: str,
                               expected_name: str | None = None) -> List[str]:
    """Return validation errors for a generated engine asset pair."""
    errors: List[str] = []
    if not os.path.isfile(uasset_path):
        return [f'Missing uasset: {uasset_path}']
    if not os.path.isfile(uexp_path):
        return [f'Missing uexp: {uexp_path}']

    name = expected_name or os.path.splitext(os.path.basename(uexp_path))[0]
    verify = verify_clone('', uasset_path)
    if not verify['valid']:
        errors.extend(f'{name}: {msg}' for msg in verify['errors'])

    uexp_data = open(uexp_path, 'rb').read()
    try:
        engine = parse_engine(uexp_data)
    except Exception as exc:
        return [f'{name}: parse failed ({exc})']

    roundtrip = serialize_engine(engine)
    if len(roundtrip) != len(uexp_data):
        errors.append(
            f'{name}: serialize size mismatch ({len(uexp_data)} -> {len(roundtrip)}) '
            f'for layout {engine.variant.value}/{engine.format_hint or "default"}'
        )
    if not is_generator_safe_layout(engine):
        errors.append(
            f'{name}: unsupported generator layout '
            f'{engine.variant.value}/{engine.format_hint or "default"}/{len(uexp_data)}'
        )
    if any(ref >= 0 for ref in engine.tail_imports):
        errors.append(f'{name}: non-negative tail import refs {engine.tail_imports}')

    raw_uasset = open(uasset_path, 'rb').read()
    folder_text, folder_bytes = _read_fstring(raw_uasset, 32)
    if not folder_text.endswith('/' + name):
        errors.append(f'{name}: folder path mismatch ({folder_text})')

    folder_end = 32 + folder_bytes
    export_offset = struct.unpack_from('<i', raw_uasset, folder_end + 32)[0]
    if export_offset > 0 and export_offset + 36 + 8 <= len(raw_uasset):
        serial_size = struct.unpack_from('<q', raw_uasset, export_offset + 28)[0]
        expected_serial = len(uexp_data) - 4
        if serial_size != expected_serial:
            errors.append(f'{name}: SerialSize {serial_size} != expected {expected_serial}')

    idx_to_name, name_to_idx = _parse_name_lookup(raw_uasset)
    if name not in name_to_idx:
        errors.append(f'{name}: short asset name missing from uasset name table')
    full_path = f'/Game/Cars/Parts/Engine/{name}'
    if full_path not in name_to_idx:
        errors.append(f'{name}: full asset path missing from uasset name table')

    sound_paths = []
    for text in idx_to_name.values():
        info = _parse_engine_sound_ref(text)
        if not info:
            continue
        sound_paths.append((text, info))
    for text, info in sound_paths:
        object_name = info.get('object_name')
        if object_name and object_name not in name_to_idx:
            errors.append(f'{name}: sound object "{object_name}" missing for path {text}')

    return errors


def validate_engine_datatable(dt_uasset_path: str, dt_uexp_path: str,
                              engine_names: List[str]) -> List[str]:
    """Return validation errors for engine shop registration."""
    errors: List[str] = []
    if not os.path.isfile(dt_uasset_path) or not os.path.isfile(dt_uexp_path):
        return ['Engines DataTable files are missing']

    dt_ua = open(dt_uasset_path, 'rb').read()
    dt_ue = open(dt_uexp_path, 'rb').read()

    for engine_name in sorted(engine_names):
        fname_idx = get_fname_index(dt_ua, engine_name)
        if fname_idx < 0:
            errors.append(f'{engine_name}: missing DataTable FName entry')
            continue

        row = find_row_by_fname_idx(dt_ue, fname_idx)
        if row is None:
            errors.append(f'{engine_name}: missing DataTable row')
            continue

        row_data = read_row(dt_ue, fname_idx)
        if not row_data or not row_data.get('display_name'):
            errors.append(f'{engine_name}: unreadable DataTable row payload')

        engine_ref = _find_engine_import_ref(dt_ua, engine_name)
        if engine_ref is None:
            errors.append(f'{engine_name}: missing MHEngineDataAsset import in DataTable')
            continue

        tail = dt_ue[row['tail_start']:row['row_end']]
        if struct.pack('<i', engine_ref) not in tail:
            errors.append(f'{engine_name}: DataTable row tail is missing import ref {engine_ref}')

    return errors


def _approx_equal(actual: Any, expected: Any, abs_tol: float = 1e-6) -> bool:
    if actual is None or expected is None:
        return actual is expected
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return math.isclose(float(actual), float(expected), rel_tol=0.0, abs_tol=abs_tol)
    return actual == expected


def _matches_signature(properties: Dict[str, Any], expected: Dict[str, Any]) -> bool:
    for key, expected_value in expected.items():
        if key not in properties:
            return False
        if not _approx_equal(properties.get(key), expected_value):
            return False
    return True


def audit_engine_value_consistency(
    engine_dir: str,
    standard_baseline: Optional[Dict[str, float]] = None,
    required_standard_heating_power: Optional[float] = None,
    forbidden_standard_format_hint: Optional[str] = None,
    compact_baseline: Optional[Dict[str, float]] = None,
    compact_outlier_signature: Optional[Dict[str, float]] = None,
    bike_baseline: Optional[Dict[str, float]] = None,
    diesel_baseline: Optional[Dict[str, float]] = None,
    ev_baseline: Optional[Dict[str, float]] = None,
    min_fuel_consumption: Optional[float] = None,
) -> Dict[str, Any]:
    """Audit engine properties for known problematic template inheritance."""
    if not os.path.isdir(engine_dir):
        return {
            'valid': False,
            'checked': 0,
            'errors': [f'Engine directory not found: {engine_dir}'],
            'warnings': [],
            'legacy_bike_names': [],
        }

    errors: List[str] = []
    warnings: List[str] = []
    legacy_bike_names: List[str] = []
    checked = 0

    for fname in sorted(os.listdir(engine_dir)):
        if not fname.endswith('.uexp'):
            continue
        path = os.path.join(engine_dir, fname)
        if not os.path.isfile(path):
            continue

        name = os.path.splitext(fname)[0]
        try:
            engine = parse_engine(open(path, 'rb').read())
        except Exception as exc:
            errors.append(f'{name}: audit parse failed ({exc})')
            continue

        checked += 1
        variant = engine.variant.value
        fuel_consumption = engine.properties.get('FuelConsumption')
        if min_fuel_consumption is not None and isinstance(fuel_consumption, (int, float)):
            if float(fuel_consumption) <= float(min_fuel_consumption):
                errors.append(
                    f'{name}: FuelConsumption {float(fuel_consumption):.6g} is at or below safe minimum '
                    f'{float(min_fuel_consumption):.6g}'
                )
                continue

        if variant == 'ice_standard':
            if forbidden_standard_format_hint and engine.format_hint == forbidden_standard_format_hint:
                errors.append(f'{name}: standard engine still uses retired layout {forbidden_standard_format_hint}')
                continue
            if required_standard_heating_power is not None:
                if 'HeatingPower' not in engine.properties:
                    errors.append(f'{name}: standard engine is missing explicit HeatingPower')
                    continue
                if not _approx_equal(engine.properties.get('HeatingPower'), required_standard_heating_power):
                    errors.append(
                        f'{name}: HeatingPower {float(engine.properties.get("HeatingPower", 0.0)):.6g} '
                        f'!= expected {float(required_standard_heating_power):.6g}'
                    )
                    continue
            if standard_baseline:
                mismatches = [
                    key for key, expected in standard_baseline.items()
                    if key in engine.properties and not _approx_equal(engine.properties.get(key), expected)
                ]
                if mismatches:
                    joined = ', '.join(mismatches[:4])
                    extra = '' if len(mismatches) <= 4 else ', ...'
                    warnings.append(
                        f'{name}: standard baseline differs from expected values for {joined}{extra}'
                    )
        elif variant == 'ice_compact':
            idle = engine.properties.get('IdleThrottle')
            if idle is None:
                errors.append(f'{name}: compact engine is missing IdleThrottle')
                continue
            if float(idle) > 1.0:
                errors.append(f'{name}: compact IdleThrottle {idle:.6g} exceeds safe threshold 1.0')
                continue
            if compact_outlier_signature and _matches_signature(engine.properties, compact_outlier_signature):
                errors.append(f'{name}: compact engine still matches the retired V6Sport outlier baseline')
                continue
            if compact_baseline:
                mismatches = [
                    key for key, expected in compact_baseline.items()
                    if key in engine.properties and not _approx_equal(engine.properties.get(key), expected)
                ]
                if mismatches:
                    joined = ', '.join(mismatches[:4])
                    extra = '' if len(mismatches) <= 4 else ', ...'
                    warnings.append(
                        f'{name}: compact baseline differs from expected values for {joined}{extra}'
                    )
        elif variant == 'bike':
            missing = [key for key in ('IdleThrottle', 'StarterRPM') if key not in engine.properties]
            if missing:
                legacy_bike_names.append(name)
                errors.append(f'{name}: bike uses legacy layout missing {", ".join(missing)}')
                continue
            if bike_baseline:
                mismatches = [
                    key for key, expected in bike_baseline.items()
                    if key in engine.properties and not _approx_equal(engine.properties.get(key), expected)
                ]
                if mismatches:
                    joined = ', '.join(mismatches[:4])
                    extra = '' if len(mismatches) <= 4 else ', ...'
                    warnings.append(
                        f'{name}: bike baseline differs from expected values for {joined}{extra}'
                    )
        elif variant == 'diesel_hd':
            if diesel_baseline:
                mismatches = [
                    key for key, expected in diesel_baseline.items()
                    if key in engine.properties and not _approx_equal(engine.properties.get(key), expected)
                ]
                if mismatches:
                    joined = ', '.join(mismatches[:4])
                    extra = '' if len(mismatches) <= 4 else ', ...'
                    warnings.append(
                        f'{name}: diesel baseline differs from expected values for {joined}{extra}'
                    )
        elif variant == 'ev':
            if ev_baseline:
                mismatches = [
                    key for key, expected in ev_baseline.items()
                    if key in engine.properties and not _approx_equal(engine.properties.get(key), expected)
                ]
                if mismatches:
                    joined = ', '.join(mismatches[:4])
                    extra = '' if len(mismatches) <= 4 else ', ...'
                    warnings.append(
                        f'{name}: EV baseline differs from expected values for {joined}{extra}'
                    )

    return {
        'valid': not errors,
        'checked': checked,
        'errors': errors,
        'warnings': warnings,
        'legacy_bike_names': legacy_bike_names,
    }


def validate_engine_generation_tree(mt_root: str) -> Dict[str, Any]:
    """Validate a staged MotorTown tree before packing or saving."""
    engine_dir = os.path.join(mt_root, 'Content', 'Cars', 'Parts', 'Engine')
    dt_uasset_path = os.path.join(mt_root, 'Content', 'DataAsset', 'VehicleParts', 'Engines.uasset')
    dt_uexp_path = os.path.join(mt_root, 'Content', 'DataAsset', 'VehicleParts', 'Engines.uexp')

    # If there are no engine files in the mod tree, skip validation.
    # This is normal when the mod only contains transmissions, economy, etc.
    if not os.path.isdir(engine_dir):
        return {'valid': True, 'engine_names': [], 'errors': []}

    engine_names = sorted(
        os.path.splitext(fname)[0]
        for fname in os.listdir(engine_dir)
        if fname.endswith('.uexp') and os.path.isfile(os.path.join(engine_dir, fname))
    )

    errors: List[str] = []
    for engine_name in engine_names:
        uasset_path = os.path.join(engine_dir, engine_name + '.uasset')
        uexp_path = os.path.join(engine_dir, engine_name + '.uexp')
        errors.extend(validate_engine_asset_pair(uasset_path, uexp_path, expected_name=engine_name))

    errors.extend(validate_engine_datatable(dt_uasset_path, dt_uexp_path, engine_names))
    return {'valid': not errors, 'engine_names': engine_names, 'errors': errors}
