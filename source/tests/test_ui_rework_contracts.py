from __future__ import annotations

import zipfile
from pathlib import Path

from PySide6 import QtCore, QtGui

import native_qt_app
from native_qt.creator import CreatorCatalogSidebar
from native_qt.theme import ICON_DIR, ICON_SIZES, load_icon_pixmap
from native_services import NativeEditorService
import export_complete_source_release_zip
import export_public_source_zip


PROJECT_ROOT = Path(__file__).resolve().parents[1]
THEME_QSS = PROJECT_ROOT / "src" / "native_assets" / "native_qt_theme.qss"


def _opaque_bounds(pixmap: QtGui.QPixmap) -> QtCore.QRect:
    image = pixmap.toImage().convertToFormat(QtGui.QImage.Format.Format_ARGB32)
    min_x = image.width()
    min_y = image.height()
    max_x = -1
    max_y = -1
    for y in range(image.height()):
        for x in range(image.width()):
            if QtGui.QColor.fromRgba(image.pixel(x, y)).alpha() <= 0:
                continue
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
    if max_x < min_x or max_y < min_y:
        return QtCore.QRect()
    return QtCore.QRect(min_x, min_y, (max_x - min_x) + 1, (max_y - min_y) + 1)


def test_standard_icons_stay_inside_target_canvas(qapp):
    sizes = {
        ICON_SIZES.inline,
        ICON_SIZES.button,
        ICON_SIZES.primary_button,
        ICON_SIZES.launcher,
        ICON_SIZES.tab,
        ICON_SIZES.tree,
        ICON_SIZES.list_row,
        ICON_SIZES.empty_state,
    }
    for icon_path in sorted(ICON_DIR.glob("*.svg")):
        for size in sizes:
            bounds = _opaque_bounds(load_icon_pixmap(icon_path.name, size, color="#ffffff"))
            assert not bounds.isNull(), f"{icon_path.name} rendered blank at {size}px"
            assert bounds.width() <= size, f"{icon_path.name} overflows width at {size}px"
            assert bounds.height() <= size, f"{icon_path.name} overflows height at {size}px"


def test_topbar_actions_have_headroom_at_supported_widths(qapp, qtbot):
    for width, height in ((1280, 800), (1600, 980), (2200, 1200)):
        window = native_qt_app.NativeQtEditorWindow(NativeEditorService(), smoke_test=True)
        qtbot.addWidget(window)
        window.resize(width, height)
        window.show()
        qapp.processEvents()
        assert window.command_bar.height() >= window.status_label.sizeHint().height() + 8
        for button in (window.reload_button, window.command_button, window.pack_templates_button, window.pack_mod_button):
            assert button.height() >= button.fontMetrics().height() + 12
            assert button.iconSize().width() <= ICON_SIZES.primary_button


def test_theme_restores_readable_font_and_scoped_input_rules():
    qss = THEME_QSS.read_text(encoding="utf-8")
    assert 'font-family: "Segoe UI";' in qss
    assert "Segoe UI Variable Text" not in qss
    assert "QLineEdit,\nQComboBox,\nQPlainTextEdit,\nQTreeWidget" not in qss
    assert "QTreeWidget,\nQListView" in qss or "QTreeWidget,\nQListWidget" in qss


def test_creator_header_no_longer_crowds_form_area(qapp, qtbot):
    window = native_qt_app.NativeQtEditorWindow(NativeEditorService(), smoke_test=True)
    qtbot.addWidget(window)
    window.resize(1280, 800)
    window.show()
    qapp.processEvents()
    window.open_engine_creator()
    qapp.processEvents()

    creator = window.creator_workspace
    assert not hasattr(creator, "scene_preview_label")
    assert creator.header_frame.height() <= 96
    assert creator.scroll.viewport().height() >= 250
    rendered_fields = list((creator.form.property_widgets if creator.form else {}).values())
    assert rendered_fields
    assert min(field.height() for field in rendered_fields[:6]) >= 24
    assert window.search_edit.placeholderText() == "Search parts"
    assert window.search_edit.width() >= window.search_edit.sizeHint().width() - 4


def test_engine_catalog_all_variants_prefers_gas_aggregate_duplicate():
    rows = [
        {"name": "2JZ320HP", "title": "Toyota 2JZ-GTE 3.0L Twin-Turbo I6", "group_key": "cyl_6", "group_label": "6 Cylinder", "variant": "ice_compact"},
        {"name": "2JZ320HP", "title": "Toyota 2JZ-GTE 3.0L Twin-Turbo I6", "group_key": "gas", "group_label": "Gas", "variant": "ice_standard"},
        {"name": "30tdi", "title": "Audi 3.0 TDI", "group_key": "diesel_hd", "group_label": "Diesel HD"},
    ]

    deduped = CreatorCatalogSidebar._dedupe_all_engine_variant_rows(rows)

    assert [row["name"] for row in deduped] == ["2JZ320HP", "30tdi"]
    assert deduped[0]["group_label"] == "Gas"
    assert deduped[0]["variant"] == "ice_compact"


def test_user_facing_branding_uses_frog_mod_editor():
    files = [
        PROJECT_ROOT / "run.bat",
        PROJECT_ROOT / "desktop_native" / "app.manifest",
        PROJECT_ROOT / "desktop_native" / "app.rc",
        PROJECT_ROOT / "desktop_native" / "README.md",
        PROJECT_ROOT / "scripts" / "export_public_source_zip.py",
        PROJECT_ROOT / "scripts" / "export_native_desktop_exe.py",
        PROJECT_ROOT / "scripts" / "export_obfuscated_full_project_bundle.py",
        PROJECT_ROOT / "scripts" / "export_full_project_source_bundle.py",
        PROJECT_ROOT / "scripts" / "export_rust_native_source_bundle.py",
    ]
    forbidden = (
        "Motor Town" + " Mod Editor",
        "Motor Town" + " Mod Workbench",
        "MotorTown" + "ModEditor.exe",
        "MotorTown" + "ModEditor_",
        "FrogTuning" + "Desktop",
    )
    hits = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for needle in forbidden:
            if needle in text:
                hits.append(f"{path.relative_to(PROJECT_ROOT)}: {needle}")
    assert not hits, "\n".join(hits)


def test_public_source_validation_accepts_required_ui_assets(tmp_path):
    root = tmp_path / "public"
    required = export_public_source_zip.REQUIRED_PUBLIC_SOURCE_PATHS
    for rel in required:
        path = root / rel
        if path.suffix:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.name == "native_asset_manifest.json":
                path.write_text(
                    '{"assets":[{"outputs":[{"filename":"welcome_hero.png"}]}],"brand_mark":{"filename":"brand_mark.png"}}',
                    encoding="utf-8",
                )
            else:
                path.write_text("Frog Mod Editor\n", encoding="utf-8")
        else:
            path.mkdir(parents=True, exist_ok=True)
            (path / ".keep").write_text("Frog Mod Editor\n", encoding="utf-8")
    asset_root = root / "source" / "src" / "native_assets"
    (asset_root / "welcome_hero.png").write_bytes(b"png")
    (asset_root / "brand_mark.png").write_bytes(b"png")
    (asset_root / "curve_banner.png").write_bytes(b"png")
    (asset_root / "icons" / "parts.svg").write_text("<svg></svg>", encoding="utf-8")

    export_public_source_zip._validate_public_source_tree(root)

    zip_path = tmp_path / "source.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        for path in root.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(root).as_posix())
    export_public_source_zip._validate_public_source_zip(zip_path)


def test_public_source_validation_rejects_missing_split_qt_module(tmp_path):
    root = tmp_path / "public"
    for rel in export_public_source_zip.REQUIRED_PUBLIC_SOURCE_PATHS:
        path = root / rel
        if path.suffix:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.name == "native_asset_manifest.json":
                path.write_text(
                    '{"assets":[{"outputs":[{"filename":"welcome_hero.png"},{"filename":"curve_banner.png"}]}],"brand_mark":{"filename":"brand_mark.png"}}',
                    encoding="utf-8",
                )
            else:
                path.write_text("Frog Mod Editor\n", encoding="utf-8")
        else:
            path.mkdir(parents=True, exist_ok=True)
            (path / ".keep").write_text("Frog Mod Editor\n", encoding="utf-8")
    asset_root = root / "source" / "src" / "native_assets"
    (asset_root / "welcome_hero.png").write_bytes(b"png")
    (asset_root / "brand_mark.png").write_bytes(b"png")
    (asset_root / "curve_banner.png").write_bytes(b"png")
    (asset_root / "icons" / "parts.svg").write_text("<svg></svg>", encoding="utf-8")

    (root / "source" / "src" / "native_qt" / "forms.py").unlink()

    try:
        export_public_source_zip._validate_public_source_tree(root)
    except RuntimeError as exc:
        assert "source/src/native_qt/forms.py" in str(exc)
    else:
        raise AssertionError("validator accepted a public source tree with a missing Qt split module")


def test_public_source_validation_rejects_missing_referenced_svg_icon(tmp_path):
    root = tmp_path / "public"
    for rel in export_public_source_zip.REQUIRED_PUBLIC_SOURCE_PATHS:
        path = root / rel
        if path.suffix:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.name == "native_asset_manifest.json":
                path.write_text(
                    '{"assets":[{"outputs":[{"filename":"welcome_hero.png"},{"filename":"curve_banner.png"}]}],"brand_mark":{"filename":"brand_mark.png"}}',
                    encoding="utf-8",
                )
            else:
                path.write_text("Frog Mod Editor\n", encoding="utf-8")
        else:
            path.mkdir(parents=True, exist_ok=True)
            (path / ".keep").write_text("Frog Mod Editor\n", encoding="utf-8")
    asset_root = root / "source" / "src" / "native_assets"
    (asset_root / "welcome_hero.png").write_bytes(b"png")
    (asset_root / "brand_mark.png").write_bytes(b"png")
    (asset_root / "curve_banner.png").write_bytes(b"png")
    (asset_root / "icons" / "parts.svg").write_text("<svg></svg>", encoding="utf-8")
    (root / "source" / "src" / "native_qt" / "window.py").write_text(
        'from native_qt.theme import load_icon\nicon = load_icon("missing.svg")\n',
        encoding="utf-8",
    )

    try:
        export_public_source_zip._validate_public_source_tree(root)
    except RuntimeError as exc:
        assert "missing.svg" in str(exc)
    else:
        raise AssertionError("validator accepted a public source tree with a missing referenced SVG icon")


def test_real_public_source_export_zip_contains_ui_contract_files(tmp_path, monkeypatch):
    staging = tmp_path / "frog_mod_editor_public_source"
    zip_path = tmp_path / "Frog_Mod_Editor_Public_Source.zip"
    runtime_staging = tmp_path / "frog_mod_editor_runtime_overlay"
    runtime_zip_path = tmp_path / "Frog_Mod_Editor_Runtime_Overlay.zip"

    def copy_stubbed_runtime_base(src: Path, dst: Path) -> None:
        dst.mkdir(parents=True, exist_ok=True)
        (dst / "python.exe").write_bytes(b"")
        (dst / "pythonw.exe").write_bytes(b"")
        (dst / "Lib" / "encodings").mkdir(parents=True, exist_ok=True)
        (dst / "Lib" / "encodings" / "__init__.py").write_text("", encoding="utf-8")

    def copy_stubbed_runtime_site_packages() -> None:
        pyside = (
            export_public_source_zip.RUNTIME_SOURCE_DIR
            / "python"
            / "Lib"
            / "site-packages"
            / "PySide6"
        )
        shiboken = (
            export_public_source_zip.RUNTIME_SOURCE_DIR
            / "python"
            / "Lib"
            / "site-packages"
            / "shiboken6"
        )
        pyside.mkdir(parents=True, exist_ok=True)
        shiboken.mkdir(parents=True, exist_ok=True)
        for name in ("__init__.py", "QtCore.pyd", "QtGui.pyd", "QtWidgets.pyd", "QtCharts.pyd", "QtSvg.pyd"):
            (pyside / name).write_bytes(b"")
        (pyside / "plugins" / "platforms").mkdir(parents=True, exist_ok=True)
        (pyside / "plugins" / "platforms" / "qwindows.dll").write_bytes(b"")
        (shiboken / "Shiboken.pyd").write_bytes(b"")

    monkeypatch.setattr(export_public_source_zip, "_copy_python_runtime_base", copy_stubbed_runtime_base)
    monkeypatch.setattr(export_public_source_zip, "_copy_runtime_site_packages", copy_stubbed_runtime_site_packages)
    monkeypatch.setattr(export_public_source_zip, "BACKUPS_DIR", tmp_path)
    monkeypatch.setattr(export_public_source_zip, "STAGING_DIR", staging)
    monkeypatch.setattr(export_public_source_zip, "ZIP_PATH", zip_path)
    monkeypatch.setattr(export_public_source_zip, "SOURCE_DIR", staging / "source")
    monkeypatch.setattr(export_public_source_zip, "RUNTIME_STAGING_DIR", runtime_staging)
    monkeypatch.setattr(export_public_source_zip, "RUNTIME_ZIP_PATH", runtime_zip_path)
    monkeypatch.setattr(export_public_source_zip, "RUNTIME_SOURCE_DIR", runtime_staging / "source")

    result = export_public_source_zip.export_public_source_zip()
    assert result == zip_path
    with zipfile.ZipFile(result, "r") as archive:
        names = set(archive.namelist())
    with zipfile.ZipFile(runtime_zip_path, "r") as archive:
        runtime_names = set(archive.namelist())

    for rel in (
        "source/src/native_qt/theme.py",
        "source/src/native_qt/window.py",
        "source/src/native_qt/creator.py",
        "source/src/native_qt/forms.py",
        "source/src/native_qt/widgets.py",
        "source/src/native_assets/native_qt_theme.qss",
        "source/src/native_assets/brand_mark.png",
        "source/src/native_assets/welcome_hero.png",
        "source/src/native_assets/curve_banner.png",
        "source/tests/test_native_qt_button_contracts.py",
        "source/tests/test_native_qt_input_contracts.py",
        "source/tests/test_native_qt_overview_card_contracts.py",
        "source/tests/test_native_qt_template_row_contracts.py",
        "source/scripts/export_complete_source_release_zip.py",
        "source/scripts/export_public_source_zip.py",
        "source/scripts/export_runtime_manifest.py",
        "source/scripts/generate_native_ui_assets.py",
        "source/scripts/inspect_template_pack.py",
    ):
        assert rel in names
    assert not any(name == "source/python" or name.startswith("source/python/") for name in names)
    assert "source/python/python.exe" in runtime_names
    assert "source/python/pythonw.exe" in runtime_names
    assert "source/python/Lib/site-packages/PySide6/QtWidgets.pyd" in runtime_names

    with zipfile.ZipFile(result, "r") as archive:
        assert archive.read("source/src/native_qt/window.py") == (PROJECT_ROOT / "src" / "native_qt" / "window.py").read_bytes()
        assert archive.read("source/src/native_assets/native_qt_theme.qss") == THEME_QSS.read_bytes()
        assert archive.read("source/scripts/export_public_source_zip.py") == (
            PROJECT_ROOT / "scripts" / "export_public_source_zip.py"
        ).read_bytes()


def test_complete_source_release_export_contains_clean_source_and_runtime(tmp_path, monkeypatch):
    staging = tmp_path / "frog_mod_editor_public_source"
    zip_path = tmp_path / "Frog_Mod_Editor_Public_Source.zip"
    runtime_staging = tmp_path / "frog_mod_editor_runtime_overlay"
    runtime_zip_path = tmp_path / "Frog_Mod_Editor_Runtime_Overlay.zip"
    complete_staging = tmp_path / "frog_mod_editor_complete_source_release"
    complete_zip_path = tmp_path / "Frog_Mod_Editor_Complete_Source_Release.zip"

    def copy_stubbed_runtime_base(src: Path, dst: Path) -> None:
        dst.mkdir(parents=True, exist_ok=True)
        (dst / "python.exe").write_bytes(b"")
        (dst / "pythonw.exe").write_bytes(b"")
        (dst / "Lib" / "encodings").mkdir(parents=True, exist_ok=True)
        (dst / "Lib" / "encodings" / "__init__.py").write_text("", encoding="utf-8")

    def copy_stubbed_runtime_site_packages() -> None:
        pyside = (
            export_public_source_zip.RUNTIME_SOURCE_DIR
            / "python"
            / "Lib"
            / "site-packages"
            / "PySide6"
        )
        shiboken = (
            export_public_source_zip.RUNTIME_SOURCE_DIR
            / "python"
            / "Lib"
            / "site-packages"
            / "shiboken6"
        )
        pyside.mkdir(parents=True, exist_ok=True)
        shiboken.mkdir(parents=True, exist_ok=True)
        for name in ("__init__.py", "QtCore.pyd", "QtGui.pyd", "QtWidgets.pyd", "QtCharts.pyd", "QtSvg.pyd"):
            (pyside / name).write_bytes(b"")
        (pyside / "plugins" / "platforms").mkdir(parents=True, exist_ok=True)
        (pyside / "plugins" / "platforms" / "qwindows.dll").write_bytes(b"")
        (shiboken / "Shiboken.pyd").write_bytes(b"")

    monkeypatch.setattr(export_public_source_zip, "_copy_python_runtime_base", copy_stubbed_runtime_base)
    monkeypatch.setattr(export_public_source_zip, "_copy_runtime_site_packages", copy_stubbed_runtime_site_packages)
    monkeypatch.setattr(export_public_source_zip, "BACKUPS_DIR", tmp_path)
    monkeypatch.setattr(export_public_source_zip, "STAGING_DIR", staging)
    monkeypatch.setattr(export_public_source_zip, "ZIP_PATH", zip_path)
    monkeypatch.setattr(export_public_source_zip, "SOURCE_DIR", staging / "source")
    monkeypatch.setattr(export_public_source_zip, "RUNTIME_STAGING_DIR", runtime_staging)
    monkeypatch.setattr(export_public_source_zip, "RUNTIME_ZIP_PATH", runtime_zip_path)
    monkeypatch.setattr(export_public_source_zip, "RUNTIME_SOURCE_DIR", runtime_staging / "source")
    monkeypatch.setattr(export_complete_source_release_zip, "BACKUPS_DIR", tmp_path)
    monkeypatch.setattr(export_complete_source_release_zip, "COMPLETE_STAGING_DIR", complete_staging)
    monkeypatch.setattr(export_complete_source_release_zip, "COMPLETE_ZIP_PATH", complete_zip_path)

    result = export_complete_source_release_zip.export_complete_source_release_zip()

    assert result == complete_zip_path
    with zipfile.ZipFile(zip_path, "r") as archive:
        split_names = set(archive.namelist())
    with zipfile.ZipFile(result, "r") as archive:
        complete_names = set(archive.namelist())

    assert not any(name == "source/python" or name.startswith("source/python/") for name in split_names)
    for rel in (
        "README.md",
        "README_ADVANCED_USERS.md",
        "run.bat",
        "source/src/native_qt/window.py",
        "source/src/native_assets/native_qt_theme.qss",
        "source/scripts/export_complete_source_release_zip.py",
        "source/scripts/export_public_source_zip.py",
        "source/tests/test_native_qt_template_row_contracts.py",
        "source/python/python.exe",
        "source/python/pythonw.exe",
        "source/python/Lib/site-packages/PySide6/QtWidgets.pyd",
        "source/python/Lib/site-packages/shiboken6/Shiboken.pyd",
    ):
        assert rel in complete_names

    forbidden = [
        name
        for name in complete_names
        if name.endswith((".pyc", ".pyo", ".tmp", ".log", ".pak"))
        or "__pycache__" in name
        or ".pytest_cache" in name
    ]
    assert not forbidden

    with zipfile.ZipFile(result, "r") as archive:
        assert archive.read("source/src/native_qt/window.py") == (PROJECT_ROOT / "src" / "native_qt" / "window.py").read_bytes()
        assert archive.read("source/scripts/export_complete_source_release_zip.py") == (
            PROJECT_ROOT / "scripts" / "export_complete_source_release_zip.py"
        ).read_bytes()


def test_public_source_readmes_document_noncommercial_license():
    assert "CC BY-NC 4.0" in export_public_source_zip.README_TEXT
    assert "You may not sell it" in export_public_source_zip.README_TEXT
    assert "CC BY-NC 4.0" in export_public_source_zip.ADVANCED_README_TEXT
    assert "DataTable Flow" in export_public_source_zip.ADVANCED_README_TEXT
    assert "Template Pack Flow" in export_public_source_zip.ADVANCED_README_TEXT
    assert "Frog_Mod_Editor_Complete_Source_Release.zip" in export_public_source_zip.README_TEXT
    assert "export_complete_source_release_zip.py" in export_public_source_zip.ADVANCED_README_TEXT


def test_runtime_overlay_validation_rejects_generated_artifacts(tmp_path):
    root = tmp_path / "runtime"
    for rel in export_public_source_zip.RUNTIME_REQUIRED_PATHS:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"runtime")
    (root / "source" / "python" / "Lib" / "__pycache__").mkdir(parents=True)
    (root / "source" / "python" / "Lib" / "__pycache__" / "bad.pyc").write_bytes(b"bad")

    try:
        export_public_source_zip._validate_runtime_overlay_tree(root)
    except RuntimeError as exc:
        assert "forbidden generated artifacts" in str(exc)
    else:
        raise AssertionError("runtime overlay validation accepted generated cache artifacts")
