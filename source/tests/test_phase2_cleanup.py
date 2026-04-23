from __future__ import annotations

from pathlib import Path

import native_qt_app


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
QT_ROOT = SRC_ROOT / "native_qt"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_native_qt_app_keeps_stable_entrypoints():
    assert callable(native_qt_app.apply_theme)
    assert native_qt_app.NativeQtEditorWindow.__name__ == "NativeQtEditorWindow"
    assert callable(native_qt_app.main)


def test_legacy_surfaces_removed_from_workspace():
    assert not (SRC_ROOT / "native_app.py").exists()
    assert not (SRC_ROOT / "server.py").exists()
    assert not (PROJECT_ROOT / "web").exists()


def test_dead_creator_classes_removed_from_active_qt_sources():
    active_sources = [_read_text(SRC_ROOT / "native_qt_app.py")]
    active_sources.extend(_read_text(path) for path in sorted(QT_ROOT.glob("*.py")))
    combined = "\n".join(active_sources)
    for class_name in ("CreatorFieldForm", "EngineCreateDialog", "TireCreateDialog"):
        assert class_name not in combined


def test_active_launchers_exporters_and_docs_do_not_reference_legacy_surfaces():
    public_root = PROJECT_ROOT.parent if (PROJECT_ROOT.parent / "run.bat").exists() else PROJECT_ROOT
    files_to_check = [
        public_root / "run.bat",
        PROJECT_ROOT / "desktop_native" / "README.md",
        PROJECT_ROOT / "scripts" / "export_native_desktop_exe.py",
        PROJECT_ROOT / "scripts" / "export_full_project_source_bundle.py",
        PROJECT_ROOT / "scripts" / "export_obfuscated_full_project_bundle.py",
        PROJECT_ROOT / "scripts" / "export_rust_native_source_bundle.py",
    ]
    forbidden_strings = (
        "localhost:8090",
        "src/server.py",
        "src\\server.py",
        "web/index.html",
        "src/native_app.py",
        "src\\native_app.py",
    )
    hits: list[str] = []
    for path in files_to_check:
        if not path.exists():
            continue
        text = _read_text(path)
        for forbidden in forbidden_strings:
            if forbidden in text:
                hits.append(f"{path.name}: {forbidden}")
    assert not hits, "\n".join(hits)
