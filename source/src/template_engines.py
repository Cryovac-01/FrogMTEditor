"""Helpers for classifying template engines by shop order and vanilla donors."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

from parsers.uexp_engine import parse_engine, detect_variant


PROFILE_DONOR_MAP = {
    'v8': 'Ferrari_275_V12_400HP',
    'v12': 'Ferrari_275_V12_400HP',
    'i4': 'I4Sport_150HP',
    'v6': 'V6Sport_400HP',
    'truck': 'HeavyDuty_440HP',
    'electric': 'Electric_300HP',
    'bike_small': 'Bike_i4_100HP',
    'bike_twin': 'Bike_i4_100HP',
    'bike_i4': 'Bike_i4_100HP',
}

PROFILE_SOUND_DIR_MAP = {
    'v8': 'V8',
    'v12': 'v12',
    'bike_small': 'I2_350cc',
    'bike_twin': 'Twin_650B',
    'bike_i4': 'I4',
}

GAS_TRUCK_NAMES = {
    '81bb',
    'L86',
}

SOUND_PROFILE_OVERRIDES = {
    '13b': 'v8',
    '26b': 'v12',
    'bugattiW16': 'v6',
    'bmw_k1600': 'bike_i4',
    'triumph_daytona660': 'bike_i4',
    'triumph_rocket3': 'bike_i4',
    'triumph_speed_triple_1200': 'bike_i4',
    'yamaha_tracer9': 'bike_i4',
}

INTERNAL_ASSET_NAME_OVERRIDES = {
    'indian_scout_1250': 'indianscout1250',
    'honda_cbr600rr_2024': 'hondacbr600rr2024',
}

ASSET_NAME_TO_TEMPLATE_NAME = {
    asset_name: template_name
    for template_name, asset_name in INTERNAL_ASSET_NAME_OVERRIDES.items()
}

SORT_GROUP_ORDER = {
    'gas_bike': 0,
    'gas_car': 1,
    'gas_truck': 2,
    'diesel': 3,
    'ev': 4,
}

PAREN_SUFFIX_RE = re.compile(r'^(?P<title>.+?)\s*(?P<subtitle>\([^()]+\))$')
PURE_YEAR_NOTE_RE = re.compile(r'^\d{4}(?:[-+]\d{0,4})?$|^\d{4}-\d{2}$|^\d{4}-\d{4}$|^\d{4}\+$')
PURE_HP_NOTE_RE = re.compile(r'^\d+(?:\.\d+)?\s*HP$', re.IGNORECASE)

NON_MODEL_SUBTITLE_TERMS = {
    'custom',
    'track',
    'tuned',
    'stock',
    'race spec',
    'e85',
    'on-highway',
    'long-haul',
    'heavy-haul truck',
    'heavy mining',
    'ultra-class mining',
    'industrial',
    'industrial/marine',
    'industrial/mining',
    'marine/industrial',
    'marine/mining',
    'marine/offshore',
    'mining/industrial',
    'mining/oil & gas',
    'oil & gas/marine',
    'fast vessel',
    'large vessel',
    'roadster',
    'sport tourer',
    'heritage cruiser',
    'supersport',
    'supernaked',
    'hypernaked',
    'adventure',
    'classic',
    'middleweight supersport',
    'entry supersport',
}


@dataclass(frozen=True)
class TemplateSpec:
    name: str
    asset_name: str
    display_name: str
    shop_title: str
    shop_subtitle: str
    variant: str
    fuel_type: int
    hp: float
    torque_nm: float
    max_rpm: int
    sound_profile: str
    donor_name: str
    sound_dir: str
    sort_group: str


_TEMPLATE_SPECS_CACHE: dict[str, tuple[tuple[int, float], tuple[TemplateSpec, ...]]] = {}


def _normalize_layout(title: str) -> str:
    low = f' {title.lower()} '
    low = low.replace('inline-4', ' i4 ')
    low = low.replace('inline-6', ' i6 ')
    low = low.replace('three-cylinder', ' i3 ')
    low = low.replace('four-cylinder', ' i4 ')
    low = low.replace('five-cylinder', ' i5 ')
    low = low.replace('six-cylinder', ' i6 ')
    low = low.replace('flat-six', ' flat-6 ')
    low = low.replace('flat six', ' flat-6 ')
    low = low.replace('flat-four', ' flat-4 ')
    low = low.replace('flat four', ' flat-4 ')
    low = low.replace('parallel-twin', ' twin ')
    low = low.replace('v-twin', ' twin ')
    low = low.replace('l-twin', ' twin ')
    low = low.replace('boxer', ' boxer ')
    low = low.replace('triple', ' i3 ')
    return low


def classify_sound_profile(name: str, display_name: str, variant: str, hp: float) -> str:
    override = SOUND_PROFILE_OVERRIDES.get(name)
    if override:
        return override

    low = _normalize_layout(display_name)

    if variant == 'ev':
        return 'electric'
    if variant == 'diesel_hd':
        return 'truck'
    if variant == 'bike':
        if ' single ' in low or hp <= 60:
            return 'bike_small'
        if any(token in low for token in (' i4 ', ' v4 ', ' i3 ', ' i6 ', ' supercharged ')):
            return 'bike_i4'
        return 'bike_twin'
    if variant == 'ice_compact':
        if any(token in low for token in (' rotary ', ' i3 ', ' i4 ', ' flat-4 ', ' boxer ')):
            return 'i4'
        return 'v6'
    if variant == 'ice_standard':
        if any(token in low for token in (' quad-rotor ', ' 4-rotor ', ' v10 ', ' v12 ', ' w12 ', ' w16 ', ' v16 ')):
            return 'v12'
        return 'v8'
    return 'v8'


def classify_sort_group(name: str, variant: str, fuel_type: int) -> str:
    if fuel_type == 3 or variant == 'ev':
        return 'ev'
    if fuel_type == 2 or variant == 'diesel_hd':
        return 'diesel'
    if variant == 'bike':
        return 'gas_bike'
    if name in GAS_TRUCK_NAMES:
        return 'gas_truck'
    return 'gas_car'


def sort_key(spec: TemplateSpec) -> tuple[int, float, str]:
    return (SORT_GROUP_ORDER[spec.sort_group], spec.hp, spec.shop_title.lower())


def split_shop_display(display_name: str) -> tuple[str, str]:
    """Split a display name into a main title and optional subtitle line."""
    match = PAREN_SUFFIX_RE.match(display_name.strip())
    if not match:
        return display_name.strip(), ''
    title = match.group('title').strip()
    inner = match.group('subtitle')[1:-1].strip()
    return title, inner


def asset_name_for_template(template_name: str) -> str:
    override = INTERNAL_ASSET_NAME_OVERRIDES.get(template_name)
    if override:
        return override
    if '_' in template_name:
        return template_name.replace('_', '')
    return template_name


def canonical_template_name(engine_name: str, display_names: dict[str, str] | None = None) -> str:
    if display_names and engine_name not in display_names:
        for template_name in display_names:
            if asset_name_for_template(template_name) == engine_name:
                return template_name
    return ASSET_NAME_TO_TEMPLATE_NAME.get(engine_name, engine_name)


def display_name_for_engine(engine_name: str, display_names: dict[str, str]) -> str:
    canonical_name = canonical_template_name(engine_name, display_names)
    return display_names.get(canonical_name, engine_name.replace('_', ' '))


def _template_file_stamp(templates_dir: str) -> tuple[list[str], tuple[int, float]]:
    files = sorted(
        os.path.join(templates_dir, fname)
        for fname in os.listdir(templates_dir)
        if fname.endswith('.uexp')
    )
    latest_mtime = max((os.path.getmtime(path) for path in files), default=0.0)
    return files, (len(files), latest_mtime)


def load_template_specs(templates_dir: str, display_names: dict[str, str]) -> list[TemplateSpec]:
    cache_key = os.path.abspath(templates_dir)
    files, stamp = _template_file_stamp(templates_dir)
    cached = _TEMPLATE_SPECS_CACHE.get(cache_key)
    if cached and cached[0] == stamp:
        return list(cached[1])

    specs: list[TemplateSpec] = []
    for path in files:
        name = os.path.splitext(os.path.basename(path))[0]
        data = open(path, 'rb').read()
        engine = parse_engine(data)
        variant = detect_variant(data).value
        display_name = display_names.get(name, name.replace('_', ' '))
        shop_title, shop_subtitle = split_shop_display(display_name)
        fuel_type = int(engine.properties.get('FuelType') or 1)
        hp = round(engine.estimated_hp(), 1)
        torque_nm = round(engine.max_torque_nm, 1)
        max_rpm = int(engine.properties.get('MaxRPM') or 0)
        sound_profile = classify_sound_profile(name, display_name, variant, hp)
        specs.append(
            TemplateSpec(
                name=name,
                asset_name=asset_name_for_template(name),
                display_name=display_name,
                shop_title=shop_title,
                shop_subtitle=shop_subtitle,
                variant=variant,
                fuel_type=fuel_type,
                hp=hp,
                torque_nm=torque_nm,
                max_rpm=max_rpm,
                sound_profile=sound_profile,
                donor_name=PROFILE_DONOR_MAP[sound_profile],
                sound_dir=PROFILE_SOUND_DIR_MAP.get(sound_profile, ''),
                sort_group=classify_sort_group(name, variant, fuel_type),
            )
        )
    _TEMPLATE_SPECS_CACHE[cache_key] = (stamp, tuple(specs))
    return specs
