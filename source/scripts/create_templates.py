"""
create_templates.py
===================
Recreates all engine template files for the mod from vanilla base-game templates.

Run from repo root:
    python/python.exe scripts/create_templates.py

Creates all GAME_ENGINE_NAMES engines + NEW_ENGINES templates using vanilla
ICE/Diesel/EV engines as binary prototypes. Bikes now use the modern
88-byte `Bike_i4_100HP` donor so every generated bike keeps StarterRPM and
IdleThrottle.
"""
import os
import sys
import shutil
import statistics

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from engine_validation import audit_engine_value_consistency
from parsers.uexp_engine import parse_engine, serialize_engine
from parsers.uasset_clone import clone_uasset

PROJ_ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VANILLA_DIR = os.path.join(PROJ_ROOT, 'data', 'vanilla', 'Engine')
MOD_DIR     = os.path.join(PROJ_ROOT, 'data', 'mod', 'MotorTown', 'Content', 'Cars', 'Parts', 'Engine')
CURVE_FACTOR = 0.946
MIN_SAFE_DIESEL_RPM = 1500.0
MIN_SAFE_FUEL_CONSUMPTION = 0.1
FUEL_CONSUMPTION_SCALE = 0.125
# Bikes and modern standard engines carry HeatingPower, so keep the field
# present there and bias it low without changing the legacy rev/friction feel.
DEFAULT_TEMPLATE_HEATING_POWER = 0.5
STANDARD_SOURCE_ENGINE = 'H2_30HP'
COMPACT_SOURCE_ENGINE = 'I4Sport_150HP'
DIESEL_SOURCE_ENGINE = 'HeavyDuty_440HP'
BIKE_SOURCE_ENGINE = 'Bike_i4_100HP'
EV_SOURCE_ENGINE = 'Electric_300HP'
SAFE_FUEL_LINE_DONORS_BY_VARIANT = {
    'ice_standard': [
        'H2_30HP',
        'FordSmalBlock302_V8_5L_320HP',
        'Ferrari_275_V12_400HP',
    ],
    'ice_compact': [
        'I4_50HP',
        'I4_90HP',
        'I4Sport_150HP',
        'FordSmalBlock302_V8_5L_140HP',
        'FordSmalBlock302_V8_5L_180HP',
        'FordSmalBlock302_V8_5L_240HP',
    ],
    'diesel_hd': [
        'HeavyDuty_260HP',
        'HeavyDuty_350HP',
        'HeavyDuty_440HP',
        'HeavyDuty_540HP',
    ],
    'bike': [
        'Bike_30HP',
        'Bike_50HP',
        'Bike_100HP',
        'Bike_i4_100HP',
        'Bike_i4_160HP',
    ],
    'ev': [
        'Electric_130HP',
        'Electric_300HP',
        'Electric_670HP',
    ],
}
_VANILLA_FUEL_MODEL_CACHE: dict[str, list[dict[str, float | str]]] | None = None
_FAMILY_HP_MODEL_CACHE: dict[str, list[float]] | None = None
COMPACT_BASELINE_PROPS = {
    'Inertia': 2000.0,
    'StarterTorque': 200000.0,
    'FrictionCoulombCoeff': 180000.0,
    'FrictionViscosityCoeff': 450.0,
    'IdleThrottle': 0.005,
    'BlipThrottle': 3.0,
    'BlipDurationSeconds': 0.3,
}
COMPACT_OUTLIER_SIGNATURE = {
    'Inertia': 5200.0,
    'StarterTorque': 200000.0,
    'FrictionCoulombCoeff': 430000.0,
    'FrictionViscosityCoeff': 1050.0,
    'IdleThrottle': 480.0,
}
STANDARD_BASELINE_PROPS = {
    'Inertia': 5000.0,
    'StarterTorque': 200000.0,
    'FrictionCoulombCoeff': 500000.0,
    'FrictionViscosityCoeff': 1000.0,
    'IdleThrottle': 0.0017,
    'HeatingPower': DEFAULT_TEMPLATE_HEATING_POWER,
    'BlipThrottle': 10.0,
    'BlipDurationSeconds': 0.2,
    'AfterFireProbability': 1.0,
}
STANDARD_HEATING_POWER = DEFAULT_TEMPLATE_HEATING_POWER
STANDARD_LEGACY_LAYOUT_FORMAT_HINT = 'standard_v8_legacy'
BIKE_BASELINE_PROPS = {
    'Inertia': 300.0,
    'StarterTorque': 60000.0,
    'StarterRPM': 1500.0,
    'FrictionCoulombCoeff': 45.0,
    'FrictionViscosityCoeff': 300.0,
    'IdleThrottle': 0.00019,
    'HeatingPower': DEFAULT_TEMPLATE_HEATING_POWER,
    'BlipThrottle': 1.52,
    'BlipDurationSeconds': 3.0,
    'AfterFireProbability': 2.0,
}
DIESEL_BASELINE_PROPS = {
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
EV_BASELINE_PROPS = {
    'Inertia': 2000.0,
    'FrictionCoulombCoeff': 100.0,
    'FrictionViscosityCoeff': 100.0,
    'MaxRegenTorqueRatio': 0.3,
}


def fuel_consumption_for(name: str, variant: str, hp: float) -> float:
    """Return a family-normalized FuelConsumption line for this variant and HP."""
    global _VANILLA_FUEL_MODEL_CACHE

    if _VANILLA_FUEL_MODEL_CACHE is None:
        model: dict[str, list[dict[str, float | str]]] = {}
        for fuel_variant, donor_names in SAFE_FUEL_LINE_DONORS_BY_VARIANT.items():
            rows: list[dict[str, float | str]] = []
            for donor_name in donor_names:
                donor_path = os.path.join(VANILLA_DIR, donor_name + '.uexp')
                if not os.path.isfile(donor_path):
                    continue
                engine = parse_engine(open(donor_path, 'rb').read())
                fuel_consumption = float(engine.properties.get('FuelConsumption') or 1.0)
                rows.append({
                    'name': donor_name,
                    'hp': float(round(engine.estimated_hp(), 1)),
                    'fuel_consumption': fuel_consumption,
                })
            model[fuel_variant] = rows
        _VANILLA_FUEL_MODEL_CACHE = model

    rows = list((_VANILLA_FUEL_MODEL_CACHE or {}).get(variant) or [])
    if not rows:
        return 1.0

    family_median = statistics.median(
        float(row['fuel_consumption']) * FUEL_CONSUMPTION_SCALE
        for row in rows
    )
    percentile = family_hp_percentile(variant, hp)
    bounded_scale = 0.8 + (0.4 * percentile)
    return max(MIN_SAFE_FUEL_CONSUMPTION, float(family_median) * bounded_scale)


def _family_hp_values() -> dict[str, list[float]]:
    return {
        'ice_standard': [float(hp) for _name, hp, _rpm, _sound in ICE_STANDARD],
        'ice_compact': [float(hp) for _name, hp, _rpm, _sound in ICE_COMPACT],
        'diesel_hd': [float(hp) for _name, hp, _rpm, _sound in DIESEL_HD],
        'bike': [float(hp) for _name, hp, _rpm, _sound in BIKE],
        'ev': [float(hp) for _name, hp, _rpm, _torque_nm, _power_kw, _voltage_v in EV],
    }


def family_hp_percentile(variant: str, hp: float) -> float:
    """Return a 0..1 percentile for HP within the template family."""
    global _FAMILY_HP_MODEL_CACHE

    if _FAMILY_HP_MODEL_CACHE is None:
        _FAMILY_HP_MODEL_CACHE = {
            key: sorted(values)
            for key, values in _family_hp_values().items()
            if values
        }

    values = list((_FAMILY_HP_MODEL_CACHE or {}).get(variant) or [])
    if len(values) <= 1:
        return 0.5

    target = float(hp)
    if target <= values[0]:
        return 0.0
    if target >= values[-1]:
        return 1.0

    span = float(len(values) - 1)
    for index in range(1, len(values)):
        lo = float(values[index - 1])
        hi = float(values[index])
        if target > hi:
            continue
        if hi <= lo:
            return min(1.0, index / span)
        slot_fraction = (target - lo) / (hi - lo)
        return min(1.0, ((index - 1) + slot_fraction) / span)

    return 1.0


def hp_to_torque_raw(hp: float, rpm: float) -> float:
    """Return raw MaxTorque value (Nm × 10000) for a given HP at peak RPM."""
    return float(round(hp * 9549.0 / (rpm * CURVE_FACTOR) * 10000))


def runtime_diesel_rpm(rpm: float) -> float:
    """Clamp ultra-low industrial diesel RPM values to a game-safe floor."""
    return max(float(rpm), MIN_SAFE_DIESEL_RPM)


def standard_props(name: str, hp: float, rpm: float) -> dict[str, float]:
    return {
        'Inertia': STANDARD_BASELINE_PROPS['Inertia'],
        'StarterTorque': STANDARD_BASELINE_PROPS['StarterTorque'],
        'MaxTorque': hp_to_torque_raw(hp, rpm),
        'MaxRPM': float(rpm),
        'FrictionCoulombCoeff': STANDARD_BASELINE_PROPS['FrictionCoulombCoeff'],
        'FrictionViscosityCoeff': STANDARD_BASELINE_PROPS['FrictionViscosityCoeff'],
        'IdleThrottle': STANDARD_BASELINE_PROPS['IdleThrottle'],
        'FuelConsumption': fuel_consumption_for(name, 'ice_standard', hp),
        'HeatingPower': DEFAULT_TEMPLATE_HEATING_POWER,
        'BlipThrottle': STANDARD_BASELINE_PROPS['BlipThrottle'],
        'BlipDurationSeconds': STANDARD_BASELINE_PROPS['BlipDurationSeconds'],
        'AfterFireProbability': STANDARD_BASELINE_PROPS['AfterFireProbability'],
    }


def diesel_props(hp: float, rpm: float, name: str | None = None) -> dict[str, float]:
    """Build diesel engine properties while preserving target HP after RPM clamping."""
    effective_rpm = runtime_diesel_rpm(rpm)
    return {
        'MaxTorque': hp_to_torque_raw(hp, effective_rpm),
        'MaxRPM': effective_rpm,
        'StarterRPM': min(effective_rpm, 1500.0),
        'FuelConsumption': fuel_consumption_for(name or '', 'diesel_hd', hp),
    }


def kw_to_power_raw(kw: float) -> float:
    """Return raw MotorMaxPower value (kW × 10000)."""
    return float(round(kw * 10000))


def voltage_raw(volts: float) -> float:
    """Return raw MotorMaxVoltage value (V × 10000)."""
    return float(round(volts * 10000))


def hp_to_kw(hp: float) -> float:
    return hp / 1.341


def compact_props(hp: float, rpm: float, name: str | None = None) -> dict[str, float]:
    """Build compact engine properties from the normalized I4Sport baseline."""
    props = dict(COMPACT_BASELINE_PROPS)
    props.update({
        'MaxTorque': hp_to_torque_raw(hp, rpm),
        'MaxRPM': float(rpm),
        'FuelConsumption': fuel_consumption_for(name or '', 'ice_compact', hp),
    })
    return props


def bike_props(hp: float, rpm: float, name: str | None = None) -> dict[str, float]:
    """Build bike properties from the normalized Bike_i4_100HP baseline."""
    props = dict(BIKE_BASELINE_PROPS)
    props.update({
        'MaxTorque': hp_to_torque_raw(hp, rpm),
        'MaxRPM': float(rpm),
        'FuelConsumption': fuel_consumption_for(name or '', 'bike', hp),
    })
    return props


def ev_props(name: str, hp: float, max_rpm: float, torque_nm: float, power_kw: float, voltage_v: float) -> dict[str, float]:
    return {
        'MaxTorque': float(torque_nm * 10000),
        'MaxRPM': float(max_rpm),
        'MotorMaxPower': kw_to_power_raw(power_kw),
        'MotorMaxVoltage': voltage_raw(voltage_v),
        'FuelConsumption': fuel_consumption_for(name, 'ev', hp),
    }


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE LISTS
# Format for ICE/Diesel/Bike: (name, hp, rpm, sound_dir)
# Format for EV:              (name, hp, max_rpm, torque_nm, power_kw, voltage_v)
# ─────────────────────────────────────────────────────────────────────────────

# ── ICE Standard  (cloned from H2_30HP) ──────────────────────────────────────
ICE_STANDARD = [
    # GAME_ENGINE_NAMES  (base-game / original mod engines)
    ('13b',          255,   7000, '13b'),
    ('26b',          700,   9000, '26b'),
    ('73amg',        661,   7100, '73amg'),
    ('81bb',         340,   4200, '81bb'),
    ('81bbt',        490,   5500, '81bb'),
    ('F120A',        720,   8700, 'F120A'),
    ('F120Att',      900,   7500, 'F120A'),
    ('GM572',        620,   6600, 'GM572'),
    ('GM632',       1004,   6800, 'GM632'),
    ('HONDAV10F1',   840,  17300, 'hondaf1'),
    ('L86',          420,   5600, 'L86'),
    ('LT7',         1064,   8600, 'lt7'),
    ('P60B40',       444,   8400, 'P60B40'),
    ('S54B32',       333,   7900, 'S54B32'),
    ('S63B44B',      627,   6000, 'S63B44B'),
    ('S85V10505HP',  500,   7750, 's85'),
    ('SR20DET',      247,   6800, 'SR20DET'),
    ('V10ACR',       645,   6200, 'acr'),
    ('V10ACRt',      900,   6500, 'acr'),
    ('V12_789HP',    778,   8500, '812'),
    ('laferrariV12', 778,   9000, 'laferrariV12'),
    ('lamboV12',     759,   8500, 'lamboV12'),
    ('lexusV10',     552,   8700, 'lexusV10'),
    # ICE Standard new templates — round 1
    ('dodge_viper_gen1',   450,  6000, 'acr'),
    ('am_one77_v12',       750,  7200, '73amg'),
    ('alfa_8c_v8',         444,  7750, 'acr'),
    ('ssc_tuatara_e85',   1750,  8800, 'lt7'),
    ('hennessey_venom_gt',1244,  7200, 'lt7'),
    ('am_db11_amr_v12',    630,  6500, '73amg'),
    # round 2
    ('ls6_454_chevelle',        450,  6000, 'acr'),
    ('ford_427_fe_gt40',        485,  6400, 'acr'),
    ('chrysler_426_hemi',       425,  6400, '392'),
    ('pontiac_ramairiv_400',    370,  6000, 'acr'),
    ('ls7_c6_corvette_z06',     505,  7000, 'acr'),
    ('lt6_c8_corvette_z06',     670,  8600, 'lt7'),
    ('ferrari_enzo_f140b',      651,  8000, 'F120A'),
    ('ferrari_599gto_v12',      661,  8400, 'F120A'),
    ('lambo_murcielago_sv',     661,  8000, 'lamboV12'),
    ('maserati_mc12_v12',       621,  7500, 'F120A'),
    ('am_db9_v12',              510,  6800, '73amg'),
    ('gma_t50_cosworth_v12',    663, 12100, 'lexusV10'),
    ('pagani_zonda_r_v12',      740,  8500, '73amg'),
    ('jaguar_xj220_v6tt',       542,  7200, 'acr'),
    ('bentley_contgt_w12',      616,  6200, None),
    ('ferrari_488pista_f154',   710,  8000, '812'),
    ('amg_gtbs_m178ls2',        720,  7200, 'amg'),
    ('porsche_carrera_gt_v10',  603,  8000, 'lexusV10'),
    ('ford_gt05_54sc',          550,  6500, 'acr'),
    ('shelby_gt500_07_54sc',    500,  6000, 'acr'),
    ('am_valkyrie_cosworth_v12',986, 11100, 'lt7'),
    ('ferrari_360_f131',        395,  8500, '812'),
]

# ── ICE Compact (normalized from I4Sport_150HP baseline) ─────────────────────
# Note: amg_m178_gtr_pro, ferrari_f8_v8, mclaren_m840t are compact-format too
ICE_COMPACT = [
    # GAME_ENGINE_NAMES
    ('20hyundai',             252,  6000, '20hyundai'),
    ('20tfsi',                292,  6200, '20tfsi'),
    ('2JZ320HP',              276,  6800, '2jz'),
    ('50coyote',              480,  7250, '50coyote'),
    ('C63AMG671HP',           710,  6800, 'amg'),
    ('Hemi392_525HP',         485,  6200, '392'),
    ('HemiHellcat_707HP',     717,  6000, '707'),
    ('KoenigseggHV8tt2300HP',1600,  8500, 'hv8'),
    ('KoenigseggV8tt1280HP', 1160,  7800, 'hv8'),
    ('RB26DET276HP',          276,  7300, 'rb26'),
    ('RB26DET350HP',          350,  7500, 'rb26'),
    ('RB26DET440HP',          440,  8000, 'rb26'),
    ('S58',                   503,  6250, 's58'),
    ('S58comp',               530,  6250, 's58comp'),
    ('bugattiW16',           1578,  6700, 'bugattiW16'),
    # ICE Compact new templates — round 1 (+ compact-format ICE Std hybrids)
    ('amg_m178_gtr_pro',      577,  7000, 'amg'),
    ('ferrari_f8_v8',         710,  8000, '812'),
    ('mclaren_m840t',         710,  8500, '812'),
    ('porsche_9a2_gt2rs',     700,  8800, 's85'),
    ('subaru_ej257',          305,  6000, 'SR20DET'),
    ('honda_k20c1',           306,  6500, '20hyundai'),
    ('mitsubishi_4g63t',      286,  6700, 'SR20DET'),
    ('ford_23_ecoboost',      345,  6000, '50coyote'),
    ('porsche_992_cs',        443,  7500, 'acr'),
    ('toyota_gr_yaris',       268,  6500, '20tfsi'),
    ('bmw_n54b30',            302,  6250, 'S54B32'),
    ('nissan_vr38dett',       565,  6800, 'rb26'),
    ('porsche_991_gt3',       469,  8800, None),
    # ICE Compact round 2
    ('honda_f20c_s2000ap1',      237,  9000, '20hyundai'),
    ('honda_f22c_s2000ap2',      240,  8000, '20hyundai'),
    ('honda_k20a_dc5_itr',       217,  8600, '20hyundai'),
    ('honda_k20a2_ep3_ctr',      197,  8100, '20hyundai'),
    ('honda_c30a_nsx',           270,  8000, '20hyundai'),
    ('honda_c32b_nsxr',          290,  8000, '20hyundai'),
    ('toyota_3sgte_g3_mr2',      245,  7000, '2jz'),
    ('lotus_exige_s_2grfze',     345,  7000, 'L86'),
    ('bmw_s65_e92_m3',           414,  8300, 'P60B40'),
    ('bmw_s55_f80_m3m4',         425,  7600, 's58'),
    ('bmw_s14_e30_m3',           192,  7250, 'S54B32'),
    ('audi_ea855_rs3_ttrs',      395,  7000, '20tfsi'),
    ('renault_f4rt_megane_rs250',247,  6500, '20hyundai'),
    ('peugeot_ep6fdt_308gti270', 266,  6000, '20tfsi'),
    ('mazda_l3vdt_mps3',         263,  6700, 'SR20DET'),
    ('vw_ea888_golf_r_mk75',     306,  6200, '20tfsi'),
    ('ford_23eb_focus_rs_mk3',   350,  6900, '50coyote'),
    ('ferrari_california_f136ib',453,  7750, '812'),
    ('porsche_718gt4rs_ma120',   493,  9000, None),
    ('alfa_4c_1750tbi',          237,  6000, '20hyundai'),
]

# ── Diesel HD (cloned from HeavyDuty_540HP) ───────────────────────────────────
DIESEL_HD = [
    # GAME_ENGINE_NAMES
    ('30tdi',               268,  4000, 'LightDiesel'),
    ('59cummins',           305,  2900, '59cummins'),
    ('65detroit',           195,  3400, '65detroit'),
    ('66duramax',           445,  2800, '66duramax'),
    ('73powerstroke',       275,  2800, '73powerstroke'),
    ('CATC12490HP',         490,  2100, 'catc12'),
    ('CumminsX15x565',      565,  1800, 'x15'),
    ('CumminsX15x605',      605,  1800, 'x15'),
    ('CumminsX15x675',      675,  1800, 'x15'),
    ('DV27K1500HP',        1500,  2650, 'DV27K'),
    ('DetroidDD16_600HP',   600,  1800, 'detroit'),
    ('PACCARxMXx13x455',    455,  1900, 'mx13'),
    ('PACCARxMXx13x510',    510,  1900, 'mx13'),
    ('R10',                 650,  5000, 'R10'),
    ('Scania770HP',         770,  1900, '770S'),
    ('ScaniaDC16_530HP',    530,  1900, 'dc16'),
    ('ScaniaDC16_590HP',    590,  1900, 'dc16'),
    ('ScaniaDC16_660HP',    660,  1900, 'dc16'),
    ('ScaniaDC16_770HP',    770,  1900, 'dc16'),
    ('VW19TDI150HP',        150,  4000, 'LightDiesel'),
    ('VolvoD13',            500,  1900, 'd13'),
    ('VolvoD17_600HP',      600,  1800, 'fh'),
    ('VolvoD17_700HP',      700,  1800, 'fh'),
    ('VolvoD17_780HP',      780,  1800, 'fh'),
    ('VolvoD17_780HPs',     780,  1900, 'fh'),
    ('WeichaiWP17H_800HP',  800,  1900, 'fh'),
    ('WeichaiWP17H_800HPs', 800,  1950, 'fh'),
    ('benzI6',              456,  1900, 'benzI6'),
    # Diesel HD new templates — round 1
    ('cat_c15',              550,  2100, 'catc12'),
    ('cat_c18',             1000,  2100, 'catc12'),
    ('navistar_maxxforce13', 500,  2000, 'x15'),
    ('cummins_isx15',        600,  2100, 'x15'),
    ('man_d3876',            640,  1900, 'mx13'),
    ('mercedes_om473',       617,  1800, 'benzI6'),
    ('john_deere_9l',        400,  2200, 'detroit'),
    ('deutz_tcd16_v8',       770,  1900, 'fh'),
    ('detroit_series60',     500,  1800, 'detroit'),
    ('mtu_16v2000',         2400,  2100, 'fh'),
    ('cat_c32',             1200,  1800, 'catc12'),
    ('liebherr_d9508',       603,  1900, 'fh'),
    ('liebherr_d9512',      1140,  1900, 'fh'),
    ('perkins_2806',         996,  2100, 'fh'),
    ('iveco_cursor13',       540,  2100, 'benzI6'),
    # Diesel HD round 2
    ('paccar_mx11_445',     445,  1800, 'mx13'),
    ('daf_mx13_530',        530,  1900, 'mx13'),
    ('scania_dc13_500',     493,  1800, 'dc16'),
    ('scania_dc13_450',     444,  1800, 'dc16'),
    ('man_d2676_500',       493,  1950, 'mx13'),
    ('volvo_d16g700',       690,  2000, 'd13'),
    ('volvo_d13_500',       493,  2000, 'd13'),
    ('cummins_x12_500',     500,  1900, 'x15'),
    ('cummins_qsk19_800',   800,  1800, 'x15'),
    ('cummins_qsk23_950',   950,  2100, 'x15'),
    ('cummins_qsk38_1600', 1600,  1800, 'x15'),
    ('cummins_qsk60_2300', 2300,  1900, 'x15'),
    ('cummins_qsk78_3500', 3500,  1900, 'x15'),
    ('cat_3516_2000',      2000,  1800, 'catc12'),
    ('cat_3608_3300',      3300,  1000, 'catc12'),
    ('cat_3616_6600',      6600,  1000, 'catc12'),
    ('mtu_16v4000_2935',   2935,  1800, 'fh'),
    ('mtu_16v2000_2600',   2600,  2450, 'fh'),
    ('wartsila_32_12500', 12475,   750, None),
    ('wartsila_46f_20000',20000,   600, None),
    ('bergen_b3240_v16',   8000,   750, None),
]

# ── Motorcycle (normalized against Bike_i4_100HP) ─────────────────────────────
BIKE = [
    # GAME_ENGINE_NAMES bikes
    ('999r_150HP',              150,   9750, None),
    ('999r_150HPtuned',         175,  10500, None),
    ('Bike_i4_250HP',           250,  12000, None),
    ('Bike_i4_250HPtuned',      300,  13500, None),
    ('bandit1250145HP',         145,   9000, None),
    ('bandit1250tuned200HP',    200,  10000, None),
    ('cbr600rr120HP',           120,  13500, None),
    ('cbr600rrtuned160HP',      160,  14500, None),
    ('gpproto240HP',            240,  16000, None),
    ('gpprototuned320HP',       320,  17000, None),
    ('harley_120HP',            120,   5500, None),
    ('harley_120HPtuned',       150,   5800, None),
    ('hayabusa_200HP',          197,   9500, None),
    ('hayabusa_200HPtuned',     240,  10500, None),
    ('panigale1199170HP',       195,  11000, None),
    ('panigale1199tuned230HP',  230,  12000, None),
    ('r750140HP',               148,  14000, None),
    ('r750tuned190HP',          190,  15000, None),
    ('sportster120065HP',        70,   5500, None),
    ('sportster1200tuned90HP',   90,   6000, None),
    ('sv65070HP',                73,   9800, None),
    ('sv650tuned95HP',           95,  10500, None),
    ('zzr1400200HP',            200,  10500, None),
    ('zzr1400tuned270HP',       270,  11500, None),
    # New bike templates — round 1
    ('bmw_s1000rr',          210,  13500, None),
    ('honda_cbr1000rr_r',    215,  14500, None),
    ('kawasaki_h2',          228,  11500, None),
    ('kawasaki_h2r',         310,  14000, None),
    ('yamaha_r1m',           200,  13500, None),
    ('aprilia_rsv4',         217,  13200, None),
    ('mv_agusta_f4rr',       200,  13600, None),
    ('ducati_panigale_v4r',  221,  15250, None),
    ('ktm_1290_super_duke',  180,   9500, None),
    ('triumph_rocket3',      167,   6000, None),
    ('norton_v4cr',          185,  12500, None),
    ('indian_ftr1200',       121,   8250, None),
    ('bimota_tesi_h2',       228,  11500, None),
    # New bike templates — round 2
    ('kawasaki_zx10r',               203,  14000, None),
    ('kawasaki_zx6r_636',            122,  14000, None),
    ('kawasaki_z900',                124,  10500, None),
    ('ducati_streetfighter_v4',      208,  14000, None),
    ('ducati_panigale_v2',           155,  11500, None),
    ('yamaha_r7',                     73,   9000, None),
    ('yamaha_mt10',                  164,  12000, None),
    ('yamaha_tracer9',               115,  10500, None),
    ('honda_cbr600rr_2024',          119,  15000, None),
    ('triumph_daytona660',            94,  12650, None),
    ('triumph_speed_triple_1200',    180,  10750, None),
    ('aprilia_tuono_v4',             175,  11500, None),
    ('bmw_k1600',                    158,   7500, None),
    ('bmw_r18',                       91,   5750, None),
    ('bmw_f900r',                    105,   9000, None),
    ('suzuki_gsx_s1000',             150,  12000, None),
    ('suzuki_vstrom1050',            107,   9000, None),
    ('ktm_890_duke',                 121,  10000, None),
    ('ktm_1290_super_adv',           158,   9500, None),
    ('ktm_rc390',                     43,  10000, None),
    ('harley_pan_america',           150,   9500, None),
    ('moto_guzzi_v100',              115,   9500, None),
    ('indian_scout_1250',            111,   7500, None),
    ('royal_enfield_interceptor650',  47,   7500, None),
    ('royal_enfield_himalayan450',    40,   8500, None),
]

# ── EV (cloned from Electric_670HP) ──────────────────────────────────────────
# Format: (name, hp_sae, max_rpm, torque_nm, power_kw, voltage_v)
EV = [
    ('EVAlpineA290',                    218,  15000,   300,   163,  400),
    ('EVAsparkOwl',                    1985,  15000,  2000,  1480,  800),
    ('EVAudiRSetronGTPerformance',      641,  16000,   830,   478,  800),
    ('EVChevroletBoltEV',              200,   8000,   360,   149,  400),
    ('EVChevroletSilveradoEVWT',       510,  10000,   780,   380,  800),
    ('EVDrakoDragon',                 1200,  15000,  1500,   895,  800),
    ('EVElationFreedom',               671,  14000,   950,   500,  800),
    ('EVFiskerOceanUltra',             564,  12000,   720,   420,  800),
    ('EVGACAionHyperSSR',            1225,  20000,  1850,   913,  800),
    ('EVGMCHummerEV',                1000,   8000,  1627,   746,  800),
    ('EVHyundaiIoniq9',               303,  12000,   620,   226,  800),
    ('EVLotusEvija',                 2000,  20000,  1700,  1491,  800),
    ('EVLucidAirGrandTouringPerformance', 1050, 21000, 1500, 783, 900),
    ('EVLucidAirSapphire',           1234,  21000,  1600,   920,  900),
    ('EVLucidGravityDreamEdition',    828,  18000,  1200,   617,  900),
    ('EVMGMG4EV',                     201,  14000,   250,   150,  400),
    ('EVMHero917',                   1218,  21000,  1100,   908,  800),
    ('EVMercedesAMGGTXXConcept',     2011,  20000,  1750,  1500,  900),
    ('EVMercedesEQS450Plus',          329,  14000,   568,   245,  400),
    ('EVNIOEP9',                     1341,  18000,  1480,  1000,  900),
    ('EVNIOET5',                      489,  15000,   700,   365,  400),
    ('EVNetGainHyper9',                80,   7000,   180,    60,   96),
    ('EVPininfarinaBattista',         1900,  20000,  2340,  1417,  800),
    ('EVPolestar2DualMotor',          476,  15000,   740,   355,  400),
    ('EVPolestar3LongRangeSingleMotor',315, 14000,   490,   235,  800),
    ('EVPorscheTaycanTurboS',         761,  16000,  1050,   568,  800),
    ('EVRimacNevera',                1888,  20000,  2360,  1408,  800),
    ('EVRimacNeveraR',               2107,  20000,  2600,  1571,  800),
    ('EVRivianR1TQuadMotorGen1',      835,  13000,  1231,   623,  800),
    ('EVTataTiagoEV',                  74,  10000,   155,    55,  320),
    ('EVTeslaModelSPlaid',           1020,  20000,  1420,   761,  400),
    ('EVTeslaModelXPlaid',           1020,  20000,  1420,   761,  400),
    ('EVTeslaSemi',                   800,  12000,  2000,   597, 1000),
    ('EVVinFastVFe34',                201,  13000,   242,   150,  400),
    ('EVVolvoEX30',                   268,  14000,   343,   200,  400),
    ('EVWulingHongguangMiniEV',        20,   8000,    85,    15,   48),
    ('EVYangwangU9TrackEdition',     1287,  20000,  1680,   960,  800),
]


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE CREATION HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _make_engine(src_uasset: str, src_uexp: str,
                 name: str, properties: dict,
                 sound_dir=None) -> bool:
    """Clone src → name with modified properties.  Returns True on success."""
    out_uexp   = os.path.join(MOD_DIR, name + '.uexp')
    out_uasset = os.path.join(MOD_DIR, name + '.uasset')

    if os.path.isfile(out_uexp):
        print(f"  SKIP  {name:40s} (already exists)")
        return True

    with open(src_uexp, 'rb') as f:
        data = f.read()

    try:
        engine = parse_engine(data)
    except Exception as e:
        print(f"  ERR   {name:40s} parse: {e}")
        return False

    for key, val in properties.items():
        if key in engine.properties:
            engine.properties[key] = val
        else:
            print(f"  WARN  {name:40s} property '{key}' not in parsed engine")

    new_data = serialize_engine(engine)
    if len(new_data) != len(data):
        print(f"  ERR   {name:40s} size mismatch {len(new_data)} vs {len(data)}")
        return False

    try:
        clone_uasset(src_uasset, name, out_uasset, sound_dir=sound_dir)
    except Exception as e:
        print(f"  ERR   {name:40s} uasset clone: {e}")
        return False

    with open(out_uexp, 'wb') as f:
        f.write(new_data)

    hp = engine.estimated_hp() if hasattr(engine, 'estimated_hp') else '?'
    try:
        hp = round(engine.estimated_hp(), 1)
    except Exception:
        hp = '?'
    print(f"  NEW   {name:40s}  {hp!s:>8} HP")
    return True


def _vanilla(fname_no_ext: str) -> tuple:
    """Return (uasset_path, uexp_path) for a vanilla engine."""
    return (
        os.path.join(VANILLA_DIR, fname_no_ext + '.uasset'),
        os.path.join(VANILLA_DIR, fname_no_ext + '.uexp'),
    )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def _print_audit_summary(audit: dict) -> None:
    legacy = audit.get('legacy_bike_names', [])
    if legacy:
        preview = ', '.join(legacy[:5])
        extra = '' if len(legacy) <= 5 else f' (+{len(legacy) - 5} more)'
        print(f"  ERR   Legacy bike layouts remain: {preview}{extra}")
    elif audit.get('warnings'):
        preview = '; '.join(audit['warnings'][:3])
        extra = '' if len(audit['warnings']) <= 3 else f' (+{len(audit["warnings"]) - 3} more)'
        print(f"  WARN  Audit warnings: {preview}{extra}")


def main() -> int:
    os.makedirs(MOD_DIR, exist_ok=True)

    created = skipped = errors = 0

    # ── ICE Standard ─────────────────────────────────────────────────────────
    print(f"\n── ICE Standard ({STANDARD_SOURCE_ENGINE} template) ──")
    src_ua, src_ue = _vanilla(STANDARD_SOURCE_ENGINE)
    for name, hp, rpm, sound in ICE_STANDARD:
        props = standard_props(name, hp, rpm)
        ok = _make_engine(src_ua, src_ue, name, props, sound_dir=sound)
        if ok:
            if os.path.isfile(os.path.join(MOD_DIR, name + '.uexp')):
                created += 1
            else:
                skipped += 1
        else:
            errors += 1

    # ── ICE Compact ──────────────────────────────────────────────────────────
    print(f"\n── ICE Compact ({COMPACT_SOURCE_ENGINE} baseline) ──")
    src_ua, src_ue = _vanilla(COMPACT_SOURCE_ENGINE)
    for name, hp, rpm, sound in ICE_COMPACT:
        props = compact_props(hp, rpm, name=name)
        ok = _make_engine(src_ua, src_ue, name, props, sound_dir=sound)
        if ok:
            created += 1
        else:
            errors += 1

    # ── Diesel HD ─────────────────────────────────────────────────────────────
    print(f"\n── Diesel HD ({DIESEL_SOURCE_ENGINE} template) ──")
    src_ua, src_ue = _vanilla(DIESEL_SOURCE_ENGINE)
    for name, hp, rpm, sound in DIESEL_HD:
        props = diesel_props(hp, rpm, name=name)
        ok = _make_engine(src_ua, src_ue, name, props, sound_dir=sound)
        if ok:
            created += 1
        else:
            errors += 1

    # ── Motorcycles ──────────────────────────────────────────────────────────
    print(f"\n── Motorcycle ({BIKE_SOURCE_ENGINE} baseline) ──")
    src_ua, src_ue = _vanilla(BIKE_SOURCE_ENGINE)
    for name, hp, rpm, sound in BIKE:
        props = bike_props(hp, rpm, name=name)
        ok = _make_engine(src_ua, src_ue, name, props, sound_dir=sound)
        if ok:
            created += 1
        else:
            errors += 1

    # ── Electric Vehicles ────────────────────────────────────────────────────
    print(f"\n── EV ({EV_SOURCE_ENGINE} template) ──")
    src_ua, src_ue = _vanilla(EV_SOURCE_ENGINE)
    for name, hp, max_rpm, torque_nm, power_kw, voltage_v in EV:
        props = ev_props(name, hp, max_rpm, torque_nm, power_kw, voltage_v)
        ok = _make_engine(src_ua, src_ue, name, props, sound_dir=None)
        if ok:
            created += 1
        else:
            errors += 1

    total = len(ICE_STANDARD) + len(ICE_COMPACT) + len(DIESEL_HD) + len(BIKE) + len(EV)
    print(f"\n── Done: {created} created / {skipped} skipped / {errors} errors  "
          f"(total defined: {total}) ──")
    audit = audit_engine_value_consistency(
        MOD_DIR,
        standard_baseline=STANDARD_BASELINE_PROPS,
        required_standard_heating_power=STANDARD_HEATING_POWER,
        forbidden_standard_format_hint=STANDARD_LEGACY_LAYOUT_FORMAT_HINT,
        compact_baseline=COMPACT_BASELINE_PROPS,
        compact_outlier_signature=COMPACT_OUTLIER_SIGNATURE,
        bike_baseline=BIKE_BASELINE_PROPS,
        diesel_baseline=DIESEL_BASELINE_PROPS,
        ev_baseline=EV_BASELINE_PROPS,
        min_fuel_consumption=MIN_SAFE_FUEL_CONSUMPTION,
    )
    _print_audit_summary(audit)
    if not audit['valid']:
        print("\n── Audit failed ──")
        for message in audit['errors'][:10]:
            print(f"  ERR   {message}")
        if len(audit['errors']) > 10:
            print(f"  ERR   (+{len(audit['errors']) - 10} more)")
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
