"""Create the public Frog Mod Editor source zip."""
from __future__ import annotations

import json
import os
import re
import shutil
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKUPS_DIR = PROJECT_ROOT / "backups"
STAGING_DIR = BACKUPS_DIR / "frog_mod_editor_public_source"
ZIP_PATH = BACKUPS_DIR / "Frog_Mod_Editor_Public_Source.zip"
SOURCE_DIR = STAGING_DIR / "source"
RUNTIME_STAGING_DIR = BACKUPS_DIR / "frog_mod_editor_runtime_overlay"
RUNTIME_ZIP_PATH = BACKUPS_DIR / "Frog_Mod_Editor_Runtime_Overlay.zip"
RUNTIME_SOURCE_DIR = RUNTIME_STAGING_DIR / "source"

try:
    from export_runtime_manifest import (
        PYSIDE_RELATIVE_ROOT,
        PYSIDE_REQUIRED_FILES,
        PYSIDE_REQUIRED_PLUGIN_FILES,
        SHIBOKEN_RELATIVE_ROOT,
        SHIBOKEN_REQUIRED_FILES,
        PYTHON_SKIP_FILES,
        PYTHON_SKIP_PREFIXES,
        matches_prefix,
    )
except ImportError:  # pragma: no cover - direct import path fallback for unusual runners.
    from scripts.export_runtime_manifest import (  # type: ignore
        PYSIDE_RELATIVE_ROOT,
        PYSIDE_REQUIRED_FILES,
        PYSIDE_REQUIRED_PLUGIN_FILES,
        SHIBOKEN_RELATIVE_ROOT,
        SHIBOKEN_REQUIRED_FILES,
        PYTHON_SKIP_FILES,
        PYTHON_SKIP_PREFIXES,
        matches_prefix,
    )

REQUIRED_PUBLIC_SOURCE_PATHS = {
    "README.md",
    "README_ADVANCED_USERS.md",
    "run.bat",
    "source/src/native_qt/__init__.py",
    "source/src/native_qt/creator.py",
    "source/src/native_qt/forms.py",
    "source/src/native_qt/theme.py",
    "source/src/native_qt/widgets.py",
    "source/src/native_qt/window.py",
    "source/src/native_qt_app.py",
    "source/src/native_assets/native_qt_theme.qss",
    "source/src/native_assets/native_asset_manifest.json",
    "source/src/native_assets/brand_mark.png",
    "source/src/native_assets/welcome_hero.png",
    "source/src/native_assets/curve_banner.png",
    "source/src/native_assets/icons",
    "source/desktop_native/app.manifest",
    "source/desktop_native/app.rc",
    "source/scripts/create_templates.py",
    "source/scripts/export_complete_source_release_zip.py",
    "source/scripts/export_public_source_zip.py",
    "source/scripts/export_runtime_manifest.py",
    "source/scripts/generate_native_ui_assets.py",
    "source/scripts/inspect_template_pack.py",
    "source/tests",
    "source/tests/test_native_qt_button_contracts.py",
    "source/tests/test_native_qt_input_contracts.py",
    "source/tests/test_native_qt_overview_card_contracts.py",
    "source/tests/test_native_qt_template_row_contracts.py",
}

UI_ASSET_REFERENCE_PATTERN = re.compile(r"load_pixmap(?:_contained)?\(\s*[\"']([^\"']+)[\"']")
UI_ICON_REFERENCE_PATTERN = re.compile(r"load_(?:tinted_)?icon(?:_pixmap)?\(\s*[\"']([^\"']+\.svg)[\"']")

USER_FACING_BRANDING_FILES = {
    "README.md",
    "README_ADVANCED_USERS.md",
    "run.bat",
    "source/desktop_native/app.manifest",
    "source/desktop_native/app.rc",
    "source/desktop_native/README.md",
}

WORKSPACE_MATCH_DIRS = (
    "source/src/native_qt",
    "source/src/native_assets",
    "source/scripts",
    "source/tests",
)

WORKSPACE_MATCH_FILES = (
    "source/src/native_qt_app.py",
    "source/desktop_native/app.manifest",
    "source/desktop_native/app.rc",
    "source/desktop_native/README.md",
    "source/tests/test_native_qt_button_contracts.py",
    "source/tests/test_native_qt_input_contracts.py",
    "source/tests/test_native_qt_overview_card_contracts.py",
    "source/tests/test_native_qt_template_row_contracts.py",
)

FORBIDDEN_USER_BRANDING = (
    "Motor Town" + " Mod Editor",
    "Motor Town" + " Mod Workbench",
    "MotorTown" + "ModEditor",
    "FrogTuning" + "Desktop",
    "FrogTuning",
)

PUBLIC_SCRIPT_NAMES = {
    "create_templates.py",
    "export_complete_source_release_zip.py",
    "export_public_source_zip.py",
    "export_runtime_manifest.py",
    "generate_native_ui_assets.py",
    "inspect_template_pack.py",
}

SKIP_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".git",
    "target",
}

SKIP_FILE_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".tmp",
    ".log",
    ".pak",
}

SKIP_FILE_NAMES = {
    ".DS_Store",
    "runtime_payload.zip",
}

FORBIDDEN_RELEASE_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".tmp",
    ".log",
    ".pak",
}

FORBIDDEN_RELEASE_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
}

RUNTIME_REQUIRED_PATHS = {
    "source/python/python.exe",
    "source/python/pythonw.exe",
    "source/python/Lib/encodings/__init__.py",
    "source/python/Lib/site-packages/PySide6/__init__.py",
    "source/python/Lib/site-packages/PySide6/QtCore.pyd",
    "source/python/Lib/site-packages/PySide6/QtGui.pyd",
    "source/python/Lib/site-packages/PySide6/QtWidgets.pyd",
    "source/python/Lib/site-packages/PySide6/QtCharts.pyd",
    "source/python/Lib/site-packages/PySide6/QtSvg.pyd",
    "source/python/Lib/site-packages/PySide6/plugins/platforms/qwindows.dll",
    "source/python/Lib/site-packages/shiboken6/Shiboken.pyd",
}

README_TEXT = """# Frog Mod Editor

Frog Mod Editor is a Windows desktop tool for inspecting and editing selected Motor Town part assets. It focuses on engines, tires, transmissions, differentials, torque curves, template engines, and pak export.

## Release Packages

The public release can be used as either split packages or one complete package:

- `Frog_Mod_Editor_Public_Source.zip` contains the app source, parser source, native UI assets, public data, tests, docs, and public helper scripts.
- `Frog_Mod_Editor_Runtime_Overlay.zip` contains an optional bundled Python runtime under `source\\python`.
- `Frog_Mod_Editor_Complete_Source_Release.zip` contains the same cleaned source plus the trimmed runtime already expanded under `source\\python`.

The split source package is the main artifact. The runtime overlay and complete source release are for users who do not want to install Python and PySide6 themselves.

## Start the app

Option A, complete release:

1. Extract `Frog_Mod_Editor_Complete_Source_Release.zip`.
2. Double-click `run.bat`.

Option B, split release:

1. Extract `Frog_Mod_Editor_Public_Source.zip`.
2. Optional: extract `Frog_Mod_Editor_Runtime_Overlay.zip` into the same folder so it creates `source\\python`.
3. Double-click `run.bat`.

The batch file first uses the bundled runtime at `source\\python\\pythonw.exe` if it exists. If the runtime overlay is not present, it falls back to `py -3` or `python` from your Windows PATH.

For source-only use, install:

- Python 3.11 or newer
- `PySide6` for the desktop app
- `pytest` only if you want to run tests
- `Pillow` only if you want to regenerate native UI assets

Minimal source-only setup:

```bat
py -3 -m pip install PySide6
py -3 source\\src\\native_qt_app.py
```

## Basic workflow

- Browse vanilla parts from the app's part list to inspect current values.
- Open a generated mod part to edit supported fields.
- Use the create-engine screen to pick a template, adjust values, choose shop text/price/weight, and create a new engine.
- Use the create-tire screen to clone a vanilla tire layout and edit supported tire fields.
- Use the pack action to write a game-ready `_P.pak` file.
- Use the template pack action to export every curated engine template into one `_P.pak`.

## Where files are written

- Generated engines and tires are written under `source\\data\\mod\\MotorTown\\Content\\Cars\\Parts`.
- Generated DataTable entries are written under `source\\data\\mod\\MotorTown\\Content\\DataAsset\\VehicleParts`.
- Template definitions are under `source\\data\\templates\\Engine`.
- Vanilla reference data is under `source\\data\\vanilla`.

## Notes

- Names for new parts should use letters and numbers only.
- The app normalizes pak names so output files end in `_P.pak`.
- Keep a backup of any pak you replace in your Motor Town install.

## License

Frog Mod Editor is released under the Creative Commons Attribution-NonCommercial 4.0 International license, `CC BY-NC 4.0`.

Plain-language summary: you may inspect, modify, share, and learn from this project for free. You may not sell it, monetize it, bundle it into paid products, or use it to provide paid services without separate written permission.

Motor Town game names, game paths, and referenced asset formats belong to their respective owners. Those game-specific references are separate from this project's license.
"""

ADVANCED_README_TEXT = """# Frog Mod Editor - Advanced Users

This guide is for people who want to understand how the app works, audit the parser, modify the workflow, or build their own tooling around the public source package.

## Package Layout

The public release is split into source and runtime:

- `Frog_Mod_Editor_Public_Source.zip` is the authoritative source package. It includes `source\\src`, public data, native UI assets, tests, docs, and selected public scripts.
- `Frog_Mod_Editor_Runtime_Overlay.zip` is optional. Extract it over the source package to add `source\\python`.
- `Frog_Mod_Editor_Complete_Source_Release.zip` is a one-file package containing the same cleaned source plus the trimmed runtime already expanded.
- `run.bat` prefers `source\\python\\pythonw.exe`, then falls back to `py -3`, then `python`.

Source-only setup needs Python 3.11+ and `PySide6`. Install `pytest` for tests and `Pillow` only when regenerating `source\\src\\native_assets`.

## App Architecture

The shipped desktop app is the PySide6 shell in `source\\src\\native_qt_app.py` and `source\\src\\native_qt`.

- `native_qt\\window.py` owns the main shell, navigation, inspector panels, workspace overview, status footer, quick actions, and pack actions.
- `native_qt\\creator.py` owns the engine and tire creation flows.
- `native_qt\\forms.py` maps parser-backed fields into editor controls.
- `native_qt\\widgets.py` contains shared Qt widgets, delegates, dialogs, metrics, and curve/audio display helpers.
- `native_qt\\theme.py` centralizes branding, icon loading, control sizing, and native asset loading.
- `native_services.py` exposes `NativeEditorService`, the desktop service layer that loads data, edits generated assets, creates parts, and calls the pack routes.
- `api\\routes.py` contains the route-style app operations. The native app calls these directly rather than running a web server.
- `parsers\\` contains the binary readers/writers for Motor Town assets and DataTables.
- `pak_writer.py` writes the final uncompressed pak v8 archives.

The app deliberately stays narrow. It is not a general Unreal editor; it understands the Motor Town asset layouts needed by this workflow and leaves unsupported fields untouched.

## Data Directories

- `source\\data\\vanilla` contains baseline vanilla assets and DataTables used for reading, cloning, and donor row shape.
- `source\\data\\templates\\Engine` contains curated engine template pairs.
- `source\\data\\mod` is the generated workspace. New engines, tires, and DataTable outputs are written here.
- `source\\src\\native_assets` contains QSS, generated PNG artwork, the asset manifest, and SVG icons used by the PySide6 UI.
- `source\\scripts` contains only public helper scripts that are documented or useful for diagnostics.

Game-required paths such as `MotorTown\\Content`, `/Script/MotorTown`, and `/Game/Cars/Parts/...` are kept because Unreal assets and pak paths require them. Those names do not change the Frog Mod Editor branding.

## Parser Overview

The parser is a targeted Motor Town asset tool. It does not try to be a complete Unreal asset editor. The active parser code is in `source\\src\\parsers`.

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

Template engines are small `.uasset` and `.uexp` pairs in `source\\data\\templates\\Engine`. The template packer rebuilds final engine files from vanilla Motor Town donor layouts, then registers every engine in a fresh Engines DataTable.

Every engine asset in `/Cars/Parts/Engine/` needs a matching row and import reference in `/DataAsset/VehicleParts/Engines`. Missing either side can make engines appear with wrong values, fail to appear in shop lists, or crash during load.

The pack-template route:

1. Scans unique template `.uasset` and `.uexp` pairs.
2. Materializes each template against the appropriate donor-backed layout.
3. Registers each generated engine in `Engines.uasset` and `Engines.uexp`.
4. Writes the pak with engine assets plus DataTable files.
5. Verifies expected template count, materialized count, pak engine count, registered row count, and missing template names.

Use `source\\scripts\\inspect_template_pack.py` to diagnose a generated pak. It reports pak entry counts, engine asset counts, DataTable row counts, missing template pairs, and the last registered template row.

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
py -3 -m pytest source\\tests
source\\python\\python.exe source\\src\\native_qt_app.py --smoke-test
source\\python\\python.exe source\\scripts\\inspect_template_pack.py path\\to\\ZZZ_FrogTemplates_P.pak
```

For source-only setups, replace `source\\python\\python.exe` with `py -3` after installing dependencies.

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
"""

RUN_BAT_TEXT = """@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHONW=%ROOT%source\\python\\pythonw.exe"
set "PYTHONEXE=%ROOT%source\\python\\python.exe"
set "APP=%ROOT%source\\src\\native_qt_app.py"

echo Frog Mod Editor
echo ===============
echo.

if exist "%PYTHONW%" (
    echo Launching with bundled runtime overlay...
    start "" "%PYTHONW%" "%APP%"
    exit /b 0
)

if exist "%PYTHONEXE%" (
    echo Launching with bundled runtime overlay...
    start "" "%PYTHONEXE%" "%APP%"
    exit /b 0
)

where py >nul 2>nul
if not errorlevel 1 (
    echo Bundled runtime overlay not found. Launching with system Python via py -3...
    start "" py -3 "%APP%"
    exit /b 0
)

where python >nul 2>nul
if not errorlevel 1 (
    echo Bundled runtime overlay not found. Launching with system Python from PATH...
    start "" python "%APP%"
    exit /b 0
)

echo No usable Python runtime was found.
echo.
echo Either extract Frog_Mod_Editor_Runtime_Overlay.zip over this folder,
echo or install Python 3.11+ and PySide6:
echo.
echo     py -3 -m pip install PySide6
echo.
pause
exit /b 1
"""


def _should_skip(path: Path) -> bool:
    if path.name in SKIP_FILE_NAMES or path.name in SKIP_DIR_NAMES:
        return True
    if path.suffix.lower() in SKIP_FILE_SUFFIXES:
        return True
    return False


def _copy_tree(src: Path, dst: Path) -> None:
    if not src.exists():
        raise FileNotFoundError(f"Missing required path: {src}")
    for root, dirs, files in os.walk(src):
        root_path = Path(root)
        dirs[:] = [name for name in dirs if not _should_skip(root_path / name)]
        rel_root = root_path.relative_to(src)
        target_root = dst / rel_root
        target_root.mkdir(parents=True, exist_ok=True)
        for file_name in files:
            source_file = root_path / file_name
            if _should_skip(source_file):
                continue
            shutil.copy2(source_file, target_root / file_name)


def _copy_file(src: Path, dst: Path) -> None:
    if not src.is_file():
        raise FileNotFoundError(f"Missing required file: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _copy_relative_file_set(src_root: Path, dst_root: Path, rel_paths: list[str]) -> None:
    for rel_path in rel_paths:
        _copy_file(src_root / rel_path, dst_root / rel_path)


def _copy_relative_plugin_files(src_root: Path, dst_root: Path, plugins: dict[str, list[str]]) -> None:
    for folder_name, file_names in plugins.items():
        for file_name in file_names:
            _copy_file(
                src_root / "plugins" / folder_name / file_name,
                dst_root / "plugins" / folder_name / file_name,
            )


def _should_skip_runtime_base(path: Path, rel_path: Path) -> bool:
    if _should_skip(path):
        return True
    rel_parts = tuple(rel_path.parts)
    if matches_prefix(rel_parts, PYTHON_SKIP_PREFIXES):
        return True
    if rel_parts in PYTHON_SKIP_FILES:
        return True
    return False


def _copy_python_runtime_base(src: Path, dst: Path) -> None:
    if not src.exists():
        raise FileNotFoundError(f"Missing required path: {src}")
    for root, dirs, files in os.walk(src):
        root_path = Path(root)
        rel_root = root_path.relative_to(src)
        dirs[:] = [
            name
            for name in dirs
            if not _should_skip_runtime_base(root_path / name, rel_root / name)
        ]
        target_root = dst / rel_root
        target_root.mkdir(parents=True, exist_ok=True)
        for file_name in files:
            source_file = root_path / file_name
            rel_file = rel_root / file_name
            if _should_skip_runtime_base(source_file, rel_file):
                continue
            shutil.copy2(source_file, target_root / file_name)


def _copy_runtime_site_packages() -> None:
    pyside_src = PROJECT_ROOT / PYSIDE_RELATIVE_ROOT
    shiboken_src = PROJECT_ROOT / SHIBOKEN_RELATIVE_ROOT
    if not pyside_src.is_dir():
        raise FileNotFoundError(f"Missing required PySide6 runtime: {pyside_src}")
    if not shiboken_src.is_dir():
        raise FileNotFoundError(f"Missing required shiboken6 runtime: {shiboken_src}")

    runtime_root = RUNTIME_SOURCE_DIR
    _copy_relative_file_set(
        pyside_src,
        runtime_root / PYSIDE_RELATIVE_ROOT,
        list(PYSIDE_REQUIRED_FILES),
    )
    _copy_relative_plugin_files(
        pyside_src,
        runtime_root / PYSIDE_RELATIVE_ROOT,
        dict(PYSIDE_REQUIRED_PLUGIN_FILES),
    )
    _copy_relative_file_set(
        shiboken_src,
        runtime_root / SHIBOKEN_RELATIVE_ROOT,
        list(SHIBOKEN_REQUIRED_FILES),
    )


def _copy_public_scripts() -> None:
    dst = SOURCE_DIR / "scripts"
    dst.mkdir(parents=True, exist_ok=True)
    for name in sorted(PUBLIC_SCRIPT_NAMES):
        _copy_file(PROJECT_ROOT / "scripts" / name, dst / name)


def _copy_desktop_native() -> None:
    desktop_root = PROJECT_ROOT / "desktop_native"
    target_root = SOURCE_DIR / "desktop_native"
    for rel in ("src",):
        _copy_tree(desktop_root / rel, target_root / rel)
    for name in ("app.manifest", "app.rc", "build.rs", "Cargo.lock", "Cargo.toml", "README.md"):
        _copy_file(desktop_root / name, target_root / name)


def _copy_data() -> None:
    _copy_tree(PROJECT_ROOT / "data" / "vanilla", SOURCE_DIR / "data" / "vanilla")
    _copy_tree(PROJECT_ROOT / "data" / "templates" / "Engine", SOURCE_DIR / "data" / "templates" / "Engine")

    vanilla_vp0 = SOURCE_DIR / "data" / "vanilla" / "DataTable" / "VehicleParts0"
    local_vp0 = PROJECT_ROOT / "data" / "vanilla" / "DataTable" / "VehicleParts0"
    extracted_vp0 = (
        PROJECT_ROOT
        / "MotorTown718T7"
        / "MotorTown"
        / "Content"
        / "DataAsset"
        / "VehicleParts"
        / "VehicleParts0"
    )
    if not (vanilla_vp0.with_suffix(".uasset").is_file() and vanilla_vp0.with_suffix(".uexp").is_file()):
        donor_base = local_vp0 if local_vp0.with_suffix(".uasset").is_file() else extracted_vp0
        _copy_file(donor_base.with_suffix(".uasset"), vanilla_vp0.with_suffix(".uasset"))
        _copy_file(donor_base.with_suffix(".uexp"), vanilla_vp0.with_suffix(".uexp"))

    mod_dt = SOURCE_DIR / "data" / "mod" / "MotorTown" / "Content" / "DataAsset" / "VehicleParts"
    mod_dt.mkdir(parents=True, exist_ok=True)
    _copy_file(SOURCE_DIR / "data" / "vanilla" / "DataTable" / "Engines.uasset", mod_dt / "Engines.uasset")
    _copy_file(SOURCE_DIR / "data" / "vanilla" / "DataTable" / "Engines.uexp", mod_dt / "Engines.uexp")
    _copy_file(vanilla_vp0.with_suffix(".uasset"), mod_dt / "VehicleParts0.uasset")
    _copy_file(vanilla_vp0.with_suffix(".uexp"), mod_dt / "VehicleParts0.uexp")

    (SOURCE_DIR / "data" / "mod").mkdir(parents=True, exist_ok=True)
    (SOURCE_DIR / "data" / "mod" / "site_engines.json").write_text(
        json.dumps({"engines": []}, indent=2) + "\n",
        encoding="utf-8",
    )
    (SOURCE_DIR / "data" / "mod" / "site_tires.json").write_text(
        json.dumps({"tires": []}, indent=2) + "\n",
        encoding="utf-8",
    )


def _sanitize_learnings(text: str) -> str:
    replacements = {
        "Frog" + "tuning-style custom DataTable rows as metadata donors": "compatible custom DataTable rows as metadata references",
        "Frog" + "tuning-style": "custom-compatible",
        "Frog" + "tuning assets": "non-vanilla assets",
        "Frog" + "tuning is used only as a metadata reference for DataTable row shape.": "Compatible row structure research is captured in the parser logic; the public bundle uses vanilla data.",
        "legacy Frog" + "tuning compact layout": "legacy compact layout",
        "Frogtuning718": "custom pack",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def _write_docs() -> None:
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    (STAGING_DIR / "README.md").write_text(README_TEXT, encoding="utf-8")
    (STAGING_DIR / "README_ADVANCED_USERS.md").write_text(ADVANCED_README_TEXT, encoding="utf-8")
    (STAGING_DIR / "run.bat").write_text(RUN_BAT_TEXT, encoding="utf-8", newline="\r\n")

    docs_dir = SOURCE_DIR / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    learnings = (PROJECT_ROOT / "LEARNINGS.md").read_text(encoding="utf-8")
    (docs_dir / "LEARNINGS.md").write_text(_sanitize_learnings(learnings), encoding="utf-8")


def _zip_tree(root: Path, zip_path: Path) -> None:
    temp_zip = zip_path.with_suffix(zip_path.suffix + ".tmp")
    if temp_zip.exists():
        temp_zip.unlink()
    with zipfile.ZipFile(temp_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_dir():
                continue
            rel = path.relative_to(root).as_posix()
            info = zipfile.ZipInfo(rel)
            info.date_time = (2026, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            with open(path, "rb") as fh:
                archive.writestr(info, fh.read(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    if zip_path.exists():
        zip_path.unlink()
    temp_zip.replace(zip_path)


def _find_forbidden_release_paths(root: Path) -> list[str]:
    hits: list[str] = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_dir():
            if path.name in FORBIDDEN_RELEASE_DIR_NAMES:
                hits.append(rel + "/")
            continue
        if path.suffix.lower() in FORBIDDEN_RELEASE_SUFFIXES or path.name in SKIP_FILE_NAMES:
            hits.append(rel)
    return hits


def _find_forbidden_release_zip_entries(names: set[str]) -> list[str]:
    hits: list[str] = []
    for name in sorted(names):
        path = Path(name)
        parts = set(path.parts)
        if parts & FORBIDDEN_RELEASE_DIR_NAMES:
            hits.append(name)
            continue
        if path.suffix.lower() in FORBIDDEN_RELEASE_SUFFIXES or path.name in SKIP_FILE_NAMES:
            hits.append(name)
    return hits


def _validate_public_source_tree(root: Path = STAGING_DIR) -> None:
    missing = [rel for rel in sorted(REQUIRED_PUBLIC_SOURCE_PATHS) if not (root / rel).exists()]
    if missing:
        raise RuntimeError("Public source export is missing required paths:\n" + "\n".join(missing))
    if (root / "source" / "python").exists():
        raise RuntimeError("Public source export must not include source/python; use the runtime overlay zip instead.")
    forbidden_paths = _find_forbidden_release_paths(root)
    if forbidden_paths:
        raise RuntimeError("Public source export contains forbidden generated/binary artifacts:\n" + "\n".join(forbidden_paths[:50]))

    asset_root = root / "source" / "src" / "native_assets"
    manifest_path = asset_root / "native_asset_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    referenced_assets = {
        "brand_mark.png",
        "welcome_hero.png",
        "curve_banner.png",
        str((manifest.get("brand_mark") or {}).get("filename") or ""),
    }
    for scene in manifest.get("assets", []):
        for output in scene.get("outputs", []):
            referenced_assets.add(str(output.get("filename") or ""))
    ui_source_root = root / "source" / "src" / "native_qt"
    referenced_icons: set[str] = set()
    for path in ui_source_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        referenced_assets.update(match.group(1) for match in UI_ASSET_REFERENCE_PATTERN.finditer(text))
        referenced_icons.update(match.group(1) for match in UI_ICON_REFERENCE_PATTERN.finditer(text))
    missing_assets = [name for name in sorted(referenced_assets) if name and not (asset_root / name).is_file()]
    if missing_assets:
        raise RuntimeError("Native UI assets are missing from public source export:\n" + "\n".join(missing_assets))

    icon_dir = asset_root / "icons"
    if not any(icon_dir.glob("*.svg")):
        raise RuntimeError("Native icon directory is empty in public source export.")
    missing_icons = [name for name in sorted(referenced_icons) if not (icon_dir / name).is_file()]
    if missing_icons:
        raise RuntimeError("Native UI icons are missing from public source export:\n" + "\n".join(missing_icons))

    branding_hits: list[str] = []
    for rel in sorted(USER_FACING_BRANDING_FILES):
        path = root / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for forbidden in FORBIDDEN_USER_BRANDING:
            if forbidden in text:
                branding_hits.append(f"{rel}: {forbidden}")
    if branding_hits:
        raise RuntimeError("Public source export contains stale user-facing branding:\n" + "\n".join(branding_hits))


def _validate_public_source_zip(zip_path: Path = ZIP_PATH) -> None:
    with zipfile.ZipFile(zip_path, "r") as archive:
        names = set(archive.namelist())
    if any(name == "source/python" or name.startswith("source/python/") for name in names):
        raise RuntimeError("Public source zip must not include source/python; use the runtime overlay zip instead.")
    forbidden_entries = _find_forbidden_release_zip_entries(names)
    if forbidden_entries:
        raise RuntimeError("Public source zip contains forbidden generated/binary artifacts:\n" + "\n".join(forbidden_entries[:50]))
    missing = []
    for rel in sorted(REQUIRED_PUBLIC_SOURCE_PATHS):
        zip_rel = rel.replace("\\", "/")
        if zip_rel in names:
            continue
        prefix = zip_rel.rstrip("/") + "/"
        if not any(name.startswith(prefix) for name in names):
            missing.append(zip_rel)
    if missing:
        raise RuntimeError("Public source zip is missing required entries:\n" + "\n".join(missing))


def _validate_runtime_overlay_tree(root: Path = RUNTIME_STAGING_DIR) -> None:
    missing = [rel for rel in sorted(RUNTIME_REQUIRED_PATHS) if not (root / rel).is_file()]
    if missing:
        raise RuntimeError("Runtime overlay is missing required runtime files:\n" + "\n".join(missing))
    forbidden_paths = _find_forbidden_release_paths(root)
    if forbidden_paths:
        raise RuntimeError("Runtime overlay contains forbidden generated artifacts:\n" + "\n".join(forbidden_paths[:50]))


def _validate_runtime_overlay_zip(zip_path: Path = RUNTIME_ZIP_PATH) -> None:
    with zipfile.ZipFile(zip_path, "r") as archive:
        names = set(archive.namelist())
    missing = [rel for rel in sorted(RUNTIME_REQUIRED_PATHS) if rel not in names]
    if missing:
        raise RuntimeError("Runtime overlay zip is missing required entries:\n" + "\n".join(missing))
    forbidden_entries = _find_forbidden_release_zip_entries(names)
    if forbidden_entries:
        raise RuntimeError("Runtime overlay zip contains forbidden generated artifacts:\n" + "\n".join(forbidden_entries[:50]))


def _workspace_source_for_public_rel(rel: str) -> Path:
    normalized = rel.replace("\\", "/")
    if not normalized.startswith("source/"):
        raise ValueError(f"Workspace match paths must be under source/: {rel}")
    return PROJECT_ROOT / normalized.removeprefix("source/")


def _iter_workspace_match_rels(root: Path = STAGING_DIR) -> list[str]:
    rels: set[str] = set()
    for rel_dir in WORKSPACE_MATCH_DIRS:
        exported_dir = root / rel_dir
        if not exported_dir.is_dir():
            raise RuntimeError(f"Public source export is missing byte-match directory: {rel_dir}")
        for path in sorted(exported_dir.rglob("*")):
            if path.is_dir() or _should_skip(path):
                continue
            rels.add(path.relative_to(root).as_posix())
    for rel_file in WORKSPACE_MATCH_FILES:
        exported_file = root / rel_file
        if not exported_file.is_file():
            raise RuntimeError(f"Public source export is missing byte-match file: {rel_file}")
        rels.add(rel_file)
    return sorted(rels)


def _validate_staged_workspace_matches(root: Path = STAGING_DIR) -> None:
    missing: list[str] = []
    mismatched: list[str] = []
    for rel in _iter_workspace_match_rels(root):
        workspace_file = _workspace_source_for_public_rel(rel)
        exported_file = root / rel
        if not workspace_file.is_file():
            missing.append(rel)
            continue
        if exported_file.read_bytes() != workspace_file.read_bytes():
            mismatched.append(rel)
    if missing or mismatched:
        details = []
        if missing:
            details.append("Missing workspace source files:\n" + "\n".join(missing))
        if mismatched:
            details.append("Exported files differ from the workspace:\n" + "\n".join(mismatched))
        raise RuntimeError("Public source staging does not match the workspace source state:\n" + "\n\n".join(details))


def _validate_zip_workspace_matches(zip_path: Path = ZIP_PATH, root: Path = STAGING_DIR) -> None:
    missing: list[str] = []
    mismatched: list[str] = []
    with zipfile.ZipFile(zip_path, "r") as archive:
        names = set(archive.namelist())
        for rel in _iter_workspace_match_rels(root):
            if rel not in names:
                missing.append(rel)
                continue
            workspace_file = _workspace_source_for_public_rel(rel)
            if not workspace_file.is_file():
                missing.append(rel)
                continue
            if archive.read(rel) != workspace_file.read_bytes():
                mismatched.append(rel)
    if missing or mismatched:
        details = []
        if missing:
            details.append("Missing zip entries:\n" + "\n".join(missing))
        if mismatched:
            details.append("Zip entries differ from the workspace:\n" + "\n".join(mismatched))
        raise RuntimeError("Public source zip does not match the workspace source state:\n" + "\n\n".join(details))


def _build_public_source_tree() -> None:
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    _write_docs()
    _copy_tree(PROJECT_ROOT / "src", SOURCE_DIR / "src")
    _copy_public_scripts()
    _copy_tree(PROJECT_ROOT / "tests", SOURCE_DIR / "tests")
    _copy_desktop_native()
    _copy_data()
    _copy_file(PROJECT_ROOT / "pytest.ini", SOURCE_DIR / "pytest.ini")
    _copy_file(PROJECT_ROOT / "build_real_template_engines.py", SOURCE_DIR / "build_real_template_engines.py")


def _build_runtime_overlay_tree() -> None:
    RUNTIME_SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    _copy_python_runtime_base(PROJECT_ROOT / "python", RUNTIME_SOURCE_DIR / "python")
    _copy_runtime_site_packages()


def export_public_source_zip() -> Path:
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    if STAGING_DIR.exists():
        shutil.rmtree(STAGING_DIR)
    if RUNTIME_STAGING_DIR.exists():
        shutil.rmtree(RUNTIME_STAGING_DIR)

    _build_public_source_tree()
    _validate_public_source_tree(STAGING_DIR)
    _validate_staged_workspace_matches(STAGING_DIR)
    _zip_tree(STAGING_DIR, ZIP_PATH)
    _validate_public_source_zip(ZIP_PATH)
    _validate_zip_workspace_matches(ZIP_PATH, STAGING_DIR)

    _build_runtime_overlay_tree()
    _validate_runtime_overlay_tree(RUNTIME_STAGING_DIR)
    _zip_tree(RUNTIME_STAGING_DIR, RUNTIME_ZIP_PATH)
    _validate_runtime_overlay_zip(RUNTIME_ZIP_PATH)
    return ZIP_PATH


def main() -> int:
    zip_path = export_public_source_zip()
    print(f"Public source directory: {STAGING_DIR}")
    print(f"Public source zip: {zip_path}")
    print(f"Runtime overlay directory: {RUNTIME_STAGING_DIR}")
    print(f"Runtime overlay zip: {RUNTIME_ZIP_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
