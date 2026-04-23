from __future__ import annotations

from pathlib import Path

from export_runtime_manifest import (
    SHARE_REQUIRED_FILES,
    SHARE_REQUIRED_PREFIX_CONTENT,
    is_allowed_share_bundle_path,
    is_forbidden_share_bundle_path,
    validate_share_bundle_tree,
)


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"test")


def _build_minimal_share_tree(root: Path) -> None:
    for rel_path in SHARE_REQUIRED_FILES:
        _touch(root / rel_path)
    for prefix in SHARE_REQUIRED_PREFIX_CONTENT:
        _touch(root / Path(prefix) / "placeholder.uexp")


def test_share_bundle_required_files_fit_allowlist():
    for rel_path in SHARE_REQUIRED_FILES:
        rel_text = rel_path.as_posix()
        assert is_allowed_share_bundle_path(rel_text), rel_text
        assert not is_forbidden_share_bundle_path(rel_text), rel_text


def test_share_bundle_rejects_known_bloat_paths():
    blocked = (
        "MotorTown718T7/MotorTown/Content/Cars/Models/Dumbi/Body.uexp",
        "Frogtuning718T7/MotorTown/Content/Cars/Parts/Engine/Sound/lamboV12/high.ubulk",
        "python/Lib/site-packages/numpy/__init__.py",
        "python/Lib/site-packages/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe",
        "python/Lib/site-packages/PySide6/Qt6WebEngineCore.dll",
    )
    for rel_path in blocked:
        assert not is_allowed_share_bundle_path(rel_path), rel_path
        assert is_forbidden_share_bundle_path(rel_path), rel_path


def test_share_bundle_tree_validation_accepts_minimal_runtime_shape(tmp_path: Path):
    _build_minimal_share_tree(tmp_path)
    validate_share_bundle_tree(tmp_path)


def test_share_bundle_tree_validation_rejects_bloat(tmp_path: Path):
    _build_minimal_share_tree(tmp_path)
    _touch(tmp_path / "MotorTown718T7/MotorTown/Content/Cars/Models/Dumbi/Body.uexp")
    try:
        validate_share_bundle_tree(tmp_path)
    except ValueError as exc:
        assert "MotorTown718T7/MotorTown/Content/Cars/Models" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected forbidden bundle content to be rejected.")
