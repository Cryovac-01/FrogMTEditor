from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Iterable, Sequence


COMMON_RUNTIME_DIRS = (
    Path("data/mod"),
    Path("data/templates/Engine"),
    Path("data/vanilla"),
    Path("src/native_assets"),
)

RUNTIME_AUDIO_FILES = (
    Path("data/audio/engine_audio_manifest.json"),
    Path("data/audio/engine_sound_overrides.json"),
    Path("data/audio/engine_audio_toolchain.json"),
    Path("data/audio/research/engine_audio_source_shortlist.json"),
)

ROOT_RUNTIME_FILES = (
    Path("run.bat"),
)

DONOR_TREE_DIRS = (
    Path("Frogtuning718T7/MotorTown/Content/Cars/Parts/Tire"),
)

DONOR_FILES = (
    Path("MotorTown718T7/MotorTown/Content/DataAsset/VehicleParts/VehicleParts0.uasset"),
    Path("MotorTown718T7/MotorTown/Content/DataAsset/VehicleParts/VehicleParts0.uexp"),
    Path("Frogtuning718T7/MotorTown/Content/DataAsset/VehicleParts/Engines.uasset"),
    Path("Frogtuning718T7/MotorTown/Content/DataAsset/VehicleParts/Engines.uexp"),
    Path("Frogtuning718T7/MotorTown/Content/DataAsset/VehicleParts/VehicleParts0.uasset"),
    Path("Frogtuning718T7/MotorTown/Content/DataAsset/VehicleParts/VehicleParts0.uexp"),
)

PYSIDE_RELATIVE_ROOT = Path("python/Lib/site-packages/PySide6")
SHIBOKEN_RELATIVE_ROOT = Path("python/Lib/site-packages/shiboken6")

PYSIDE_REQUIRED_FILES = [
    "__init__.py",
    "_config.py",
    "pyside6.abi3.dll",
    "QtCore.pyd",
    "QtGui.pyd",
    "QtWidgets.pyd",
    "QtCharts.pyd",
    "QtSvg.pyd",
    "QtOpenGL.pyd",
    "QtOpenGLWidgets.pyd",
    "QtPrintSupport.pyd",
    "QtNetwork.pyd",
    "QtXml.pyd",
    "QtDBus.pyd",
    "Qt6Core.dll",
    "Qt6Gui.dll",
    "Qt6Widgets.dll",
    "Qt6Charts.dll",
    "Qt6Svg.dll",
    "Qt6OpenGL.dll",
    "Qt6OpenGLWidgets.dll",
    "Qt6PrintSupport.dll",
    "Qt6Network.dll",
    "Qt6Xml.dll",
    "Qt6DBus.dll",
    "opengl32sw.dll",
    "concrt140.dll",
    "msvcp140.dll",
    "msvcp140_1.dll",
    "msvcp140_2.dll",
    "msvcp140_codecvt_ids.dll",
    "vcamp140.dll",
    "vccorlib140.dll",
    "vcomp140.dll",
    "vcruntime140.dll",
    "vcruntime140_1.dll",
]

PYSIDE_REQUIRED_PLUGIN_FILES = {
    "platforms": ["qwindows.dll", "qminimal.dll"],
    "iconengines": ["qsvgicon.dll"],
    "imageformats": ["qsvg.dll", "qico.dll", "qjpeg.dll"],
    "styles": ["qmodernwindowsstyle.dll"],
}

SHIBOKEN_REQUIRED_FILES = [
    "__init__.py",
    "_config.py",
    "Shiboken.pyd",
    "shiboken6.abi3.dll",
]

IGNORE_NAMES = {"__pycache__", ".DS_Store"}
IGNORE_SUFFIXES = {".pyc", ".pyo"}

PYTHON_SKIP_PREFIXES = (
    ("Lib", "ensurepip"),
    ("Lib", "idlelib"),
    ("Lib", "site-packages"),
    ("Lib", "tkinter"),
    ("Lib", "test"),
    ("Lib", "turtledemo"),
    ("Lib", "venv"),
    ("Scripts",),
    ("Tools",),
    ("tcl",),
)

PYTHON_SKIP_FILES = {
    ("DLLs", "_tkinter.pyd"),
    ("DLLs", "tcl86t.dll"),
    ("DLLs", "tk86t.dll"),
}

SHARE_ALLOWED_PREFIXES = (
    "python/",
    "src/",
    "data/mod/",
    "data/templates/Engine/",
    "data/vanilla/",
    "Frogtuning718T7/MotorTown/Content/Cars/Parts/Tire/",
    "Frogtuning718T7/MotorTown/Content/DataAsset/VehicleParts/",
    "MotorTown718T7/MotorTown/Content/DataAsset/VehicleParts/",
    "backups/",
)

SHARE_ALLOWED_FILES = {
    "run.bat",
    "README_WINDOWS_BUILD.md",
    *{path.as_posix() for path in RUNTIME_AUDIO_FILES},
}

SHARE_FORBIDDEN_PREFIXES = (
    "MotorTown718T7/MotorTown/Content/Cars/Models/",
    "Frogtuning718T7/MotorTown/Content/Cars/Parts/Engine/Sound/",
    "python/Lib/site-packages/numpy",
    "python/Lib/site-packages/numpy.libs/",
    "python/Lib/site-packages/imageio_ffmpeg/",
    "python/Lib/site-packages/PySide6/Qt6WebEngine",
    "python/Lib/site-packages/PySide6/resources/qtwebengine",
)

SHARE_REQUIRED_FILES = (
    Path("run.bat"),
    Path("src/native_qt_app.py"),
    Path("src/native_assets/native_qt_theme.qss"),
    Path("data/audio/engine_audio_manifest.json"),
    Path("data/audio/engine_sound_overrides.json"),
    Path("data/mod/site_engines.json"),
    Path("data/mod/site_tires.json"),
    Path("data/templates/Engine/13b.uexp"),
    Path("data/vanilla/DataTable/Engines.uasset"),
    Path("data/vanilla/DataTable/Engines.uexp"),
    Path("Frogtuning718T7/MotorTown/Content/DataAsset/VehicleParts/Engines.uasset"),
    Path("Frogtuning718T7/MotorTown/Content/DataAsset/VehicleParts/Engines.uexp"),
    Path("Frogtuning718T7/MotorTown/Content/DataAsset/VehicleParts/VehicleParts0.uasset"),
    Path("Frogtuning718T7/MotorTown/Content/DataAsset/VehicleParts/VehicleParts0.uexp"),
    Path("MotorTown718T7/MotorTown/Content/DataAsset/VehicleParts/VehicleParts0.uasset"),
    Path("MotorTown718T7/MotorTown/Content/DataAsset/VehicleParts/VehicleParts0.uexp"),
    Path("python/python.exe"),
    Path("python/pythonw.exe"),
    Path("python/Lib/encodings/__init__.py"),
    Path("python/Lib/site-packages/PySide6/QtWidgets.pyd"),
    Path("python/Lib/site-packages/shiboken6/Shiboken.pyd"),
)

SHARE_REQUIRED_PREFIX_CONTENT = (
    "Frogtuning718T7/MotorTown/Content/Cars/Parts/Tire/",
)

MAX_SHARE_BUNDLE_STAGE_BYTES = 140 * 1024 * 1024
MAX_SHARE_BUNDLE_ZIP_BYTES = 150 * 1024 * 1024


def normalize_relative_path(path: str | Path) -> str:
    return str(path).replace("\\", "/").lstrip("./")


def matches_prefix(parts: tuple[str, ...], prefixes: tuple[tuple[str, ...], ...]) -> bool:
    return any(parts[: len(prefix)] == prefix for prefix in prefixes)


def should_skip_runtime_tree(tree_name: str, rel_path: Path) -> bool:
    if rel_path.name in IGNORE_NAMES or rel_path.suffix.lower() in IGNORE_SUFFIXES:
        return True
    if tree_name != "python":
        return False
    rel_parts = tuple(rel_path.parts)
    if matches_prefix(rel_parts, PYTHON_SKIP_PREFIXES):
        return True
    return rel_parts in PYTHON_SKIP_FILES


def stage_size_bytes(stage_root: Path) -> int:
    return sum(path.stat().st_size for path in stage_root.rglob("*") if path.is_file())


def is_allowed_share_bundle_path(rel_path: str | Path) -> bool:
    normalized = normalize_relative_path(rel_path)
    if is_forbidden_share_bundle_path(normalized):
        return False
    if normalized in SHARE_ALLOWED_FILES:
        return True
    return any(normalized.startswith(prefix) for prefix in SHARE_ALLOWED_PREFIXES)


def is_forbidden_share_bundle_path(rel_path: str | Path) -> bool:
    normalized = normalize_relative_path(rel_path)
    return any(normalized.startswith(prefix) for prefix in SHARE_FORBIDDEN_PREFIXES)


def _collect_share_bundle_violations(rel_paths: Sequence[str]) -> list[str]:
    violations: list[str] = []
    unexpected = sorted(path for path in rel_paths if not is_allowed_share_bundle_path(path))
    forbidden = sorted(path for path in rel_paths if is_forbidden_share_bundle_path(path))
    missing_files = sorted(
        path.as_posix()
        for path in SHARE_REQUIRED_FILES
        if path.as_posix() not in rel_paths
    )
    missing_prefixes = sorted(
        prefix
        for prefix in SHARE_REQUIRED_PREFIX_CONTENT
        if not any(path.startswith(prefix) for path in rel_paths)
    )
    if unexpected:
        violations.append("Unexpected staged paths:\n" + "\n".join(unexpected[:25]))
    if forbidden:
        violations.append("Forbidden staged paths:\n" + "\n".join(forbidden[:25]))
    if missing_files:
        violations.append("Missing required staged files:\n" + "\n".join(missing_files[:25]))
    if missing_prefixes:
        violations.append("Missing required staged content prefixes:\n" + "\n".join(missing_prefixes))
    return violations


def validate_share_bundle_tree(stage_root: Path) -> None:
    rel_paths = sorted(
        normalize_relative_path(path.relative_to(stage_root))
        for path in stage_root.rglob("*")
        if path.is_file()
    )
    violations = _collect_share_bundle_violations(rel_paths)
    total_bytes = stage_size_bytes(stage_root)
    if total_bytes > MAX_SHARE_BUNDLE_STAGE_BYTES:
        violations.append(
            f"Staged bundle size {total_bytes / (1024 * 1024):.2f} MB exceeds "
            f"{MAX_SHARE_BUNDLE_STAGE_BYTES / (1024 * 1024):.2f} MB."
        )
    if violations:
        raise ValueError("\n\n".join(violations))


def validate_share_bundle_zip(zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "r") as archive:
        rel_paths = sorted(
            normalize_relative_path(name)
            for name in archive.namelist()
            if name and not name.endswith("/")
        )
    violations = _collect_share_bundle_violations(rel_paths)
    zip_size = zip_path.stat().st_size
    if zip_size > MAX_SHARE_BUNDLE_ZIP_BYTES:
        violations.append(
            f"Bundle zip size {zip_size / (1024 * 1024):.2f} MB exceeds "
            f"{MAX_SHARE_BUNDLE_ZIP_BYTES / (1024 * 1024):.2f} MB."
        )
    if violations:
        raise ValueError("\n\n".join(violations))


def iter_runtime_files(paths: Iterable[Path]) -> tuple[str, ...]:
    return tuple(sorted(path.as_posix() for path in paths))
