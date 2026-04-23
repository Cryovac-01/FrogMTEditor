"""
Policy Editor backend for Frog Mod Editor.

Reads vanilla Policies.uasset/.uexp, allows editing existing policies
and adding new ones, then writes the modified files to the mod tree
for inclusion in the .pak.
"""
import json
import logging
import os
import shutil
import tempfile
from typing import Any, Dict, List, Optional, Tuple

from parsers.uexp_policies_dt import (
    PoliciesData, PolicyRow, parse_policies, serialize_uexp,
    update_uasset_serial_size,
    add_policy_row, remove_new_rows, EFFECT_TYPES, EFFECT_TYPE_LABELS,
    EFFECT_TYPE_UNITS,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD_ROOT = os.path.join(_PROJECT_ROOT, 'data', 'mod')

# Mod output paths (inside mod tree, matching game structure)
MOD_POLICIES_DIR = os.path.join(MOD_ROOT, 'MotorTown', 'Content', 'DataAsset')
MOD_UASSET = os.path.join(MOD_POLICIES_DIR, 'Policies.uasset')
MOD_UEXP = os.path.join(MOD_POLICIES_DIR, 'Policies.uexp')

# Vanilla file discovery
_vanilla_uasset: Optional[str] = None
_vanilla_uexp: Optional[str] = None

# Persistence file for policy mod settings
POLICY_SETTINGS_PATH = os.path.join(_PROJECT_ROOT, 'data', 'policy_settings.json')


def _atomic_write_bin(path: str, data: bytes) -> None:
    """Write binary data to path atomically."""
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        shutil.move(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _discover_vanilla() -> bool:
    """Find vanilla Policies.uasset/.uexp in the Unpacked folder."""
    global _vanilla_uasset, _vanilla_uexp
    if _vanilla_uasset and _vanilla_uexp:
        if os.path.isfile(_vanilla_uasset) and os.path.isfile(_vanilla_uexp):
            return True

    # Search relative to project root
    candidates = []
    for levels in range(1, 5):
        up = _PROJECT_ROOT
        for _ in range(levels):
            up = os.path.dirname(up)
        candidates.append(os.path.join(up, 'Unpacked'))
    candidates.append(os.path.join(os.getcwd(), 'Unpacked'))

    for base in candidates:
        base = os.path.normpath(base)
        ua = os.path.join(base, 'MotorTown', 'Content', 'DataAsset', 'Policies.uasset')
        ue = os.path.join(base, 'MotorTown', 'Content', 'DataAsset', 'Policies.uexp')
        if os.path.isfile(ua) and os.path.isfile(ue):
            _vanilla_uasset = ua
            _vanilla_uexp = ue
            logger.info("Found vanilla policies: %s", ua)
            return True

    logger.warning("Could not find vanilla Policies files.")
    return False


def set_vanilla_root(unpacked_root: str) -> bool:
    """Set vanilla paths from user-selected Unpacked folder."""
    global _vanilla_uasset, _vanilla_uexp
    ua = os.path.join(unpacked_root, 'MotorTown', 'Content', 'DataAsset', 'Policies.uasset')
    ue = os.path.join(unpacked_root, 'MotorTown', 'Content', 'DataAsset', 'Policies.uexp')
    if os.path.isfile(ua) and os.path.isfile(ue):
        _vanilla_uasset = ua
        _vanilla_uexp = ue
        return True
    # Try walking for it
    for root, dirs, files in os.walk(unpacked_root):
        if 'Policies.uasset' in files and 'Policies.uexp' in files:
            _vanilla_uasset = os.path.join(root, 'Policies.uasset')
            _vanilla_uexp = os.path.join(root, 'Policies.uexp')
            return True
    return False


def load_vanilla_policies() -> Optional[PoliciesData]:
    """Load and parse the vanilla (unmodded) policy data."""
    if not _discover_vanilla():
        return None
    try:
        with open(_vanilla_uasset, 'rb') as f:
            ua = f.read()
        with open(_vanilla_uexp, 'rb') as f:
            ue = f.read()
        return parse_policies(ua, ue)
    except Exception as e:
        logger.error("Failed to parse vanilla policies: %s", e)
        return None


def load_saved_settings() -> Optional[Dict]:
    """Load saved policy editor settings from disk."""
    if not os.path.isfile(POLICY_SETTINGS_PATH):
        return None
    try:
        with open(POLICY_SETTINGS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Failed to load policy settings: %s", e)
        return None


def save_settings(settings: Dict) -> None:
    """Persist policy editor settings."""
    os.makedirs(os.path.dirname(POLICY_SETTINGS_PATH), exist_ok=True)
    with open(POLICY_SETTINGS_PATH, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=2)


def apply_policy_changes(settings: Dict) -> Dict:
    """Apply policy modifications and write to mod tree.

    Args:
        settings: Dict with structure:
            {
                'modifications': {
                    '<row_name>': {
                        'cost': int,
                        'effect_value': float,
                        'display_name': str,  # optional
                    },
                    ...
                },
                'new_policies': [
                    {
                        'display_name': str,
                        'cost': int,
                        'effect_type': str,  # short name
                        'effect_value': float,
                    },
                    ...
                ],
            }

    Returns:
        Result dict with 'success' bool and details.
    """
    data = load_vanilla_policies()
    if data is None:
        return {'success': False, 'error': 'Could not load vanilla policy data.'}

    modifications = settings.get('modifications', {})
    new_policies = settings.get('new_policies', [])

    # Apply modifications to existing rows
    modified_count = 0
    for row in data.rows:
        mods = modifications.get(row.row_name)
        if not mods:
            continue
        if 'cost' in mods:
            row.cost = int(mods['cost'])
        if 'effect_value' in mods:
            row.effect_value = float(mods['effect_value'])
        if 'display_name' in mods:
            row.display_name = str(mods['display_name'])
        modified_count += 1

    # Add new policy rows
    added_count = 0
    for np in new_policies:
        try:
            add_policy_row(
                data,
                display_name=np['display_name'],
                cost=int(np['cost']),
                effect_short=np['effect_type'],
                effect_value=float(np['effect_value']),
                row_name=np.get('row_name', ''),
            )
            added_count += 1
        except Exception as e:
            logger.error("Failed to add policy '%s': %s", np.get('display_name'), e)

    # Serialize
    new_ue = serialize_uexp(data)
    # Update .uasset SerialSize to match actual .uexp content length.
    # Without this, UE5's async loader crashes when the .uexp size differs
    # from what the export entry declares (e.g. after adding rows or
    # changing display name lengths).
    new_ua = update_uasset_serial_size(data.uasset_bytes, new_ue)

    # Write to mod tree
    _atomic_write_bin(MOD_UASSET, new_ua)
    _atomic_write_bin(MOD_UEXP, new_ue)

    # Save settings for persistence
    save_settings(settings)

    result = {
        'success': True,
        'modified': modified_count,
        'added': added_count,
        'total_rows': len(data.rows),
        'uexp_size': len(new_ue),
        'uasset_size': len(new_ua),
    }
    logger.info("Policy changes applied: %s", result)
    return result


def remove_policy_mod() -> Dict:
    """Remove policy mod files from the mod tree."""
    removed = []
    for path in (MOD_UASSET, MOD_UEXP):
        if os.path.isfile(path):
            os.remove(path)
            removed.append(os.path.basename(path))
    # Remove settings
    if os.path.isfile(POLICY_SETTINGS_PATH):
        os.remove(POLICY_SETTINGS_PATH)
    return {'success': True, 'removed': removed}


def is_policy_mod_staged() -> bool:
    """Check if modified policy files exist in the mod tree."""
    return os.path.isfile(MOD_UEXP) and os.path.isfile(MOD_UASSET)


def get_effect_type_choices() -> List[Dict[str, str]]:
    """Return list of available effect types for the UI."""
    choices = []
    for short, label in EFFECT_TYPE_LABELS.items():
        unit, desc = EFFECT_TYPE_UNITS.get(short, ('', ''))
        choices.append({
            'key': short,
            'label': label,
            'unit': unit,
            'description': desc,
        })
    return choices
