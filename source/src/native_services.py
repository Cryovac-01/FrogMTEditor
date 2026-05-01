"""Service and typed data helpers shared by desktop-facing editors."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from desktop_view_models import (
    AssetDocument,
    ConflictState,
    PackPreview,
    TemplateCatalog,
    WorkspaceSummary,
)

from api.routes import (
    DEFAULT_CUSTOM_PAK_FILENAME,
    DEFAULT_PAKS_DIR,
    _current_live_state,
    create_engine,
    create_tire,
    delete_engine,
    delete_tire,
    get_engine_audio_manifest,
    get_engine_templates,
    get_part_detail,
    get_parts_list,
    get_tire_templates,
    list_sounds,
    pack_mod,
    pack_templates,
    prepare_engine_audio_workspace,
    recommend_engine_price,
    save_part,
    set_engine_audio_override,
)


DEFAULT_TEMPLATE_PAK_FILENAME = "ZZZ_FrogTemplates_P.pak"

VARIANT_LABELS = {
    "ice": "Gasoline",
    "ice_standard": "ICE Standard",
    "ice_compact": "ICE Compact",
    "diesel": "Diesel",
    "diesel_hd": "Diesel HD",
    "bike": "Motorcycle",
    "ev": "Electric",
}

PROPERTY_DESCRIPTIONS = {
    # ── Engine: Performance ───────────────────────────────────────────
    "MaxTorque": (
        "Peak crank torque in N·m (displayed after ÷10,000 conversion from the raw asset value). "
        "This is the single biggest factor in how powerful the engine feels. "
        "Vanilla range: ~12 N·m (Scooter 10 HP) up to ~1,500 N·m (HeavyDuty 540 HP). "
        "Typical car engines sit between 80–520 N·m. The editor warns above 2,000 N·m and blocks "
        "above 50,000 N·m. Must be greater than zero for ICE engines."
    ),
    "MaxRPM": (
        "Maximum operating RPM (redline). Determines how high the engine can rev. "
        "The editor enforces a hard range of 2,000–14,000 RPM and warns outside 2,800–10,000 "
        "(below 2,000 most engines break or freeze in-game; above 14,000 the simulation becomes "
        "unstable). Typical gas engines sit at 6,000–8,000. Sport bikes can legitimately reach "
        "10,000–13,000. Note: vanilla EV engines ship at 21,000 RPM, which exceeds the editor's "
        "hard cap — to fork an EV donor you'll need to bring MaxRPM down to ≤14,000 first."
    ),
    "TorqueCurve": (
        "Internal UE5 import reference (read-only). The negative number (e.g. -2) is a package "
        "index pointing to the torque-curve asset that shapes how torque is distributed across "
        "the RPM band. You cannot edit this value directly — it is set by the template. "
        "The curve determines the torque 'shape' (peaky vs flat), while MaxTorque sets the peak height."
    ),
    "MotorMaxPower": (
        "EV-only peak motor output in kW (displayed after ÷10,000 conversion). "
        "Vanilla range: 230 kW (Electric 130 HP) to 505 kW (Electric 670 HP). "
        "The editor warns outside 50–1,000 kW and blocks above 10,000 kW. "
        "This is the primary power stat for electric motors. Must be greater than zero for EVs."
    ),
    "MotorMaxVoltage": (
        "EV-only maximum system voltage in volts (displayed after ÷10,000 conversion). "
        "Vanilla range: 200 V to 670 V. Higher voltage generally pairs with higher power output. "
        "The editor warns outside 100–1,000 V and blocks outside 12–10,000 V."
    ),
    "MotorMaxRPM": (
        "Motor speed ceiling for EV layouts that expose it. "
        "If present, this caps the motor's maximum rotational speed independently of MaxRPM. "
        "The editor warns outside 2,500–25,000 RPM and blocks outside 600–50,000 RPM. "
        "Note: the MaxRPM field has a separate, tighter cap of 14,000."
    ),
    "MaxRegenTorqueRatio": (
        "EV regenerative braking strength as a ratio. "
        "Vanilla value: 0.3 on all stock EVs. Higher values give stronger regen braking. "
        "The editor warns above 1.0 (untested territory) and blocks above 5.0."
    ),

    # ── Engine: Start and Idle ────────────────────────────────────────
    "StarterTorque": (
        "Torque applied by the starter motor while cranking the engine, in raw asset units. "
        "Vanilla range: 20,000 (bikes/scooters) to 3,000,000 (heavy diesel). "
        "Typical gas engines: 200,000. The editor warns outside 10,000–3,500,000 and blocks "
        "above 10,000,000. Too low and the engine won't crank reliably."
    ),
    "StarterRPM": (
        "Target RPM the starter tries to reach before the engine catches and starts running. "
        "Vanilla value: 1,500 on diesels and modern bikes. Must be lower than MaxRPM. "
        "The editor warns outside 500–3,000 and blocks outside 100–20,000. "
        "Not present on all layouts — legacy bike and compact layouts may omit it."
    ),
    "IdleThrottle": (
        "Minimum throttle opening that keeps the engine running at idle. "
        "IMPORTANT: the scale varies dramatically by layout type. "
        "Compact/standard gas: ~0.002–0.005 (very small fractional values). "
        "Modern bikes: ~0.0002. Diesels: ~0.017. "
        "DANGER: on compact layouts, values above 1.0 cause the vehicle to creep forward "
        "without any throttle input (the retired V6Sport had 480 — do not use values like that). "
        "The editor blocks anything above 1.0 to prevent this failure mode."
    ),
    "BlipThrottle": (
        "Throttle amount used for automatic rev-match blips during downshifts. "
        "Vanilla range: 1.0 (scooter/bike) to 10.0 (V8s). Typical gas engines: 3.0–5.0. "
        "The editor warns outside 0.5–10.0 and blocks above 50.0. "
        "Higher values make downshift blips more aggressive and audible."
    ),
    "BlipDurationSeconds": (
        "Duration of the rev-match blip in seconds. "
        "Vanilla range: 0.2–0.5 s for gas engines, up to 3.0 s for bikes. "
        "Some older compact layouts store NaN here, which the game treats as a default. "
        "The editor warns outside 0.1–3.0 s and blocks above 10.0 s."
    ),

    # ── Engine: Friction and Fuel ─────────────────────────────────────
    "Inertia": (
        "Rotational inertia of the engine assembly (flywheel, crank, etc.) in raw units. "
        "Controls how quickly the engine revs up and down — higher = slower response. "
        "Vanilla range: 80 (scooter) to 50,000 (heavy diesel). "
        "Typical gas engines: 1,200–5,200. Bikes: 300–350. EVs: 2,000–3,000. "
        "The editor warns outside 80–60,000 and blocks above 100,000. Must be greater than "
        "zero. Too low makes the engine feel twitchy; too high makes it feel sluggish."
    ),
    "FrictionCoulombCoeff": (
        "Constant mechanical drag from bearings, seals, and baseline friction. "
        "Always present as a positive number — acts as a flat drag regardless of RPM. "
        "Vanilla range: 50 (bikes/EVs) to 2,500,000 (heavy diesel). "
        "Typical gas engines: 180,000–500,000. The editor warns outside 50–3,000,000 and "
        "blocks above 10,000,000. Higher values make the engine lose more power to friction."
    ),
    "FrictionViscosityCoeff": (
        "RPM-dependent drag from oil shear, pumping losses, and windage. "
        "This drag increases with engine speed — higher values punish high-RPM performance. "
        "Vanilla range: 10 (scooter) to 6,000 (heavy diesel). "
        "Typical gas engines: 450–1,050. Bikes: 330–500. EVs: 100. "
        "The editor warns outside 10–6,500 and blocks above 20,000."
    ),
    "FuelConsumption": (
        "Base fuel-use scalar. Higher values = more fuel consumed for a given power output. "
        "Vanilla range: 3 (scooter) to 670 (Electric 670 HP — yes, EVs use this too for energy drain). "
        "Typical gas engines: 90–320, roughly correlating with HP. Diesels: 260–540. "
        "The editor warns outside 3–700 and blocks above 10,000. Must be greater than zero "
        "or the engine won't consume fuel at all."
    ),
    "FuelType": (
        "Fuel type enum used by the game. Determines which fuel the engine uses at gas stations. "
        "Values: 0 = Gas (legacy, behaves like 1), 1 = Gasoline, 2 = Diesel, 3 = Electric. "
        "Must match the engine variant — diesel engines should be 2, EVs should be 3."
    ),

    # ── Engine: Thermal and Effects ───────────────────────────────────
    "HeatingPower": (
        "Explicit heat-generation term. Only present on some layouts (standard V8s, bikes). "
        "Vanilla bikes: ~1.15–1.17. When present, this affects engine temperature buildup. "
        "The template policy keeps this low where supported and structurally absent otherwise. "
        "The editor warns above 5.0 and blocks above 100.0."
    ),
    "AfterFireProbability": (
        "Decel pop / afterfire (backfire) probability scalar. "
        "Controls how likely the engine is to produce popping sounds on deceleration. "
        "Vanilla: 1.0 on engines that have it (V8s, bikes). 0.0 = no pops, 1.0 = frequent pops. "
        "The editor warns above 1.0 (untested but may increase frequency further) and blocks "
        "above 10.0."
    ),

    # ── Engine: Diesel-Specific ───────────────────────────────────────
    "IntakeSpeedEfficiency": (
        "Diesel/heavy-duty airflow efficiency term (reverse-engineered). "
        "Appears to affect breathing and power delivery under speed and load. "
        "Vanilla value: 1.0 on all observed diesels. The editor warns outside 0.5–2.0 and "
        "blocks above 20.0. Deviating far from 1.0 may produce unpredictable power behavior."
    ),
    "MaxJakeBrakeStep": (
        "Maximum jake-brake (engine brake) strength in discrete steps. Diesel-only. "
        "Vanilla value: 3 on all observed heavy-duty diesels. "
        "Integer values only. The editor warns above 5 and blocks above 50. "
        "Higher values allow stronger engine-braking when activated in-game."
    ),
    "EngineType": (
        "Diesel-specific engine classification enum stored as a raw integer. "
        "Vanilla value: 2 on heavy-duty diesels. The full enum mapping is only partially decoded. "
        "It is safest to leave this at the template default unless you know the mapping."
    ),

    # ── Tire Properties ───────────────────────────────────────────────
    "GripMultiplier": (
        "Offroad grip adjustment as a percentage offset. "
        "0 = baseline behavior. Positive values add offroad grip, negative values reduce it. "
        "Stored internally as a multiplier. Typical range: -50 to +100."
    ),
    "LateralStiffness": "Base sideways carcass stiffness. Higher values resist lateral deformation more strongly.",
    "LongStiffness": "Base longitudinal stiffness for traction and braking load.",
    "LongSlipStiffness": "Longitudinal slip response term. Shapes how quickly the tire reacts as it starts spinning or locking.",
    "CorneringStiffness": "Primary slip-angle cornering force term. Higher values usually increase lateral bite once the tire takes a set.",
    "LoadRating": "Nominal supported load rating for the tire.",
    "MaxLoad": "Upper supported load limit before the tire is outside its intended operating range.",
    "MaxSpeed": "Rated top speed for the tire layout.",
    "RollingResistance": "Rolling drag term. Lower values usually help top speed and efficiency.",
    "WearRate": "Primary wear scalar for normal running conditions.",
    "WearRate2": "Secondary wear scalar on richer tire layouts. Reverse engineered and likely adds extra wear behavior.",
    "ThermalSensitivity": "Thermal response scalar. Higher values appear to make grip change more aggressively with temperature.",
    "TireTemperature": "Explicit tire operating temperature field on richer layouts.",
    "CamberStiffness": "Camber-related cornering contribution. The editor uses this in the quick grip estimate as Cornering Stiffness + Camber Stiffness / 2.",
    "TreadDepth": "Additional tread-depth field used on richer layouts. Likely tied to off-road bite, wet behavior, and wear reserve.",
}

ENGINE_GROUPS = (
    ("Performance", {
        "TorqueCurve",
        "MaxTorque",
        "MaxRPM",
        "MotorMaxPower",
        "MotorMaxVoltage",
        "MotorMaxRPM",
        "MaxRegenTorqueRatio",
    }),
    ("Start and Idle", {
        "StarterTorque",
        "StarterRPM",
        "IdleThrottle",
        "BlipThrottle",
        "BlipDurationSeconds",
    }),
    ("Friction and Fuel", {
        "Inertia",
        "FrictionCoulombCoeff",
        "FrictionViscosityCoeff",
        "FuelConsumption",
        "FuelType",
    }),
    ("Thermal and Effects", {
        "HeatingPower",
        "AfterFireProbability",
    }),
    ("Diesel and Brake", {
        "IntakeSpeedEfficiency",
        "MaxJakeBrakeStep",
        "EngineType",
    }),
)

TIRE_GROUPS = (
    ("Grip and Slip", {
        "GripMultiplier",
        "LateralStiffness",
        "CorneringStiffness",
        "CamberStiffness",
        "LongStiffness",
        "LongSlipStiffness",
    }),
    ("Load and Speed", {
        "LoadRating",
        "MaxLoad",
        "MaxSpeed",
        "RollingResistance",
    }),
    ("Wear and Thermal", {
        "WearRate",
        "WearRate2",
        "ThermalSensitivity",
        "TireTemperature",
        "TreadDepth",
    }),
)

READONLY_FIELDS = {"TorqueCurve", "NumKeys", "_error"}
PROPERTY_LABEL_OVERRIDES = {
    "MaxRPM": "Max RPM",
    "StarterRPM": "Starter RPM",
    "MotorMaxRPM": "Motor Max RPM",
    "MaxTorque": "Max Torque",
    "TorqueCurve": "Torque Curve",
    "MaxRegenTorqueRatio": "Max Regen Torque Ratio",
    "MotorMaxPower": "Motor Max Power",
    "MotorMaxVoltage": "Motor Max Voltage",
    "FrictionCoulombCoeff": "Friction Coulomb Coeff",
    "FrictionViscosityCoeff": "Friction Viscosity Coeff",
    "FuelConsumption": "Fuel Consumption",
    "FuelType": "Fuel Type",
    "AfterFireProbability": "AfterFire Probability",
    "GripMultiplier": "Offroad +/- %",
    "LateralStiffness": "Lateral Stiffness",
    "CorneringStiffness": "Cornering Stiffness",
    "CamberStiffness": "Camber Stiffness",
    "LongStiffness": "Long Stiffness",
    "LongSlipStiffness": "Long Slip Stiffness",
    "LoadRating": "Load Rating",
    "MaxLoad": "Max Load",
    "MaxSpeed": "Max Speed",
    "RollingResistance": "Rolling Resistance",
    "WearRate": "Wear Rate",
    "WearRate2": "Wear Rate 2",
    "ThermalSensitivity": "Thermal Sensitivity",
    "TireTemperature": "Tire Temperature",
    "TreadDepth": "Tread Depth",
}


def parse_optional_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        text = str(value).strip()
        if not text:
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


def is_readonly_property(key: str, part_type: str) -> bool:
    return key in READONLY_FIELDS or key.endswith("_InterpMode")


def format_property_name(key: str) -> str:
    text = str(key or "")
    if not text:
        return ""
    override = PROPERTY_LABEL_OVERRIDES.get(text)
    if override:
        return override
    text = text.replace("_", " ").strip()
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    text = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", text)
    return text[:1].upper() + text[1:] if text else ""


def get_edit_value(key: str, prop: Dict[str, Any], part_type: str) -> str:
    if not isinstance(prop, dict):
        return str(prop or "")
    if prop.get("editable") is False and prop.get("display", "") != "":
        return str(prop.get("display", ""))
    if part_type == "tire" and key == "GripMultiplier":
        return str(prop.get("display", ""))
    if part_type == "engine" and key in {"MaxTorque", "MotorMaxPower", "MotorMaxVoltage"}:
        return str(prop.get("display", ""))
    raw = prop.get("raw")
    if isinstance(raw, str):
        return raw
    if isinstance(raw, int):
        return str(raw)
    if isinstance(raw, float):
        return str(float(f"{raw:.6g}"))
    display = prop.get("display")
    if display is None:
        return ""
    return str(display)


def categorize_properties(part_type: str, properties: Dict[str, Any]) -> List[tuple[str, List[tuple[str, Dict[str, Any]]]]]:
    definitions = ENGINE_GROUPS if part_type == "engine" else TIRE_GROUPS if part_type == "tire" else ()
    grouped: List[tuple[str, List[tuple[str, Dict[str, Any]]]]] = []
    assigned: set[str] = set()

    for title, keys in definitions:
        bucket = [(key, properties[key]) for key in properties if key in keys]
        if bucket:
            grouped.append((title, bucket))
            assigned.update(key for key, _ in bucket)

    remaining = [(key, properties[key]) for key in properties if key not in assigned]
    if remaining:
        grouped.append(("Other", remaining))
    return grouped


def _flatten_parts(raw: Dict[str, Any]) -> Dict[str, Any]:
    groups = raw.get("parts", {}) if isinstance(raw, dict) else {}
    items: List[Dict[str, Any]] = []
    for part_type, rows in groups.items():
        for row in rows or []:
            item = dict(row)
            item["part_type"] = str(part_type).lower()
            item["title"] = row.get("name", "")
            items.append(item)
    items.sort(key=lambda item: (str(item.get("part_type", "")), str(item.get("name", "")).lower()))
    return {
        "items": items,
        "count": len(items),
        "state_version": raw.get("state_version", ""),
        "engine_count": raw.get("engine_count", 0),
        "tire_count": raw.get("tire_count", 0),
        "part_count": raw.get("part_count", len(items)),
        "groups": groups,
    }


def _flatten_engine_templates(raw: Dict[str, Any]) -> Dict[str, Any]:
    groups = raw.get("templates", {}) if isinstance(raw, dict) else {}
    flat: List[Dict[str, Any]] = []
    group_items: List[Dict[str, Any]] = []
    for group_key, group in groups.items():
        group = group or {}
        group_items.append({
            "key": group_key,
            "label": group.get("label", group_key),
            "variant": group.get("variant", ""),
            "properties": list(group.get("properties", [])),
            "count": len(group.get("engines", [])),
        })
        for engine in group.get("engines", []):
            item = dict(engine)
            item["group_key"] = group_key
            item["group_label"] = group.get("label", group_key)
            item["variant"] = group.get("variant", item.get("variant", ""))
            flat.append(item)
    flat.sort(key=lambda item: (str(item.get("group_label", "")).lower(), str(item.get("title", item.get("name", ""))).lower()))
    group_items.sort(key=lambda item: str(item.get("label", "")).lower())
    return {
        "groups": group_items,
        "items": flat,
        "count": len(flat),
        "audit": raw.get("audit"),
    }


def _flatten_tire_templates(raw: Dict[str, Any]) -> Dict[str, Any]:
    groups = raw.get("templates", {}) if isinstance(raw, dict) else {}
    flat: List[Dict[str, Any]] = []
    group_items: List[Dict[str, Any]] = []
    for group_key, group in groups.items():
        group = group or {}
        group_items.append({
            "key": group_key,
            "label": group.get("label", format_property_name(group_key)),
            "properties": list(group.get("properties", [])),
            "count": len(group.get("tires", [])),
        })
        for tire in group.get("tires", []):
            item = dict(tire)
            item["group_key"] = group_key
            item["group_label"] = group.get("label", format_property_name(group_key))
            flat.append(item)
    flat.sort(key=lambda item: (str(item.get("group_label", "")).lower(), str(item.get("title", item.get("name", ""))).lower()))
    group_items.sort(key=lambda item: str(item.get("label", "")).lower())
    return {
        "groups": group_items,
        "items": flat,
        "count": len(flat),
    }


def get_tire_field_coverage(part: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not part or part.get("type") != "tire":
        return None
    metadata = part.get("metadata") or {}
    properties = part.get("properties") or {}
    supported = list(metadata.get("supported_properties") or properties.keys())
    supported_set = set(supported)
    known = list(metadata.get("known_properties") or supported)
    possible = list(metadata.get("possible_properties") or known)
    missing_possible = list(metadata.get("missing_possible_properties") or [name for name in possible if name not in supported_set])
    missing_known = list(metadata.get("missing_known_properties") or [name for name in known if name not in supported_set])
    return {
        "supported": supported,
        "possible": possible,
        "known": known,
        "missing_possible": missing_possible,
        "missing_known": missing_known,
        "group_label": metadata.get("group_label", ""),
        "property_count": int(metadata.get("property_count") or len(supported)),
        "possible_count": int(metadata.get("possible_property_count") or len(possible)),
        "known_count": int(metadata.get("known_property_count") or len(known)),
    }


def estimate_tire_grip_g(part: Dict[str, Any], property_values: Optional[Dict[str, Any]] = None) -> Optional[float]:
    property_values = property_values or {}

    def read_value(key: str) -> Optional[float]:
        if key in property_values:
            return parse_optional_number(property_values.get(key))
        prop = (part.get("properties") or {}).get(key)
        if not isinstance(prop, dict):
            return None
        raw = prop.get("raw")
        if isinstance(raw, (int, float)):
            return float(raw)
        return parse_optional_number(prop.get("display"))

    cornering = read_value("CorneringStiffness")
    camber = read_value("CamberStiffness")
    if cornering is None and camber is None:
        return None
    grip = (cornering or 0.0) + ((camber or 0.0) / 2.0)
    return round(grip, 2)


def build_engine_state(
    part: Dict[str, Any],
    property_values: Optional[Dict[str, Any]] = None,
    shop_values: Optional[Dict[str, Any]] = None,
    sound_dir: Optional[str] = None,
) -> Dict[str, Any]:
    property_values = property_values or {}
    metadata = part.get("metadata") or {}
    shop = dict(metadata.get("shop") or {})
    if shop_values:
        shop.update(shop_values)

    def read_number(key: str) -> Optional[float]:
        if key in property_values:
            return parse_optional_number(property_values.get(key))
        prop = (part.get("properties") or {}).get(key)
        return parse_optional_number(get_edit_value(key, prop or {}, "engine")) if isinstance(prop, dict) else None

    resolved_sound_dir = sound_dir
    if resolved_sound_dir is None:
        sound_meta = metadata.get("sound") or {}
        resolved_sound_dir = sound_meta.get("dir", "")

    return {
        "variant": metadata.get("variant") or "ice_standard",
        "isEV": bool(metadata.get("is_ev")),
        "display_name": str(shop.get("display_name") or "").strip(),
        "description": str(shop.get("description") or "").strip(),
        "price": parse_optional_number(shop.get("price")),
        "weight": parse_optional_number(shop.get("weight")),
        "maxRPM": read_number("MaxRPM"),
        "starterRPM": read_number("StarterRPM"),
        "maxTorqueNm": read_number("MaxTorque"),
        "motorMaxPowerKw": read_number("MotorMaxPower"),
        "fuelConsumption": read_number("FuelConsumption"),
        "idleThrottle": read_number("IdleThrottle"),
        "inertia": read_number("Inertia"),
        "starterTorque": read_number("StarterTorque"),
        "frictionCoulombCoeff": read_number("FrictionCoulombCoeff"),
        "frictionViscosityCoeff": read_number("FrictionViscosityCoeff"),
        "soundDir": str(resolved_sound_dir or "").strip(),
    }


def build_engine_warnings(state: Dict[str, Any]) -> List[Dict[str, str]]:
    warnings: List[Dict[str, str]] = []
    if not state:
        return warnings

    def add(level: str, text: str) -> None:
        warnings.append({"level": level, "text": text})

    def approx(left: Optional[float], right: Optional[float], tol: float = 1e-6) -> bool:
        return left is not None and right is not None and abs(left - right) <= tol

    retired_compact_baseline = (
        state.get("variant") == "ice_compact"
        and approx(state.get("inertia"), 5200)
        and approx(state.get("starterTorque"), 200000)
        and approx(state.get("frictionCoulombCoeff"), 430000)
        and approx(state.get("frictionViscosityCoeff"), 1050)
        and approx(state.get("idleThrottle"), 480)
    )

    if not state.get("display_name"):
        add("warning", "Display name is empty, so the shop entry will look broken.")
    if state.get("description") and any(ch in state.get("description", "") for ch in "()"):
        add("notice", "Description lines usually read cleaner without parentheses.")
    if not state.get("description") and str(state.get("display_name") or "").rstrip().endswith(")"):
        add("notice", "Trailing parenthetical text in the name usually belongs in the description line.")

    price = state.get("price")
    if price is not None and (price < 1000 or price > 100000):
        add("warning", "Price is outside the current recommended range of 1,000 to 100,000 coins.")

    variant = state.get("variant")
    max_rpm = state.get("maxRPM")
    if variant == "diesel_hd" and max_rpm is not None and max_rpm < 1500:
        add("danger", "Heavy diesel engines below 1500 RPM are known to freeze or behave badly in-game.")
    elif not state.get("isEV") and max_rpm is not None and max_rpm < 600:
        add("danger", "Extremely low Max RPM values can break engine behavior in-game.")

    starter_rpm = state.get("starterRPM")
    if starter_rpm is not None and max_rpm is not None and starter_rpm > max_rpm:
        add("warning", "Starter RPM is higher than Max RPM.")
    max_torque_nm = state.get("maxTorqueNm")
    if not state.get("isEV") and max_torque_nm is not None and max_torque_nm <= 0:
        add("warning", "Max Torque should be greater than zero.")
    motor_max_power = state.get("motorMaxPowerKw")
    if state.get("isEV") and motor_max_power is not None and motor_max_power <= 0:
        add("warning", "Motor Max Power should be greater than zero for EV engines.")
    fuel_consumption = state.get("fuelConsumption")
    if fuel_consumption is not None and fuel_consumption <= 0:
        add("warning", "Fuel Consumption should be greater than zero.")
    idle_throttle = state.get("idleThrottle")
    if variant == "ice_compact" and idle_throttle is not None and idle_throttle > 1:
        add("danger", "Compact engines with very high Idle Throttle are known to creep forward without throttle. The normalized compact baseline is about 0.005.")
    if retired_compact_baseline:
        add("danger", "This compact engine still matches the retired V6Sport-based outlier baseline. Rebuild or normalize it before use.")
    if variant == "bike" and (idle_throttle is None or starter_rpm is None):
        add("notice", "This bike uses the older legacy layout, so Idle Throttle and Starter RPM are not present.")

    weight = state.get("weight")
    if weight is not None:
        if variant == "diesel_hd" and weight < 100:
            add("warning", "This diesel weight is unusually low for a heavy-duty engine.")
        elif variant == "ev" and weight < 20:
            add("warning", "This EV motor weight is unusually low.")
        elif variant not in {"diesel_hd", "ev"} and weight < 40:
            add("warning", "This engine weight is unusually low.")

    if state.get("isEV") and state.get("soundDir") and state.get("soundDir") != "Electric":
        add("notice", "EV engines usually work best with the Electric sound pack.")
    return warnings


def get_all_sound_options(raw: Dict[str, Any]) -> List[Dict[str, str]]:
    options: List[Dict[str, str]] = []
    seen: set[str] = set()
    by_cue = raw.get("by_cue", {}) if isinstance(raw, dict) else {}
    for cue, rows in by_cue.items():
        for row in rows or []:
            sound_dir = str(row.get("dir") or "").strip()
            if not sound_dir or sound_dir in seen:
                continue
            seen.add(sound_dir)
            options.append({
                "dir": sound_dir,
                "group": str(cue or "Engine"),
                "source": str(row.get("source") or ""),
                "label": f"{sound_dir} [{cue}]",
            })
    for row in raw.get("bike", []) if isinstance(raw, dict) else []:
        sound_dir = str(row.get("dir") or "").strip()
        if not sound_dir or sound_dir in seen:
            continue
        seen.add(sound_dir)
        options.append({
            "dir": sound_dir,
            "group": "Bike",
            "source": str(row.get("source") or ""),
            "label": f"{sound_dir} [Bike]",
        })
    electric = raw.get("electric") if isinstance(raw, dict) else None
    if electric and "Electric" not in seen:
        options.append({
            "dir": "Electric",
            "group": "Electric",
            "source": str((electric or {}).get("source") or ""),
            "label": "Electric [EV]",
        })
    options.sort(key=lambda item: (item.get("group", ""), item.get("dir", "").lower()))
    return options


def build_property_value_map(part: Dict[str, Any]) -> Dict[str, str]:
    properties = part.get("properties") or {}
    part_type = part.get("type") or ""
    return {
        key: get_edit_value(key, prop, part_type)
        for key, prop in properties.items()
        if isinstance(prop, dict)
    }


@dataclass
class NativeEditorService:
    default_paks_dir: str = DEFAULT_PAKS_DIR
    default_mod_pak_name: str = DEFAULT_CUSTOM_PAK_FILENAME
    default_template_pak_name: str = DEFAULT_TEMPLATE_PAK_FILENAME

    def bootstrap(self) -> Dict[str, Any]:
        sounds = self.list_sounds()
        return {
            "state": self.get_live_state(),
            "parts": self.list_parts(),
            "sounds": sounds,
            "sound_options": get_all_sound_options(sounds),
            "engine_audio": self.get_engine_audio_manifest(),
            "defaults": {
                "paks_dir": self.default_paks_dir,
                "mod_pak_name": self.default_mod_pak_name,
                "template_pak_name": self.default_template_pak_name,
            },
        }

    def get_workspace_summary(self) -> WorkspaceSummary:
        raw = get_parts_list()
        state = _current_live_state()
        return WorkspaceSummary.from_payload(raw, state_version=str(state.get("version") or ""))

    def get_live_state(self) -> Dict[str, Any]:
        return _current_live_state()

    def list_parts(self) -> Dict[str, Any]:
        raw = get_parts_list()
        flat = _flatten_parts(raw)
        return {**flat, "raw": raw}

    def get_part_detail(self, path: str) -> Dict[str, Any]:
        return get_part_detail(path)

    def get_asset_document(self, path: str) -> AssetDocument:
        return AssetDocument.from_detail(self.get_part_detail(path))

    def get_engine_templates(self) -> Dict[str, Any]:
        raw = get_engine_templates()
        flat = _flatten_engine_templates(raw)
        return {**flat, "raw": raw}

    def get_engine_template_catalog_view(self) -> TemplateCatalog:
        return TemplateCatalog.from_payload(self.get_engine_templates(), "engine")

    def get_tire_templates(self) -> Dict[str, Any]:
        raw = get_tire_templates()
        flat = _flatten_tire_templates(raw)
        return {**flat, "raw": raw}

    def get_tire_template_catalog_view(self) -> TemplateCatalog:
        return TemplateCatalog.from_payload(self.get_tire_templates(), "tire")

    def list_sounds(self) -> Dict[str, Any]:
        return list_sounds()

    def get_sound_options(self) -> List[Dict[str, str]]:
        return get_all_sound_options(self.list_sounds())

    def get_engine_audio_manifest(self) -> Dict[str, Any]:
        return get_engine_audio_manifest()

    def prepare_engine_audio_workspace(self) -> Dict[str, Any]:
        return prepare_engine_audio_workspace()

    def get_engine_audio_row(self, engine_name: str) -> Optional[Dict[str, Any]]:
        engine_name = str(engine_name or "").strip()
        if not engine_name:
            return None
        manifest = self.get_engine_audio_manifest()
        for row in manifest.get("engines", []):
            if str(row.get("engine_name") or "").strip() == engine_name:
                return dict(row)
        return None

    def set_engine_audio_override(self, engine_name: str, enabled: bool, override_sound_dir: str = "") -> Dict[str, Any]:
        return set_engine_audio_override({
            "engine_name": engine_name,
            "enabled": enabled,
            "override_sound_dir": override_sound_dir,
        })

    def recommend_engine_price(self, torque_nm: Any, include_bikes: bool = False) -> Dict[str, Any]:
        return recommend_engine_price({
            "torque_nm": torque_nm,
            "include_bikes": include_bikes,
        })

    def save_part(self, path: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return save_part(path, data)

    def create_engine(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return create_engine(dict(data))

    def create_tire(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return create_tire(dict(data))

    def delete_part(self, path: str, expected_version: str = "") -> Dict[str, Any]:
        part_path = str(path or "").strip()
        if not part_path:
            return {"error": "No part path specified"}
        payload = {"path": part_path, "expected_version": expected_version}
        if part_path.startswith("mod/Engine/"):
            return delete_engine(payload)
        if part_path.startswith("mod/Tire/"):
            return delete_tire(payload)
        return {"error": "Only generated engines and tires can be deleted from the desktop app."}

    def pack_mod(self, output_path: str, parts: Optional[Iterable[str]] = None) -> Dict[str, Any]:
        return pack_mod(output_path, list(parts or []))

    def pack_templates(self, output_path: str) -> Dict[str, Any]:
        return pack_templates(output_path)

    def build_pack_preview(self, kind: str, output_path: str, selection_label: str, item_count: int) -> PackPreview:
        return PackPreview(
            kind=str(kind or "").strip() or "workspace",
            output_path=str(output_path or "").strip(),
            selection_label=str(selection_label or "").strip(),
            item_count=max(0, int(item_count or 0)),
            state_version=str(self.get_live_state().get("version") or ""),
        )

    def build_conflict_state(self, result: Optional[Dict[str, Any]], default_message: str) -> ConflictState:
        return ConflictState.from_result(result, default_message)

    def get_referenced_curve(self, detail: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        asset_info = detail.get("asset_info") or {}
        curve_name = str(asset_info.get("torque_curve_name") or "").strip()
        if not curve_name:
            return None
        source = str(detail.get("source") or "mod").strip() or "mod"
        candidates = [
            f"{source}/Engine/TorqueCurve/{curve_name}",
            f"mod/Engine/TorqueCurve/{curve_name}",
            f"vanilla/Engine/TorqueCurve/{curve_name}",
        ]
        if source == "template":
            candidates.insert(1, f"template/Engine/TorqueCurve/{curve_name}")
        seen: set[str] = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            curve_detail = get_part_detail(candidate)
            if curve_detail and not curve_detail.get("error") and curve_detail.get("curve_data"):
                return curve_detail
        return None
