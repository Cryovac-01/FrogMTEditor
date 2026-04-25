# Frog Mod Editor - Advanced Users

This guide is for people who want to understand how the app works, audit the parser, modify the workflow, or build their own tooling around the public source package.

## Package Layout

The public release is split into source and runtime:

- `Frog_Mod_Editor_Public_Source.zip` is the authoritative source package. It includes `source\src`, public data, native UI assets, tests, docs, and selected public scripts.
- `Frog_Mod_Editor_Runtime_Overlay.zip` is optional. Extract it over the source package to add `source\python`.
- `Frog_Mod_Editor_Complete_Source_Release.zip` is a one-file package containing the same cleaned source plus the trimmed runtime already expanded.
- `run.bat` prefers `source\python\pythonw.exe`, then falls back to `py -3`, then `python`.

Source-only setup needs Python 3.11+ and `PySide6`. Install `pytest` for tests and `Pillow` only when regenerating `source\src\native_assets`.

## App Architecture

The shipped desktop app is the PySide6 shell in `source\src\native_qt_app.py` and `source\src\native_qt`.

- `native_qt\window.py` owns the main shell, navigation, inspector panels, workspace overview, status footer, quick actions, and pack actions.
- `native_qt\creator.py` owns the engine and tire creation flows.
- `native_qt\forms.py` maps parser-backed fields into editor controls.
- `native_qt\widgets.py` contains shared Qt widgets, delegates, dialogs, metrics, and curve/audio display helpers.
- `native_qt\theme.py` centralizes branding, icon loading, control sizing, and native asset loading.
- `native_services.py` exposes `NativeEditorService`, the desktop service layer that loads data, edits generated assets, creates parts, and calls the pack routes.
- `api\routes.py` contains the route-style app operations. The native app calls these directly rather than running a web server.
- `parsers\` contains the binary readers/writers for Motor Town assets and DataTables.
- `pak_writer.py` writes the final uncompressed pak v8 archives.

The app deliberately stays narrow. It is not a general Unreal editor; it understands the Motor Town asset layouts needed by this workflow and leaves unsupported fields untouched.

## Data Directories

- `source\data\vanilla` contains baseline vanilla assets and DataTables used for reading, cloning, and donor row shape.
- `source\data\templates\Engine` contains curated engine template pairs.
- `source\data\mod` is the generated workspace. New engines, tires, and DataTable outputs are written here.
- `source\src\native_assets` contains QSS, generated PNG artwork, the asset manifest, and SVG icons used by the PySide6 UI.
- `source\scripts` contains only public helper scripts that are documented or useful for diagnostics.

Game-required paths such as `MotorTown\Content`, `/Script/MotorTown`, and `/Game/Cars/Parts/...` are kept because Unreal assets and pak paths require them. Those names do not change the Frog Mod Editor branding.

## Parser Overview

The parser is a targeted Motor Town asset tool. It does not try to be a complete Unreal asset editor. The active parser code is in `source\src\parsers`.

- `.uasset` helpers read package header fields, name tables, import tables, export table sizes, and selected object references.
- `.uexp` parsers read and write known Motor Town layouts for engines, tires, transmissions, LSDs, and torque curves.
- DataTable helpers add row names, append imports, duplicate compatible row payloads, patch hidden asset references, and update serial sizes.
- The pak writer emits uncompressed pak v8 files with Motor Town content paths.

## Engine Parser Flow

Engine editing is based on reading the existing Unreal package pair and changing only known fields.

1. The `.uasset` reader builds the name table and import table so properties and hidden object references can be resolved.
2. The `.uexp` parser walks the engine property payload and extracts known scalar values such as horsepower, torque, idle RPM, redline, displacement, weight, price, fuel type, and related shop metadata.
3. Variant detection classifies layout differences such as ICE, diesel, EV, and compact legacy forms so serialization does not force every engine through the same binary shape.
4. Serialization writes only supported property values back into the original structure and preserves unknown bytes.
5. If a `.uasset` header grows because names or imports were appended, serial sizes and offsets are repaired before the asset is packed.

The important rule is that parsed values are user-facing, but the binary layout remains authoritative. If the parser does not understand a field, the app should preserve it rather than invent a replacement.

## DataTable Flow

Motor Town shop visibility depends on DataTable rows as well as asset files.

- Row keys must match the engine or tire asset names that the game expects.
- Display names, descriptions, price, mass, category, and shop-visible flags live in row payloads.
- Some rows contain hidden negative import references that point back to asset imports in the `.uasset` package.
- New rows may need new name table entries, new imports, preload dependency updates, and corrected serial sizes.
- The template packer applies a universal shop-visible row-tail policy for generated engine templates so late-list engines do not disappear from the in-game shop.
- Template pack verification checks that every materialized engine asset has both `.uasset` and `.uexp` pak entries and a matching generated DataTable row.

If an engine exists in the pak but not in the DataTable, the game may not list it. If the DataTable row exists but points at the wrong import or has a bad tail layout, the game may stop listing rows after a specific template.

## Engine Template Pack Flow

Template engines are small `.uasset` and `.uexp` pairs in `source\data\templates\Engine`. The template packer rebuilds final engine files from vanilla Motor Town donor layouts, then registers every engine in a fresh Engines DataTable.

Every engine asset in `/Cars/Parts/Engine/` needs a matching row and import reference in `/DataAsset/VehicleParts/Engines`. Missing either side can make engines appear with wrong values, fail to appear in shop lists, or crash during load.

The pack-template route:

1. Scans unique template `.uasset` and `.uexp` pairs.
2. Materializes each template against the appropriate donor-backed layout.
3. Registers each generated engine in `Engines.uasset` and `Engines.uexp`.
4. Writes the pak with engine assets plus DataTable files.
5. Verifies expected template count, materialized count, pak engine count, registered row count, and missing template names.

Use `source\scripts\inspect_template_pack.py` to diagnose a generated pak. It reports pak entry counts, engine asset counts, DataTable row counts, missing template pairs, and the last registered template row.

## Tire, Transmission, LSD, And Torque Curve Scope

The app supports targeted editing for several part families:

- Tires: clone supported vanilla layouts, edit known tire properties, write generated tire assets, and register generated rows.
- Transmissions: parse and expose supported ratios and related known properties where the current binary layout is understood.
- LSD/differentials: parse selected fields used by supported generated parts.
- Torque curves: read curve data for display and supported adjustments; unknown curve payload data remains preserved.

Current limitations are intentional. Unsupported layouts should be treated as read-only or preserved binary data until the parser has a tested contract for them.

## Important Binary Rules

- FName entries use the UE5 hash format expected by Motor Town.
- New engine rows need both the short asset name and `/Game/Cars/Parts/Engine/<name>` path in the name table.
- DataTable rows contain hidden negative import references that must be retargeted from the template row to the new asset import.
- `SerialSize`, `SerialOffset`, total header size, and related offsets must be patched whenever a `.uasset` header grows.
- Pak v8 index records for these uncompressed files do not include a phantom block count.

## Public Helper Scripts

- `create_templates.py` rebuilds or refreshes template metadata/data used by the curated engine workflow.
- `generate_native_ui_assets.py` regenerates native PNG assets from the asset manifest. It requires Pillow.
- `inspect_template_pack.py` inspects a generated template pak and reports asset/DataTable coverage.
- `export_public_source_zip.py` builds the source zip and runtime overlay.
- `export_complete_source_release_zip.py` builds a one-file source release with the trimmed runtime included.
- `export_runtime_manifest.py` documents the minimal runtime file set used by release tooling.

Unrelated private packaging, audio workspace, and build-helper scripts are intentionally excluded from the public source zip.

## Validation Workflow

The runtime overlay is intentionally lean and does not ship pytest. Install `pytest` into your Python environment before running the test command. Useful checks from the source root:

```bat
py -3 -m pytest source\tests
source\python\python.exe source\src\native_qt_app.py --smoke-test
source\python\python.exe source\scripts\inspect_template_pack.py path\to\ZZZ_FrogTemplates_P.pak
```

For source-only setups, replace `source\python\python.exe` with `py -3` after installing dependencies.

## Why UAssetGUI And RePak Are Not Required

Frog Mod Editor performs the narrow operations it needs directly: it parses the fields it understands, writes those fields back into the original binary layouts, updates DataTable rows/imports, and writes pak v8 archives. Because the workflow is targeted and automated, users do not need to open assets manually in UAssetGUI or package files manually with RePak.

## Current Limits

- This is not a general Unreal Engine editor.
- Unsupported fields are left blank or read-only in the UI.
- The safest path is to use the included vanilla data and generated templates rather than mixing unrelated asset layouts.
- Audio cooking and large temporary audio workspaces are not part of this public source zip.

## License

Frog Mod Editor is released under the Creative Commons Attribution-NonCommercial 4.0 International license, `CC BY-NC 4.0`.

Plain-language summary: you may inspect, modify, share, and learn from this project for free. You may not sell it, monetize it, bundle it into paid products, or use it to provide paid services without separate written permission.

Motor Town game names, game paths, and referenced asset formats belong to their respective owners. Those game-specific references are separate from this project's license.
