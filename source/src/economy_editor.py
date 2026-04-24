"""
Economy Editor module for Frog Mod Editor.

Reads and modifies Motor Town's Balance.json (cargo payment multipliers)
and DefaultMotorTownBalance.ini (global economy settings) to allow
players to apply global multiplier presets (2x, 3x, 5x, 10x) across
all cargo payments, bus rates, and taxi rates.

The modified files are staged into the mod tree so pack_mod() picks
them up automatically.
"""
import json
import os
import re
import copy
import logging
import shutil
import tempfile
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _atomic_write(path: str, content: str, encoding: str = 'utf-8') -> None:
    """Write *content* to *path* atomically (write → flush → rename).

    Prevents truncated files if the process is interrupted mid-write.
    """
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding=encoding) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        # Atomic rename (same filesystem)
        shutil.move(tmp, path)
    except BaseException:
        # Clean up the temp file on failure
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD_ROOT = os.path.join(_PROJECT_ROOT, 'data', 'mod')

# Vanilla game paths (the unpacked originals, used as baseline)
# Auto-discovered at module load or set manually via set_vanilla_paths()
_vanilla_balance_json: Optional[str] = None
_vanilla_balance_ini: Optional[str] = None


_VANILLA_PATHS_CACHE = os.path.join(_PROJECT_ROOT, 'data', 'vanilla_paths.json')


def _search_dir_for_vanilla(directory: str) -> Tuple[Optional[str], Optional[str]]:
    """Walk a directory looking for Balance.json and DefaultMotorTownBalance.ini."""
    bj = bi = None
    if not os.path.isdir(directory):
        return None, None
    for root, dirs, files in os.walk(directory):
        for f in files:
            if f == 'Balance.json' and not bj:
                bj = os.path.join(root, f)
            elif f == 'DefaultMotorTownBalance.ini' and not bi:
                bi = os.path.join(root, f)
        if bj and bi:
            break
    return bj, bi


def _auto_discover_vanilla_paths() -> None:
    """Try to auto-discover vanilla game files from common locations.

    Checks (in order):
      1. Cached paths from a previous successful discovery
      2. Sibling 'Unpacked' folders relative to the project
      3. The project's own data/vanilla directory
      4. Directly inside the project tree (for single-folder distributions)
    """
    global _vanilla_balance_json, _vanilla_balance_ini
    if _vanilla_balance_json and _vanilla_balance_ini:
        return  # Already set

    # 1. Try loading from cached paths file
    if os.path.isfile(_VANILLA_PATHS_CACHE):
        try:
            with open(_VANILLA_PATHS_CACHE, 'r', encoding='utf-8') as f:
                cached = json.load(f)
            bj = cached.get('balance_json')
            bi = cached.get('balance_ini')
            if bj and bi and os.path.isfile(bj) and os.path.isfile(bi):
                _vanilla_balance_json = bj
                _vanilla_balance_ini = bi
                logger.info("Loaded vanilla paths from cache: json=%s, ini=%s", bj, bi)
                return
        except Exception:
            pass

    # 2. Build candidate directories — most specific first
    candidates = []
    # Sibling "Unpacked" folder at various levels up from project root
    for levels in range(1, 5):
        up = _PROJECT_ROOT
        for _ in range(levels):
            up = os.path.dirname(up)
        candidates.append(os.path.join(up, 'Unpacked'))
    # Inside project data
    candidates.append(os.path.join(_PROJECT_ROOT, 'data', 'vanilla'))
    # CWD-based (user may run from the folder containing Unpacked)
    candidates.append(os.path.join(os.getcwd(), 'Unpacked'))
    # Direct check: maybe the project root itself contains MotorTown/
    candidates.append(_PROJECT_ROOT)

    for candidate in candidates:
        candidate = os.path.normpath(candidate)
        bj, bi = _search_dir_for_vanilla(candidate)
        if bj and bi:
            _vanilla_balance_json = bj
            _vanilla_balance_ini = bi
            logger.info("Auto-discovered vanilla paths: json=%s, ini=%s", bj, bi)
            _save_vanilla_paths_cache(bj, bi)
            return

    logger.warning("Could not auto-discover vanilla game files. "
                    "Use set_vanilla_paths() or select 'Unpacked' folder in the UI.")


def _save_vanilla_paths_cache(bj: str, bi: str) -> None:
    """Persist discovered paths so next launch is instant."""
    try:
        os.makedirs(os.path.dirname(_VANILLA_PATHS_CACHE), exist_ok=True)
        with open(_VANILLA_PATHS_CACHE, 'w', encoding='utf-8') as f:
            json.dump({'balance_json': bj, 'balance_ini': bi}, f, indent=2)
    except Exception as e:
        logger.warning("Could not cache vanilla paths: %s", e)


def vanilla_paths_ok() -> bool:
    """Return True if both vanilla paths are set and point to real files."""
    return bool(
        _vanilla_balance_json and os.path.isfile(_vanilla_balance_json)
        and _vanilla_balance_ini and os.path.isfile(_vanilla_balance_ini)
    )


def set_vanilla_root(unpacked_root: str) -> bool:
    """Set vanilla paths by searching a user-selected folder.

    Called from the UI when the user browses for the Unpacked folder.
    Returns True if both files were found.
    """
    bj, bi = _search_dir_for_vanilla(unpacked_root)
    if bj and bi:
        set_vanilla_paths(bj, bi)
        _save_vanilla_paths_cache(bj, bi)
        return True
    return False


_auto_discover_vanilla_paths()

# Mod output paths (inside the mod tree so pak_writer picks them up)
_MOD_RAWASSETS_DIR = os.path.join(MOD_ROOT, 'MotorTown', 'Content', 'RawAssets')
_MOD_CONFIG_DIR = os.path.join(MOD_ROOT, 'MotorTown', 'Config')
_MOD_BALANCE_JSON = os.path.join(_MOD_RAWASSETS_DIR, 'Balance.json')
_MOD_BALANCE_INI = os.path.join(_MOD_CONFIG_DIR, 'DefaultMotorTownBalance.ini')

# Economy settings file (persisted user preferences)
_ECONOMY_SETTINGS_PATH = os.path.join(_PROJECT_ROOT, 'data', 'economy_settings.json')

# cargos.json — the full Cargos_01 DataTable dumped from the live game by
# CryovacCargoDumper. Contains every FCargoRow field for all 90 cargo types,
# including the 25 rows that have no Balance.json PaymentMultipliers entry.
# Used as the authoritative list of cargo names + per-row context (real base
# rate PaymentPer1Km, weight-penalty slope, etc.) when building the mod.
_VANILLA_CARGO_DUMP = os.path.join(_PROJECT_ROOT, 'data', 'vanilla', 'cargos.json')


# Cached on first read
_cargo_dump_cache: Optional[Dict[str, Dict[str, Any]]] = None


def load_vanilla_cargo_dump() -> Dict[str, Dict[str, Any]]:
    """Load cargos.json and return {cargo_name: row_fields_dict}.

    The dump covers all 90 cargo rows in Cargos_01. Each row has the real
    DataTable values — PaymentPer1Km, PaymentPer1KmMultiplierByMaxWeight,
    BasePayment, WeightRange min/max, delivery distance limits, and so on.

    Returns an empty dict if cargos.json is missing. When that happens,
    callers fall back to Balance.json PaymentMultipliers (65 rows).
    """
    global _cargo_dump_cache
    if _cargo_dump_cache is not None:
        return _cargo_dump_cache
    if not os.path.isfile(_VANILLA_CARGO_DUMP):
        logger.warning("cargos.json not found at %s", _VANILLA_CARGO_DUMP)
        _cargo_dump_cache = {}
        return _cargo_dump_cache
    try:
        with open(_VANILLA_CARGO_DUMP, 'r', encoding='utf-8') as f:
            data = json.load(f)
        _cargo_dump_cache = {r['name']: r for r in data.get('rows', []) if 'name' in r}
        logger.info("Loaded %d cargo rows from %s",
                    len(_cargo_dump_cache), _VANILLA_CARGO_DUMP)
    except Exception as e:
        logger.warning("Could not load cargos.json: %s", e)
        _cargo_dump_cache = {}
    return _cargo_dump_cache


# Default multiplier for cargo rows that have no explicit Balance.json
# entry. UE4 DataTables treat a missing key as 1.0× (no override).
_IMPLICIT_PAYMENT_MULTIPLIER = 1.0

# ---------------------------------------------------------------------------
# Multiplier presets
# ---------------------------------------------------------------------------
MULTIPLIER_PRESETS = {
    '1x (Vanilla)': 1.0,
    '2x': 2.0,
    '3x': 3.0,
    '5x': 5.0,
    '10x': 10.0,
    'Custom': None,  # signals per-value editing mode
}

PRESET_LABELS = list(MULTIPLIER_PRESETS.keys())

# ---------------------------------------------------------------------------
# INI field definitions  (field_name, display_name, category)
# ---------------------------------------------------------------------------
INI_ECONOMY_FIELDS = [
    # Cargo & Delivery
    ('BoxTrailerPaymentPer1Km', 'Box Trailer Payment / km', 'cargo'),
    ('MaxNonFixCargo', 'Max Non-Fixed Cargo', 'cargo'),
    ('JobIncomeToJobExpMultiplier', 'Job Income → EXP Multiplier', 'cargo'),
    # Bus
    ('BusPayment', 'Bus Base Payment', 'bus'),
    ('BusPaymentPer100Meter', 'Bus Payment / 100m', 'bus'),
    # Taxi
    ('TaxiPaymentPer100Meter', 'Taxi Payment / 100m', 'taxi'),
    # Ambulance
    ('AmbulancePaymentPer100Meter', 'Ambulance Payment / 100m', 'ambulance'),
    # Tow / Rescue
    ('NavigatedTowRequestBasePayment', 'Tow Request Base Payment', 'tow'),
    ('NavigatedTowRequestPaymentPer1Km', 'Tow Request Payment / km', 'tow'),
    ('VehicleDeliveryBasePayment', 'Vehicle Delivery Base Payment', 'tow'),
    ('VehicleDeliveryPaymentPer1Km', 'Vehicle Delivery Payment / km', 'tow'),
    ('RescueRequestBasePayment', 'Rescue Request Base Payment', 'tow'),
    ('RescueRequestPaymentPer1Km', 'Rescue Request Payment / km', 'tow'),
    ('TowStartRewardBasePayment', 'Tow Start Reward Base Payment', 'tow'),
    # Fuel costs
    ('FuelCostPerLiter', 'Fuel Cost / Liter (legacy)', 'fuel'),
    ('RoadsideServiceRefuelingBaseCost', 'Roadside Refueling Base Cost', 'fuel'),
    # Vehicle spawn
    ('RoadsideServiceTowToRoadCostPer1Km', 'Tow to Road Cost / km', 'vehicle'),
]

# Fields affected by the global economy multiplier (payments & rewards)
GLOBAL_ECONOMY_FIELDS = [
    'BoxTrailerPaymentPer1Km',
    'NavigatedTowRequestBasePayment',
    'NavigatedTowRequestPaymentPer1Km',
    'VehicleDeliveryBasePayment',
    'VehicleDeliveryPaymentPer1Km',
    'RescueRequestBasePayment',
    'RescueRequestPaymentPer1Km',
    'TowStartRewardBasePayment',
    'JobIncomeToJobExpMultiplier',
]

BUS_RATE_FIELDS = [
    'BusPayment',
    'BusPaymentPer100Meter',
]

TAXI_RATE_FIELDS = [
    'TaxiPaymentPer100Meter',
]

AMBULANCE_RATE_FIELDS = [
    'AmbulancePaymentPer100Meter',
]

FUEL_COST_FIELDS = [
    'FuelCostPerLiter',
    'RoadsideServiceRefuelingBaseCost',
]

VEHICLE_COST_FIELDS = [
    'RoadsideServiceTowToRoadCostPer1Km',
]


# ---------------------------------------------------------------------------
# Vanilla path configuration
# ---------------------------------------------------------------------------
def set_vanilla_paths(balance_json: str, balance_ini: str) -> None:
    """Set the paths to the unpacked vanilla game files."""
    global _vanilla_balance_json, _vanilla_balance_ini
    _vanilla_balance_json = balance_json
    _vanilla_balance_ini = balance_ini


def discover_vanilla_paths(unpacked_root: str) -> Tuple[Optional[str], Optional[str]]:
    """Auto-discover vanilla Balance.json and DefaultMotorTownBalance.ini."""
    balance_json = None
    balance_ini = None
    for root, dirs, files in os.walk(unpacked_root):
        for f in files:
            if f == 'Balance.json':
                balance_json = os.path.join(root, f)
            elif f == 'DefaultMotorTownBalance.ini':
                balance_ini = os.path.join(root, f)
        if balance_json and balance_ini:
            break
    return balance_json, balance_ini


# ---------------------------------------------------------------------------
# Balance.json (Cargo Payment Multipliers)
# ---------------------------------------------------------------------------
def load_vanilla_balance_json() -> Dict[str, Any]:
    """Load the vanilla Balance.json from the unpacked game files."""
    if _vanilla_balance_json and os.path.isfile(_vanilla_balance_json):
        with open(_vanilla_balance_json, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"Cargo": {"PaymentMultipliers": {}}, "BusStop": {"PaymentMultipliers": {}}}


def load_mod_balance_json() -> Optional[Dict[str, Any]]:
    """Load the modded Balance.json if it exists."""
    if os.path.isfile(_MOD_BALANCE_JSON):
        with open(_MOD_BALANCE_JSON, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def get_cargo_payments(vanilla: bool = True) -> Dict[str, float]:
    """Get cargo payment multipliers for every cargo in the game.

    Vanilla Motor Town ships Balance.json with explicit PaymentMultipliers
    for only 65 of the 90 cargo rows in the Cargos_01 DataTable. The
    missing 25 rows (IronOre, Cement, CopperOre, Tank_250kL, the two
    Transformers, etc.) fall back to 1.0× at runtime because they have
    no entry.

    The UI cargo table iterates this dict, so returning only the 65
    explicit entries means those 25 rows are invisible in the editor —
    users can't see their values or override them. We merge in every
    row from cargos.json (the live DataTable dump) with 1.0× as the
    implicit baseline so all 90 cargos are editable.

    When vanilla=False, return just the modded dict as-written.
    """
    if not vanilla:
        modded = load_mod_balance_json()
        if modded:
            return modded.get('Cargo', {}).get('PaymentMultipliers', {})
    data = load_vanilla_balance_json()
    explicit = dict(data.get('Cargo', {}).get('PaymentMultipliers', {}))
    dump = load_vanilla_cargo_dump()
    if not dump:
        return explicit
    merged: Dict[str, float] = {}
    for cargo_name in dump:
        merged[cargo_name] = explicit.get(cargo_name, _IMPLICIT_PAYMENT_MULTIPLIER)
    # Keep any Balance.json entries the dump doesn't know about.
    for cargo_name, value in explicit.items():
        merged.setdefault(cargo_name, value)
    return merged


def get_cargo_row_info(cargo_name: str) -> Dict[str, Any]:
    """Return the per-row DataTable info for a cargo (PaymentPer1Km, etc.).

    Returns an empty dict if the cargo isn't in cargos.json.
    """
    return load_vanilla_cargo_dump().get(cargo_name, {})


def apply_cargo_multiplier(multiplier: float) -> Dict[str, Any]:
    """Apply a global multiplier to every cargo in the game and save.

    Writes an explicit PaymentMultipliers entry for all 90 rows known
    to the editor (65 from Balance.json + 25 implicit-1.0× rows from
    cargos.json). Without this, rows like IronOre, Cement, Transformer_20MVA
    would silently stay at 1.0× regardless of the economy slider.

    The per-vehicle capacity penalty is a different axis, handled by
    the CryovacCargoScaling Lua mod.
    """
    vanilla = load_vanilla_balance_json()
    modified = copy.deepcopy(vanilla)

    cargo_section = modified.setdefault('Cargo', {})
    cargo_payments = cargo_section.setdefault('PaymentMultipliers', {})

    # Full 90-row view (explicit + implicit-1.0×). Write every row so
    # previously-implicit cargos participate in the global multiplier.
    full_view = get_cargo_payments(vanilla=True)

    for cargo_name, base_value in full_view.items():
        cargo_payments[cargo_name] = round(base_value * multiplier, 6)

    modified['Cargo']['PaymentMultipliers'] = cargo_payments
    _save_balance_json(modified)
    return modified


def apply_bus_stop_multiplier(multiplier: float) -> Dict[str, Any]:
    """Apply a multiplier to bus stop payment multipliers in Balance.json."""
    vanilla = load_vanilla_balance_json()
    # Start from current mod state or vanilla
    modded = load_mod_balance_json() or copy.deepcopy(vanilla)

    bus_payments = modded.get('BusStop', {}).get('PaymentMultipliers', {})
    vanilla_bus = vanilla.get('BusStop', {}).get('PaymentMultipliers', {})

    for stop_id, base_value in vanilla_bus.items():
        bus_payments[stop_id] = round(base_value * multiplier, 6)

    modded['BusStop']['PaymentMultipliers'] = bus_payments
    _save_balance_json(modded)
    return modded


def _save_balance_json(data: Dict[str, Any]) -> None:
    """Save modified Balance.json to the mod tree (atomic write)."""
    _atomic_write(_MOD_BALANCE_JSON, json.dumps(data, indent=4))
    logger.info("Saved modified Balance.json to %s", _MOD_BALANCE_JSON)


# ---------------------------------------------------------------------------
# DefaultMotorTownBalance.ini parsing and modification
# ---------------------------------------------------------------------------
def load_vanilla_balance_ini() -> Dict[str, Any]:
    """Parse the vanilla DefaultMotorTownBalance.ini into a dict of field→value."""
    if not _vanilla_balance_ini or not os.path.isfile(_vanilla_balance_ini):
        return {}
    with open(_vanilla_balance_ini, 'r', encoding='utf-8') as f:
        content = f.read()
    return _parse_balance_ini(content)


def load_mod_balance_ini() -> Optional[Dict[str, Any]]:
    """Load the modded INI values if the mod file exists."""
    if os.path.isfile(_MOD_BALANCE_INI):
        with open(_MOD_BALANCE_INI, 'r', encoding='utf-8') as f:
            content = f.read()
        return _parse_balance_ini(content)
    return None


def _parse_balance_ini(content: str) -> Dict[str, Any]:
    """Extract key=value fields from the BalanceTable= line in the INI."""
    result = {}
    # Find the BalanceTable= line
    match = re.search(r'BalanceTable=\((.+)\)', content, re.DOTALL)
    if not match:
        return result

    table_content = match.group(1)

    # Parse simple key=value pairs (numeric values)
    for field_name, _, _ in INI_ECONOMY_FIELDS:
        pattern = rf'{field_name}=([0-9]+(?:\.[0-9]+)?)'
        m = re.search(pattern, table_content)
        if m:
            val = m.group(1)
            result[field_name] = float(val) if '.' in val else int(val)

    # Also parse array-style fields like FuelCostPerLiters=((Electric, 2.0),(Diesel, 5.0))
    fuel_match = re.search(
        r'FuelCostPerLiters=(\(\(.+?\)\))',
        table_content,
    )
    if fuel_match:
        result['_FuelCostPerLiters_raw'] = fuel_match.group(0)
        fuel_pairs = re.findall(r'\((\w+),\s*([0-9.]+)\)', fuel_match.group(1))
        result['_fuel_cost_per_liters'] = {k: float(v) for k, v in fuel_pairs}

    # Parse VehicleSpawnCostPer1KmByTruckClass
    spawn_match = re.search(
        r'VehicleSpawnCostPer1KmByTruckClass=(\(\(.+?\)\))',
        table_content,
    )
    if spawn_match:
        result['_VehicleSpawnCostPer1KmByTruckClass_raw'] = spawn_match.group(0)

    # Parse VehicleOwnerProfitShare  →  { 'Small': 0.2, 'Pickup': 0.2, ... }
    profit_match = re.search(
        r'VehicleOwnerProfitShare=\((.+?)\),VehicleOwnerProfitSharePerCost',
        table_content,
    )
    if profit_match:
        pairs = re.findall(r'\((\w+),\s*([0-9.]+)\)', profit_match.group(1))
        result['_profit_share'] = {k: float(v) for k, v in pairs}


    # Store raw content for reconstruction
    result['_raw_content'] = content
    result['_table_content'] = table_content

    return result


def apply_ini_multipliers(
    economy_multiplier: float = 1.0,
    bus_multiplier: float = 1.0,
    taxi_multiplier: float = 1.0,
    ambulance_multiplier: float = 1.0,
    fuel_multiplier: float = 1.0,
    vehicle_multiplier: float = 1.0,
) -> Dict[str, Any]:
    """Apply multipliers to INI economy fields and save to mod tree."""
    vanilla = load_vanilla_balance_ini()
    if not vanilla or '_raw_content' not in vanilla:
        return {'error': 'Could not load vanilla balance INI'}

    content = vanilla['_raw_content']

    # Apply multipliers to each field based on category
    for field_name, _, category in INI_ECONOMY_FIELDS:
        if field_name not in vanilla:
            continue

        base_value = vanilla[field_name]
        if category == 'bus':
            multiplier = bus_multiplier
        elif category == 'taxi':
            multiplier = taxi_multiplier
        elif category == 'ambulance':
            multiplier = ambulance_multiplier
        elif category in ('cargo', 'tow'):
            multiplier = economy_multiplier
        elif category == 'fuel':
            multiplier = fuel_multiplier
        elif category == 'vehicle':
            multiplier = vehicle_multiplier
        else:
            continue

        new_value = base_value * multiplier
        # Format: preserve int if original was int, otherwise float with 6 decimals
        if isinstance(base_value, int):
            new_str = str(int(new_value))
        else:
            new_str = f'{new_value:.6f}'

        # Replace in content
        pattern = rf'({field_name}=)[0-9]+(?:\.[0-9]+)?'
        content = re.sub(pattern, rf'\g<1>{new_str}', content)

    # Scale the FuelCostPerLiters array (Electric, Diesel, Water per-type costs)
    fuel_costs = vanilla.get('_fuel_cost_per_liters', {})
    if fuel_costs:
        content = _scale_ini_array_field(
            content, 'FuelCostPerLiters', fuel_costs, fuel_multiplier,
        )

    _save_balance_ini(content)
    return {'success': True}


def _save_balance_ini(content: str) -> None:
    """Save modified INI to the mod tree (atomic write)."""
    _atomic_write(_MOD_BALANCE_INI, content)
    logger.info("Saved modified DefaultMotorTownBalance.ini to %s", _MOD_BALANCE_INI)


def _scale_ini_array_field(content: str, field_name: str,
                           vanilla_values: Dict[str, float],
                           multiplier: float) -> str:
    """Scale numeric values inside an INI array field like ((Key, Value),...).

    IMPORTANT: scopes all (Key, Value) substitutions to the specific
    field_name's block. Earlier versions used an unscoped regex which
    caused keys shared across fields (e.g. 'Pickup' appears in both
    VehicleOwnerProfitShare and RentalCostMultiplier) to be substituted
    in every matching spot. That silently wrecked RentalCostMultiplier
    values any time the profit-share preset ran with a non-1.0 factor.
    """
    # Find the opening `field_name=((` — require a word boundary before
    # the field name so e.g. `VehicleSpawnCostByTruckClass` doesn't
    # accidentally prefix-match a field called `SpawnCostByTruckClass`.
    m = re.search(rf'\b{re.escape(field_name)}=\(\(', content)
    if not m:
        return content
    block_start = m.end() - 2  # position of the opening `((`

    # Walk paren depth forward to find the matching closing `))`.
    depth = 0
    i = block_start
    while i < len(content):
        c = content[i]
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
            if depth == 0:
                i += 1  # include the closing `)`
                break
        i += 1

    block = content[block_start:i]
    new_block = block
    for key, base_val in vanilla_values.items():
        new_val = base_val * multiplier
        kp = rf'(\({re.escape(key)},\s*)[0-9]+(?:\.[0-9]+)?(\))'
        new_block = re.sub(kp, rf'\g<1>{new_val:.6f}\2', new_block)

    return content[:block_start] + new_block + content[i:]


def apply_profit_share_multiplier(multiplier: float) -> Dict[str, Any]:
    """Scale VehicleOwnerProfitShare values in the INI by a multiplier.

    Vanilla values are ~0.2–0.3 per vehicle class.
    multiplier=1.0 keeps vanilla, 2.0 doubles the share, etc.
    """
    vanilla = load_vanilla_balance_ini()
    if not vanilla or '_raw_content' not in vanilla:
        return {'error': 'Could not load vanilla balance INI'}
    profit_share = vanilla.get('_profit_share', {})
    if not profit_share:
        return {'error': 'Could not parse VehicleOwnerProfitShare from INI'}

    # Start from current mod content if it exists, otherwise vanilla
    mod_ini = load_mod_balance_ini()
    if mod_ini and '_raw_content' in mod_ini:
        content = mod_ini['_raw_content']
    else:
        content = vanilla['_raw_content']

    content = _scale_ini_array_field(
        content, 'VehicleOwnerProfitShare', profit_share, multiplier,
    )
    _save_balance_ini(content)
    return {'success': True}


# Profit share presets: label → multiplier on vanilla VehicleOwnerProfitShare
# Vanilla values are 0.2 (Small/Pickup/Bus/Bike) and 0.3 (Truck/SemiTractor).
# User reports vanilla ≈ 5% in-game. Presets scale proportionally.
PROFIT_SHARE_PRESETS = {
    '2.5%': 0.5,
    '5% (Vanilla)': 1.0,
    '10%': 2.0,
    '15%': 3.0,
    '20%': 4.0,
}

PROFIT_SHARE_LABELS = list(PROFIT_SHARE_PRESETS.keys())


# ---------------------------------------------------------------------------
# Unified economy settings (persisted user preferences)
# ---------------------------------------------------------------------------
def load_economy_settings() -> Dict[str, Any]:
    """Load saved economy multiplier settings."""
    defaults = {
        'economy_multiplier': 1.0,
        'bus_multiplier': 1.0,
        'taxi_multiplier': 1.0,
        'ambulance_multiplier': 1.0,
        'fuel_multiplier': 1.0,
        'vehicle_multiplier': 1.0,
        'economy_custom': False,
        'bus_custom': False,
        'taxi_custom': False,
        'ambulance_custom': False,
        'fuel_custom': False,
        'vehicle_custom': False,
        'capacity_scaling_mode': 'Vanilla',
        'profit_share': '5% (Vanilla)',
        'custom_cargo_overrides': {},
        'custom_ini_overrides': {},
    }
    if os.path.isfile(_ECONOMY_SETTINGS_PATH):
        try:
            with open(_ECONOMY_SETTINGS_PATH, 'r', encoding='utf-8') as f:
                saved = json.load(f)
            defaults.update(saved)
        except Exception as e:
            logger.warning("Could not load economy settings: %s", e)
    return defaults


def save_economy_settings(settings: Dict[str, Any]) -> None:
    """Persist economy multiplier settings (atomic write)."""
    _atomic_write(_ECONOMY_SETTINGS_PATH, json.dumps(settings, indent=2))


def apply_custom_cargo_values(cargo_overrides: Dict[str, float]) -> Dict[str, Any]:
    """Apply per-cargo custom payment values and save to Balance.json.

    Args:
        cargo_overrides: dict mapping cargo name -> new payment multiplier value.
    """
    vanilla = load_vanilla_balance_json()
    modified = copy.deepcopy(vanilla)
    cargo_payments = modified.get('Cargo', {}).get('PaymentMultipliers', {})
    for cargo_name, new_value in cargo_overrides.items():
        cargo_payments[cargo_name] = round(new_value, 6)
    modified['Cargo']['PaymentMultipliers'] = cargo_payments
    _save_balance_json(modified)
    return modified


def apply_custom_ini_values(ini_overrides: Dict[str, float]) -> Dict[str, Any]:
    """Apply per-field custom INI values and save.

    Args:
        ini_overrides: dict mapping INI field name -> new numeric value.
    """
    vanilla = load_vanilla_balance_ini()
    if not vanilla or '_raw_content' not in vanilla:
        return {'error': 'Could not load vanilla balance INI'}
    content = vanilla['_raw_content']
    for field_name, new_value in ini_overrides.items():
        if isinstance(new_value, int):
            new_str = str(new_value)
        else:
            new_str = f'{new_value:.6f}'
        pattern = rf'({field_name}=)[0-9]+(?:\.[0-9]+)?'
        content = re.sub(pattern, rf'\g<1>{new_str}', content)
    _save_balance_ini(content)
    return {'success': True}


def apply_all_economy_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Apply all economy multiplier settings and write mod files.

    Args:
        settings: dict with keys like 'economy_multiplier', 'bus_multiplier', etc.
                  Values are preset labels like '2x', '5x', 'Custom', etc.
                  For Custom mode, also reads 'custom_cargo_overrides' and
                  'custom_ini_overrides' dicts with per-value settings.

    Returns:
        dict with 'success' or 'error' key.
    """
    # All 6 categories now send direct float values from sliders.
    # Legacy preset labels are also handled for backwards compatibility.
    def _resolve_mult(key):
        raw = settings.get(f'{key}_multiplier', 1.0)
        if isinstance(raw, str):
            return MULTIPLIER_PRESETS.get(raw, 1.0)
        return float(raw)

    eco_mult = _resolve_mult('economy')
    bus_mult = _resolve_mult('bus')
    taxi_mult = _resolve_mult('taxi')
    amb_mult = _resolve_mult('ambulance')
    fuel_mult = _resolve_mult('fuel')
    veh_mult = _resolve_mult('vehicle')

    # Custom mode flags (checkbox state from UI)
    is_custom_cargo = bool(settings.get('economy_custom', False)) or eco_mult is None
    is_custom_bus = bool(settings.get('bus_custom', False)) or bus_mult is None
    is_custom_taxi = bool(settings.get('taxi_custom', False)) or taxi_mult is None
    is_custom_amb = bool(settings.get('ambulance_custom', False)) or amb_mult is None
    is_custom_fuel = bool(settings.get('fuel_custom', False))
    is_custom_veh = bool(settings.get('vehicle_custom', False))

    # capacity_scaling_mode is stored in settings but drives a separate
    # deploy path (CryovacCargoScaling Lua mod via cargo_scaling_deployer).
    # It intentionally does NOT modify Balance.json — that axis and this
    # axis (per-cargo-type vs per-vehicle-weight) are unrelated.

    results = {}

    # 1. Apply cargo payment multipliers in Balance.json
    try:
        if is_custom_cargo:
            custom_cargo = settings.get('custom_cargo_overrides', {})
            if custom_cargo:
                apply_custom_cargo_values(custom_cargo)
            results['balance_json'] = 'ok (custom)'
        else:
            apply_cargo_multiplier(eco_mult)
            results['balance_json'] = 'ok'
    except Exception as e:
        results['balance_json'] = f'error: {e}'

    # 2. Apply bus stop multipliers in Balance.json
    try:
        if not is_custom_bus:
            apply_bus_stop_multiplier(bus_mult)
        results['bus_stop_json'] = 'ok'
    except Exception as e:
        results['bus_stop_json'] = f'error: {e}'

    # 3. Apply INI multipliers
    try:
        custom_ini = settings.get('custom_ini_overrides', {})
        any_custom = any([is_custom_cargo, is_custom_bus, is_custom_taxi,
                          is_custom_amb, is_custom_fuel, is_custom_veh])
        if any_custom and custom_ini:
            apply_custom_ini_values(custom_ini)
            results['balance_ini'] = {'success': True, 'mode': 'custom'}
        else:
            ini_result = apply_ini_multipliers(
                economy_multiplier=eco_mult or 1.0,
                bus_multiplier=bus_mult or 1.0,
                taxi_multiplier=taxi_mult or 1.0,
                ambulance_multiplier=amb_mult or 1.0,
                fuel_multiplier=fuel_mult or 1.0,
                vehicle_multiplier=veh_mult or 1.0,
            )
            results['balance_ini'] = ini_result
    except Exception as e:
        results['balance_ini'] = f'error: {e}'

    # 4. Profit share preset was removed — VehicleOwnerProfitShare in
    # the balance INI applies globally per vehicle class and so
    # affected every matching vehicle in the world, including ones
    # the player doesn't own (rentals, AI-company trucks). Any
    # legacy profit_share value in `settings` is ignored.
    results['profit_share'] = 'skipped (feature removed)'

    # 5. Save settings for next session
    save_economy_settings(settings)

    any_errors = any('error' in str(v) for v in results.values())
    return {
        'success': not any_errors,
        'details': results,
        'multipliers': {
            'economy': 'custom' if is_custom_cargo else (eco_mult or 1.0),
            'bus': 'custom' if is_custom_bus else (bus_mult or 1.0),
            'taxi': 'custom' if is_custom_taxi else (taxi_mult or 1.0),
            'ambulance': 'custom' if is_custom_amb else (amb_mult or 1.0),
            'fuel': 'custom' if is_custom_fuel else (fuel_mult or 1.0),
            'vehicle': 'custom' if is_custom_veh else (veh_mult or 1.0),
        },
    }


def remove_economy_mod_files() -> None:
    """Remove economy mod files (reset to vanilla)."""
    for path in (_MOD_BALANCE_JSON, _MOD_BALANCE_INI):
        if os.path.isfile(path):
            try:
                os.remove(path)
                logger.info("Removed mod economy file: %s", path)
            except OSError as e:
                logger.warning("Could not remove %s: %s", path, e)
    # Restore the vanilla INI in the game directory if we previously deployed one
    restore_vanilla_ini()


# ---------------------------------------------------------------------------
# Loose INI deployment — UE4 does not load INI files from .pak archives
# ---------------------------------------------------------------------------
_INI_BACKUP_SUFFIX = '.frogmod_backup'


def _derive_game_root(pak_output_path: str) -> Optional[str]:
    """Derive the MotorTown game root from a .pak output path.

    Expected layout:
      .../MotorTown/Content/Paks/<name>.pak  →  .../MotorTown/

    Returns None if the path doesn't match the expected structure.
    """
    norm = pak_output_path.replace('\\', '/')
    parts = [p for p in norm.split('/') if p]

    def _rejoin(parts_list):
        joined = os.sep.join(parts_list)
        if pak_output_path.replace('\\', '/').startswith('/'):
            joined = os.sep + joined
        return joined

    # Walk backwards to find 'Paks' under 'Content'
    for i in range(len(parts) - 1, 0, -1):
        if parts[i].lower() == 'paks' and i >= 2:
            content_idx = i - 1
            if parts[content_idx].lower() == 'content':
                return _rejoin(parts[:content_idx])

    # Fallback: look for 'MotorTown' directory name
    for i in range(len(parts) - 1, -1, -1):
        if parts[i].lower() in ('motortow', 'motortown'):
            return _rejoin(parts[:i + 1])

    return None


def _backup_and_copy(src: str, target: str) -> Dict[str, Any]:
    """Back up *target* (once) and then overwrite it with *src*.

    Returns a dict with 'deployed_to' / 'backup' on success or 'error'.
    """
    backup = target + _INI_BACKUP_SUFFIX
    if os.path.isfile(target) and not os.path.isfile(backup):
        try:
            shutil.copy2(target, backup)
            logger.info("Backed up %s", backup)
        except OSError as e:
            return {'error': f'Backup failed: {e}'}
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(src, target)
        logger.info("Deployed %s", target)
        return {'deployed_to': target, 'backup': backup}
    except OSError as e:
        return {'error': f'Deploy failed: {e}', 'source': src}


def deploy_ini_to_game_only(pak_output_path: str) -> Dict[str, Any]:
    """Deploy the modified INI to the game directory.

    Writes to TWO locations so that every field takes effect:

      1. ``Config/DefaultMotorTownBalance.ini``  — the project default.
      2. ``Saved/Config/Windows/MotorTownBalance.ini`` — the per-user
         override.  UE4's config hierarchy gives Saved/ higher priority
         than Config/, so if the game ever wrote a cached value here
         (e.g. fuel prices), it would shadow our Default changes.  By
         writing our values into the Saved config as well, we guarantee
         the game uses them.

    Both ``Windows`` and ``WindowsNoEditor`` Saved subdirectories are
    covered.  Balance.json stays in the pak (the game reads it there).

    Returns a dict summarising what was deployed.
    """
    if not os.path.isfile(_MOD_BALANCE_INI):
        return {'skipped': True, 'reason': 'No modified INI to deploy'}

    game_root = _derive_game_root(pak_output_path)
    if not game_root:
        return {
            'error': ('Could not determine the game directory from the pak '
                      'output path. You may need to manually copy '
                      'DefaultMotorTownBalance.ini to MotorTown/Config/.'),
        }

    results: Dict[str, Any] = {}

    # 1. Deploy to Config/ (project default)
    target_default = os.path.join(game_root, 'Config',
                                  'DefaultMotorTownBalance.ini')
    results['default'] = _backup_and_copy(_MOD_BALANCE_INI, target_default)

    # 2. Deploy to Saved/Config/ (per-user override — highest priority)
    #    UE4 strips the "Default" prefix for the Saved version.
    saved_name = 'MotorTownBalance.ini'
    for platform_dir in ('Windows', 'WindowsNoEditor'):
        saved_path = os.path.join(game_root, 'Saved', 'Config',
                                  platform_dir, saved_name)
        # Only deploy if the Saved directory or file already exists —
        # we don't want to create a Saved tree that never existed.
        saved_dir = os.path.dirname(saved_path)
        if os.path.isdir(saved_dir) or os.path.isfile(saved_path):
            results[f'saved_{platform_dir}'] = _backup_and_copy(
                _MOD_BALANCE_INI, saved_path)

    # Flatten for the simple 'deployed_to' key expected by callers
    deployed = results.get('default', {}).get('deployed_to', '')
    if deployed:
        results['deployed_to'] = deployed

    return results


def restore_vanilla_ini(pak_output_path: str = '') -> Dict[str, Any]:
    """Restore all backed-up vanilla INI files in the game directory."""
    game_root = None
    if pak_output_path:
        game_root = _derive_game_root(pak_output_path)
    if not game_root:
        try:
            from api.routes import DEFAULT_PAKS_DIR
            game_root = _derive_game_root(
                os.path.join(DEFAULT_PAKS_DIR, 'dummy.pak'))
        except ImportError:
            pass
    if not game_root:
        return {'skipped': True, 'reason': 'Could not determine game directory'}

    restored = {}

    # Restore Config/ default
    target = os.path.join(game_root, 'Config', 'DefaultMotorTownBalance.ini')
    backup = target + _INI_BACKUP_SUFFIX
    if os.path.isfile(backup):
        try:
            shutil.copy2(backup, target)
            os.remove(backup)
            logger.info("Restored vanilla INI from %s", backup)
            restored['default'] = {'restored': target}
        except OSError as e:
            logger.warning("Failed to restore vanilla INI: %s", e)
            restored['default'] = {'error': str(e)}

    # Restore Saved/ overrides
    for platform_dir in ('Windows', 'WindowsNoEditor'):
        saved = os.path.join(game_root, 'Saved', 'Config',
                             platform_dir, 'MotorTownBalance.ini')
        saved_backup = saved + _INI_BACKUP_SUFFIX
        if os.path.isfile(saved_backup):
            try:
                shutil.copy2(saved_backup, saved)
                os.remove(saved_backup)
                logger.info("Restored saved INI from %s", saved_backup)
                restored[f'saved_{platform_dir}'] = {'restored': saved}
            except OSError as e:
                restored[f'saved_{platform_dir}'] = {'error': str(e)}

    return restored if restored else {'skipped': True, 'reason': 'No backups found'}


def get_economy_summary() -> Dict[str, Any]:
    """Get a summary of current economy state for display."""
    settings = load_economy_settings()
    vanilla_cargo = get_cargo_payments(vanilla=True)
    modded_cargo = get_cargo_payments(vanilla=False)
    vanilla_ini = load_vanilla_balance_ini()
    modded_ini = load_mod_balance_ini()

    has_mod = os.path.isfile(_MOD_BALANCE_JSON) or os.path.isfile(_MOD_BALANCE_INI)

    return {
        'settings': settings,
        'has_mod': has_mod,
        'vanilla_cargo_count': len(vanilla_cargo),
        'modded_cargo_count': len(modded_cargo),
        'vanilla_bus_payment': vanilla_ini.get('BusPayment', 'N/A'),
        'vanilla_taxi_payment': vanilla_ini.get('TaxiPaymentPer100Meter', 'N/A'),
        'vanilla_ambulance_payment': vanilla_ini.get('AmbulancePaymentPer100Meter', 'N/A'),
        'modded_bus_payment': modded_ini.get('BusPayment', 'N/A') if modded_ini else 'N/A',
        'modded_taxi_payment': modded_ini.get('TaxiPaymentPer100Meter', 'N/A') if modded_ini else 'N/A',
    }
