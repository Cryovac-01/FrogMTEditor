"""
Rebuild template engine .uasset files from vanilla Motor Town donors.

Each template has a .uexp with valid engine parameters. This module creates
fresh .uassets by cloning vanilla base-game donors, ensuring all import
references point to assets that ship with Motor Town.
"""
import os
import struct
from parsers.uexp_engine import (
    detect_variant,
    is_generator_safe_layout,
    parse_engine,
    serialize_engine,
)
from parsers.uasset_clone import clone_uasset, _read_fstring


# Default vanilla donor engine for each variant (must exist in data/vanilla/Engine/)
DEFAULT_DONOR_MAP = {
    'ice_standard': 'FordSmalBlock302_V8_5L_320HP',
    'ice_compact':  'I4Sport_150HP',
    'diesel_hd':    'HeavyDuty_440HP',
    'bike':         'Bike_i4_100HP',
    'ev':           'Electric_300HP',
}

# Structure donors define the binary layout and any inherited baseline fields
# that the template generator does not explicitly overwrite.
STRUCTURE_DONOR_MAP = {
    'ice_standard': 'H2_30HP',
    'ice_compact':  'I4Sport_150HP',
    'diesel_hd':    'HeavyDuty_440HP',
    'bike':         'Bike_i4_100HP',
    'ev':           'Electric_300HP',
}

# TorqueCurve to assign per variant
TC_MAP = {
    'ice_standard': 'TorqueCurve_SmallBlock',
    'ice_compact':  'TorqueCurve_DOHC',
    'diesel_hd':    'TorqueCurve_DieselTruck',
    'bike':         'TorqueCurve_Bike_i4',
    'ev':           'TorqueCurve_ElectricMotor_HighPerf',
}

KEEP_DONOR_TORQUE_CURVE = {
    'Bike_30HP',
    'Bike_50HP',
    'Bike_100HP',
}
SAFE_COMPACT_STRUCTURE_DONORS = (
    ('I4_50HP', 51.5),
    ('I4_90HP', 90.2),
    ('I4Sport_150HP', 149.3),
    ('FordSmalBlock302_V8_5L_180HP', 180.3),
    ('FordSmalBlock302_V8_5L_240HP', 238.3),
)


def resolve_structure_donor_name(variant: str, donor_name: str | None = None,
                                 hp: float | None = None) -> str:
    """Return the safe vanilla donor to use for .uexp structure generation."""
    resolved = donor_name or STRUCTURE_DONOR_MAP.get(variant) or DEFAULT_DONOR_MAP.get(variant)
    if variant == 'ice_standard':
        # Use the modern H2 layout so HeatingPower is serialized explicitly
        # instead of falling back to the legacy V8 omission strategy.
        return STRUCTURE_DONOR_MAP['ice_standard']
    if variant in ('diesel_hd', 'ev', 'bike'):
        baseline = STRUCTURE_DONOR_MAP.get(variant)
        if not baseline:
            raise ValueError(f'No structure donor for variant: {variant}')
        return baseline
    if variant != 'ice_compact':
        if not resolved:
            raise ValueError(f'No vanilla donor for variant: {variant}')
        return resolved
    if hp is None:
        return 'I4Sport_150HP'
    return min(
        SAFE_COMPACT_STRUCTURE_DONORS,
        key=lambda item: (abs(float(item[1]) - float(hp)), item[0]),
    )[0]


def _patch_engine_serial_size(uasset_data: bytes, uexp_size: int) -> bytes:
    """Patch SerialSize in an engine .uasset to match the actual .uexp size.

    UE reads exactly SerialSize bytes from the .uexp. The relationship is:
    SerialSize = uexp_file_size - 4  (4 bytes of UObject terminator overhead)
    """
    data = bytearray(uasset_data)
    _, fb = _read_fstring(bytes(data), 32)
    fe = 32 + fb
    export_count = struct.unpack_from('<i', data, fe + 28)[0]
    export_offset = struct.unpack_from('<i', data, fe + 32)[0]
    if export_count <= 0 or export_offset <= 0:
        return bytes(data)
    # SerialSize at byte 28 of the export entry
    new_serial_size = uexp_size - 4
    struct.pack_into('<q', data, export_offset + 28, new_serial_size)
    return bytes(data)


def rebuild_template(template_name: str, variant: str,
                     vanilla_dir: str, output_dir: str,
                     uexp_size: int, donor_name: str | None = None,
                     sound_dir: str | None = None) -> str:
    """Clone a vanilla donor .uasset for a template engine.

    Args:
        template_name: Engine name (e.g. 'honda_k20c1')
        variant: Engine variant string ('ice_standard', 'ice_compact', etc.)
        vanilla_dir: Path to data/vanilla/Engine/ with donor .uassets
        output_dir: Where to write the cloned .uasset
        uexp_size: Size of the template's .uexp file
        donor_name: Optional explicit donor asset name. Falls back to the
                    default donor for *variant* when omitted.

    Returns:
        Path to the created .uasset, or raises on error.
    """
    donor_name = donor_name or DEFAULT_DONOR_MAP.get(variant)
    if not donor_name:
        raise ValueError(f'No vanilla donor for variant: {variant}')

    donor_path = os.path.join(vanilla_dir, donor_name + '.uasset')
    if not os.path.isfile(donor_path):
        raise FileNotFoundError(f'Vanilla donor not found: {donor_path}')

    tc_name = None if donor_name in KEEP_DONOR_TORQUE_CURVE else TC_MAP.get(variant)
    output_path = os.path.join(output_dir, template_name + '.uasset')

    # Clone vanilla donor → new engine name, with correct TorqueCurve
    # Sound paths stay as vanilla (V8, Truck, Bike, etc.) — no sound_dir override
    clone_uasset(donor_path, template_name, output_path,
                 torque_curve_name=tc_name,
                 sound_dir=sound_dir)

    # Patch SerialSize to match the template's .uexp
    cloned = open(output_path, 'rb').read()
    patched = _patch_engine_serial_size(cloned, uexp_size)
    with open(output_path, 'wb') as f:
        f.write(patched)

    return output_path


def build_donor_backed_uexp_bytes(template_data: bytes, donor_data: bytes) -> bytes:
    """Return a vanilla-format .uexp using donor structure and template values."""
    template_engine = parse_engine(template_data)
    donor_engine = parse_engine(donor_data)

    if not is_generator_safe_layout(donor_engine):
        raise ValueError(
            f'Unsupported donor layout: '
            f'{donor_engine.variant.value}/{donor_engine.format_hint or "default"}/{len(donor_data)}'
        )

    for prop_name in donor_engine.properties:
        if prop_name in template_engine.properties:
            donor_engine.properties[prop_name] = template_engine.properties[prop_name]

    output = serialize_engine(donor_engine)
    if len(output) != len(donor_data):
        raise ValueError(
            f'Donor-backed serialization mismatch: {len(donor_data)} -> {len(output)} '
            f'for {donor_engine.variant.value}/{donor_engine.format_hint or "default"}'
        )

    rebuilt_engine = parse_engine(output)
    if not is_generator_safe_layout(rebuilt_engine):
        raise ValueError(
            f'Rebuilt engine layout is not generator-safe: '
            f'{rebuilt_engine.variant.value}/{rebuilt_engine.format_hint or "default"}/{len(output)}'
        )

    return output


def materialize_template_files(source_name: str, output_name: str, variant: str,
                               templates_dir: str, vanilla_dir: str,
                               output_dir: str,
                               donor_name: str | None = None,
                               structure_donor_name: str | None = None,
                               sound_dir: str | None = None) -> tuple[str, str]:
    """Build a donor-backed engine pair from one template key to another output key."""
    uasset_donor_name = donor_name or DEFAULT_DONOR_MAP.get(variant)
    if not uasset_donor_name:
        raise ValueError(f'No vanilla donor for variant: {variant}')

    template_uexp_path = os.path.join(templates_dir, source_name + '.uexp')
    if not os.path.isfile(template_uexp_path):
        raise FileNotFoundError(f'Template .uexp not found: {template_uexp_path}')
    template_uexp_data = open(template_uexp_path, 'rb').read()
    template_engine = parse_engine(template_uexp_data)
    resolved_structure_donor = structure_donor_name or resolve_structure_donor_name(
        variant,
        donor_name=uasset_donor_name,
        hp=template_engine.estimated_hp(),
    )
    donor_uexp_path = os.path.join(vanilla_dir, resolved_structure_donor + '.uexp')
    if not os.path.isfile(donor_uexp_path):
        raise FileNotFoundError(f'Vanilla donor .uexp not found: {donor_uexp_path}')

    output_uexp_data = build_donor_backed_uexp_bytes(
        template_uexp_data,
        open(donor_uexp_path, 'rb').read(),
    )

    os.makedirs(output_dir, exist_ok=True)
    output_uasset_path = rebuild_template(
        output_name,
        variant,
        vanilla_dir,
        output_dir,
        len(output_uexp_data),
        donor_name=uasset_donor_name,
        sound_dir=sound_dir,
    )
    output_uexp_path = os.path.join(output_dir, output_name + '.uexp')
    with open(output_uexp_path, 'wb') as f:
        f.write(output_uexp_data)

    return output_uasset_path, output_uexp_path


def rebuild_template_files(template_name: str, variant: str,
                           templates_dir: str, vanilla_dir: str,
                           output_dir: str,
                           donor_name: str | None = None,
                           structure_donor_name: str | None = None,
                           sound_dir: str | None = None) -> tuple[str, str]:
    """Rebuild both .uasset and .uexp for a template engine from a vanilla donor."""
    return materialize_template_files(
        template_name,
        template_name,
        variant,
        templates_dir,
        vanilla_dir,
        output_dir,
        donor_name=donor_name,
        structure_donor_name=structure_donor_name,
        sound_dir=sound_dir,
    )


def rebuild_all_templates(templates_dir: str, vanilla_dir: str,
                          output_dir: str,
                          donor_overrides: dict[str, str] | None = None) -> dict:
    """Rebuild all template .uassets from vanilla donors.

    For each .uexp in templates_dir:
      1. Detect variant
      2. Clone vanilla donor .uasset with correct name + TorqueCurve
      3. Patch SerialSize
      4. Copy .uexp as-is to output_dir

    Args:
        templates_dir: Path to data/templates/Engine/ (has .uexp files)
        vanilla_dir: Path to data/vanilla/Engine/ (has donor .uassets)
        output_dir: Where to write rebuilt .uasset + copied .uexp
        donor_overrides: Optional map of template_name -> donor asset name

    Returns:
        {'rebuilt': int, 'errors': [str]}
    """
    os.makedirs(output_dir, exist_ok=True)
    rebuilt = 0
    errors = []

    for f in sorted(os.listdir(templates_dir)):
        if not f.endswith('.uexp'):
            continue
        name = os.path.splitext(f)[0]
        uexp_path = os.path.join(templates_dir, f)

        try:
            uexp_data = open(uexp_path, 'rb').read()
            variant = detect_variant(uexp_data).value

            rebuild_template_files(
                name,
                variant,
                templates_dir,
                vanilla_dir,
                output_dir,
                donor_name=(donor_overrides or {}).get(name),
            )
            rebuilt += 1
        except Exception as exc:
            errors.append(f'{name}: {exc}')

    return {'rebuilt': rebuilt, 'errors': errors}

