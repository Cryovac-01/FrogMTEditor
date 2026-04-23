# Motor Town Engine Modding — Key Learnings

## The Golden Rule
**Every engine in /Cars/Parts/Engine/ MUST have matching entries in /DataAsset/VehicleParts/Engines (rows + imports), and vice versa. No orphans on either side.**

---

## Creating a New Engine (Complete Working Recipe)

### 1. Engine Asset (/Cars/Parts/Engine/)
- Clone a vanilla `.uasset` using `clone_uasset()` with correct UE5 FName hashes
- Copy the SAME donor's `.uexp` and inject custom float values:
  - `float[2]` = MaxTorque (raw value, divide by 10000 for Nm)
  - `float[3]` = MaxRPM
  - `float[7]` = HP (explicit display value)
  - These positions are relative to the TorqueCurve import offset (tc@14 for V8/V6/Bike)

### 2. DataTable Entry (/DataAsset/VehicleParts/Engines)

**Engines.uasset:**
- Add 2 FName entries to name table (short name + full `/Game/Cars/Parts/Engine/<name>` path)
- Add 2 import entries (64 bytes total, appended to import table):
  - MHEngineDataAsset import FIRST, Package import SECOND
- Increment ImportCount by 2
- Bump all post-import offsets by 64 bytes
- Update TotalHeaderSize and SerialOffset

**Engines.uexp:**
- Duplicate a donor row of matching variant
- Fix the FName index (first 4 bytes)
- **CRITICAL: Find and fix the hidden MHEngineDataAsset import reference**
  - Scan row bytes for the donor's negative import ID
  - Replace with the new engine's import ID
  - Position varies per row type (byte 198-310)
- Update display name, price, weight
- Patch SerialSize in .uasset

---

## UE5 FName Hash Algorithm

```
strihash = CRC-32 (polynomial 0x04C11DB7, normal form) of UPPERCASE string, init=0
strcrc32  = CRC-32 (polynomial 0xEDB88320, reflected) of original string, 4 bytes per char, init=0xFFFFFFFF, final XOR
combined  = (strihash & 0xFFFF) | ((strcrc32 & 0xFFFF) << 16)
storage   = struct.pack('<I', combined)  ← LITTLE-ENDIAN
```

Source: UAssetAPI CRCGenerator.cs (github.com/atenfyr/UAssetAPI)

---

## Critical Bugs Found and Fixed

| Bug | Symptom | Root Cause | Fix |
|-----|---------|------------|-----|
| OOM crash (28 GB allocation) | Game crashes on pak load | `_index_entry()` wrote extra `block_count` uint32 | Removed phantom block_count |
| SerialOffset not updated | Serialization error | `clone_uasset()` / `add_row_key()` didn't update export SerialOffset when header grew | Patch SerialOffset in export table after any header size change |
| Missing offset bumps | Serialization error | Only bumped fields [4,8,10,11] — missed [34], [40], BulkDataStartOffset | Scan ALL header int32s in range [rest_start, total_size+serial_size] |
| Wrong hash endianness | Engine loads but .uexp values ignored (500 torque) | Hash stored as big-endian, should be little-endian | Changed `struct.pack('>I', ...)` to `struct.pack('<I', ...)` |
| Wrong hash algorithm | Same as above | Used FNV-1a instead of UE5's dual CRC algorithm | Implemented correct Strihash_DEPRECATED + StrCrc32 |
| Missing row import reference | Engine shows donor's torque (500/522) | Duplicated DataTable row still references donor engine's import | Scan row for donor's import ID, replace with new engine's |
| DataTable row trimming | "Corrupt data" crash | Row scanner misses some rows, rebuild creates inconsistent data | Don't remove rows — only add or modify |
| Preload dependency insertion | ACCESS_VIOLATION crash | Inserting into preload dep list corrupts subsequent offsets | Don't touch preload dependencies |
| SerialSize mismatch | "Serial size mismatch" crash | DataTable .uasset SerialSize not updated after .uexp row changes | Always call `_patch_datatable_serial_size()` after any .uexp modification |

---

## Pak Format (v8, uncompressed)

- **Data section**: 53-byte record header + raw file bytes per entry
- **Index section**: FString mount ("../../../") + file count + entries (path + offset + sizes + SHA1 + flags)
- **Footer**: 221 bytes (enc_key_guid + encrypted + magic 0x5A6F12E1 + version 8 + index_offset + index_size + index_sha1 + compression_names)
- Index entries do NOT include block_count for uncompressed files

---

## File Organization

| Location | Purpose |
|----------|---------|
| `data/vanilla/Engine/` | 36 vanilla engine .uasset/.uexp files |
| `data/vanilla/DataTable/` | Vanilla Engines.uasset/.uexp (36 rows) |
| `data/templates/Engine/` | 218 template engine .uexp files with custom parameters |
| `src/parsers/pak_writer.py` | Pak v8 writer |
| `src/parsers/pak_reader.py` | Pak v8 reader |
| `src/parsers/uasset_clone.py` | Engine .uasset cloning with correct hashes |
| `src/parsers/uasset_engines_dt.py` | DataTable .uasset modifications (FNames, imports) |
| `src/parsers/uexp_engines_dt.py` | DataTable .uexp row management |
| `build_real_template_engines.py` | Current full personal pack builder |
| `scripts/export_web_server_bundle.py` | Deployment bundle exporter |

---

## Template Engine Pack Fix Log (2026-03-30)

### What Actually Fixed the Full Template Pack

- **Use compatible custom DataTable rows as metadata references, but do NOT ship non-vanilla assets.**
  - Vanilla-style row cloning was not enough for the large mixed template set.
  - Working row donor families:
    - bike -> `sportster120065HP`
    - gas standard -> `13b`
    - gas compact -> `20hyundai`
    - diesel -> `VW19TDI150HP`
    - EV -> `EVWulingHongguangMiniEV`

- **Internal engine asset keys must not contain underscores.**
  - Problem examples:
    - `indian_scout_1250`
    - `honda_cbr600rr_2024`
  - Symptom: unrelated entries later in the shop list would freeze even though the row looked valid.
  - Fix: generate underscore-free internal asset names for template engines, while keeping the visible shop title unchanged.

- **Template engine `.uexp` files must be rebuilt from vanilla donor structure, not copied as raw template payloads.**
  - This was especially important for compact engines and bike families.
  - `materialize_template_files()` is the stable path for emitting donor-backed `.uasset` + `.uexp` pairs.

- **Shop subtitles should use the second descriptor line.**
  - Move trailing parenthetical application/model text out of the main title.
  - Drop the parentheses when writing the descriptor line.

- **FuelConsumption for templates is normalized to `1.0`.**

### Diesel Freeze Root Cause

- The remaining heavy-diesel freezes were **not** caused by torque magnitude.
- The failing set clustered around ultra-low runtime RPM values:
  - `600`
  - `750`
  - `1000`
- Engines like `cat_3608_3300`, `cat_3616_6600`, `bergen_b3240_v16`, and the `wartsila_*` family worked after changing the generated diesel runtime window to:
  - `MaxRPM >= 1500`
  - `StarterRPM = 1500`
  - recompute `MaxTorque` from HP using that effective RPM so the intended power stays the same

### Current Known-Good User Build

- Full user pack should be built from vanilla donor assets only.
- Compatible row structure research is captured in the parser logic; the public bundle uses vanilla data.
- User-facing compiled pack excludes bikes, but bike templates stay available on the site.

Known-good command:

```powershell
.\python\python.exe build_real_template_engines.py --exclude-bikes --pack-path "C:\Program Files (x86)\Steam\steamapps\common\Motor Town\MotorTown\Content\Paks\FF2000_P.pak"
```

Known-good result from this configuration:

- `174` compiled engines
- `88` gas cars
- `2` gas trucks
- `50` diesel
- `34` EV
- `0` bikes in compiled pack
- `350` pak entries verified

---

## Engine + Tire Parameter Surface Reference (2026-04-04)

These field meanings are the current toolchain truth. When a note says **inferred**, that means the behavior comes from layout position, UI/editor behavior, and in-game outcomes rather than a named upstream Motor Town enum dump.

### Engine Parameters

- `TorqueCurve`
  - Import reference to the torque-curve asset used by the engine. Read-only in the editor.
- `Inertia`
  - Rotational inertia of the engine assembly. Higher values make the engine rev up and rev down more slowly.
- `StarterTorque`
  - Torque applied by the starter motor while cranking.
- `StarterRPM`
  - Starter target RPM before the engine catches. Only present on bike and diesel-heavy layouts.
- `MaxTorque`
  - Peak torque, stored as raw value `N-m * 10000`.
- `MaxRPM`
  - Maximum operating RPM / redline.
- `FrictionCoulombCoeff`
  - Constant friction loss term. Higher values increase baseline mechanical drag.
- `FrictionViscosityCoeff`
  - Speed-dependent friction loss term. Higher values increase drag as RPM rises.
- `IdleThrottle`
  - Minimum throttle opening used to sustain idle.
- `FuelType`
  - 1-byte enum. Observed mapping: `0/1 = Gas`, `2 = Diesel`, `3 = Electric`.
- `FuelConsumption`
  - Base consumption scalar for the powerplant.
- `HeatingPower`
  - Engine heat generation term. Current template policy writes it explicitly as `0.5` on standard and bike layouts that structurally carry the field, while leaving the older rev/friction baselines in place.
- `BlipThrottle`
  - Throttle amount used for rev-match blips.
- `BlipDurationSeconds`
  - Duration of the rev-match blip in seconds.
- `AfterFireProbability`
  - Decel/backfire probability scalar. Exact game curve is inferred.
- `EngineType`
  - 4-byte enum present on diesel-heavy layouts. Exact label mapping is still unknown; current tools preserve the raw integer. Inferred to control diesel-specific engine behavior.
- `IntakeSpeedEfficiency`
  - Diesel-heavy-only airflow efficiency term. Inferred to affect high-speed breathing / charge efficiency.
- `MaxJakeBrakeStep`
  - Diesel-heavy-only integer limit for jake-brake strength steps.
- `MaxRegenTorqueRatio`
  - EV-only regenerative braking torque ratio.
- `MotorMaxPower`
  - EV-only peak motor power, stored as raw value `kW * 10000`.
- `MotorMaxVoltage`
  - EV-only peak system voltage, stored as raw value `V * 10000`.

### Engine Layout Coverage

- `ice_standard`
  - Possible fields: `TorqueCurve`, `Inertia`, `StarterTorque`, `MaxTorque`, `MaxRPM`, `FrictionCoulombCoeff`, `FrictionViscosityCoeff`, `IdleThrottle`, `FuelConsumption`, `HeatingPower`, `BlipThrottle`, `BlipDurationSeconds`, `AfterFireProbability`
  - Current template layout keeps the modern `H2_30HP` structure only so `HeatingPower = 0.5` can be serialized explicitly, while restoring the older standard-engine friction / inertia / blip baseline.
- `ice_compact`
  - Possible fields: `TorqueCurve`, `Inertia`, `StarterTorque`, `MaxTorque`, `MaxRPM`, `FrictionCoulombCoeff`, `FrictionViscosityCoeff`, `IdleThrottle`, `FuelConsumption`, `BlipThrottle`, `BlipDurationSeconds`, `AfterFireProbability`
  - Current vanilla-safe compact layout omits `AfterFireProbability`; legacy compact layout carried it.
- `bike`
  - Possible fields: `TorqueCurve`, `Inertia`, `StarterTorque`, `StarterRPM`, `MaxTorque`, `MaxRPM`, `FrictionCoulombCoeff`, `FrictionViscosityCoeff`, `IdleThrottle`, `FuelConsumption`, `HeatingPower`, `BlipThrottle`, `BlipDurationSeconds`, `AfterFireProbability`
  - Legacy vanilla bike layout omitted `StarterRPM` and `IdleThrottle`; current template bike layout keeps both and writes `HeatingPower = 0.5`.
- `diesel_hd`
  - Possible fields: `TorqueCurve`, `Inertia`, `StarterTorque`, `StarterRPM`, `MaxTorque`, `MaxRPM`, `FrictionCoulombCoeff`, `FrictionViscosityCoeff`, `IdleThrottle`, `FuelType`, `FuelConsumption`, `EngineType`, `BlipThrottle`, `IntakeSpeedEfficiency`, `BlipDurationSeconds`, `MaxJakeBrakeStep`
  - Current template baseline is back on the previous `HeavyDuty_440HP` friction profile (`FrictionCoulombCoeff = 2800000`, `FrictionViscosityCoeff = 7000`).
- `ev`
  - Possible fields: `TorqueCurve`, `Inertia`, `MaxTorque`, `MaxRPM`, `FrictionCoulombCoeff`, `FrictionViscosityCoeff`, `FuelType`, `FuelConsumption`, `MaxRegenTorqueRatio`, `MotorMaxPower`, `MotorMaxVoltage`
  - Current template baseline is back on the previous `Electric_300HP` friction profile (`FrictionCoulombCoeff = 100`, `FrictionViscosityCoeff = 100`).

### Engine Thermal Policy

- There is no explicit cooling/radiator field in the known engine asset layouts.
- `HeatingPower` is the only explicit heat-generation field currently exposed by the parser, and only `ice_standard` and `bike` layouts carry it.
- Omitting `HeatingPower` on standard engines was not sufficient to suppress overheating in-game, so the current policy is to keep standard engines on the modern `H2_30HP` layout and serialize `HeatingPower = 0.5` explicitly.
- Layouts without `HeatingPower` (`ice_compact`, `diesel_hd`, `ev`) still rely on their inherited baseline fields such as `FrictionCoulombCoeff`, `FrictionViscosityCoeff`, `IdleThrottle`, and `FuelConsumption`.
- Current low-heat template baselines:
  - `ice_standard`: `H2_30HP` structure with `HeatingPower = 0.5`, but older standard-engine rev / friction values restored
  - `bike`: `Bike_i4_100HP` structure with `HeatingPower = 0.5`
  - `diesel_hd`: previous `HeavyDuty_440HP` runtime baseline restored
  - `ev`: previous `Electric_300HP` runtime baseline restored

### Tire Parameters

- `LateralStiffness`
  - Base lateral carcass stiffness. Higher values resist sideways deformation more strongly.
- `CorneringStiffness`
  - Primary slip-angle cornering force term. Higher values increase lateral grip response.
- `CamberStiffness`
  - Camber-related cornering contribution. Current UI grip estimate treats tire grip as `CorneringStiffness + (CamberStiffness / 2)`.
- `LongStiffness`
  - Base longitudinal stiffness for acceleration/braking grip.
- `LongSlipStiffness`
  - Longitudinal slip response term during wheelspin or lockup.
- `LoadRating`
  - Nominal rated load capacity.
- `MaxLoad`
  - Upper supported load limit.
- `TreadDepth`
  - Extra tread-depth term on richer tire layouts. Inferred to affect off-road / wet / wear behavior.
- `TireTemperature`
  - Explicit temperature-state field on richer tire layouts. Inferred thermal operating point.
- `ThermalSensitivity`
  - Sensitivity of grip to temperature changes. Inferred thermal scaling term.
- `MaxSpeed`
  - Rated maximum speed.
- `GripMultiplier`
  - Overall grip scalar multiplier.
- `RollingResistance`
  - Rolling drag term. Higher values cost speed and efficiency.
- `WearRate`
  - Primary tire wear scalar.
- `WearRate2`
  - Secondary wear scalar used only on richer layouts. Exact split is inferred.

### Tire Layout Coverage

- Known tire float families: `6`, `8`, `9`, `10`, `11`, `12`, and `14` float layouts.
- Canonical tire field union: `LateralStiffness`, `CorneringStiffness`, `CamberStiffness`, `LongStiffness`, `LongSlipStiffness`, `LoadRating`, `MaxLoad`, `TreadDepth`, `TireTemperature`, `ThermalSensitivity`, `MaxSpeed`, `GripMultiplier`, `RollingResistance`, `WearRate`, `WearRate2`
- Current editor policy:
  - Every tire detail surface shows the full known tire field list.
  - If a donor layout does not currently carry a field, that field stays blank.
  - When the requested set of tire fields matches a known richer layout, the serializer can switch to that layout by selecting a matching header exemplar.

### Current Editor Policy

- Engine detail/template surfaces now expose the full known engine field union.
- If an engine layout does not structurally carry a field, the editor shows that field as blank and read-only.
- Blank unsupported engine fields are intentionally not written back into the `.uexp`.
- Tire detail/template surfaces expose the full known tire field union as well.

