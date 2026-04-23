"""Create a complete Frog Mod Editor source release zip with runtime included."""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import export_public_source_zip as split_export


BACKUPS_DIR = split_export.BACKUPS_DIR
COMPLETE_STAGING_DIR = BACKUPS_DIR / "frog_mod_editor_complete_source_release"
COMPLETE_ZIP_PATH = BACKUPS_DIR / "Frog_Mod_Editor_Complete_Source_Release.zip"


def _complete_required_paths() -> set[str]:
    return set(split_export.REQUIRED_PUBLIC_SOURCE_PATHS) | set(split_export.RUNTIME_REQUIRED_PATHS)


def _validate_complete_release_tree(root: Path = COMPLETE_STAGING_DIR) -> None:
    missing = [rel for rel in sorted(_complete_required_paths()) if not (root / rel).exists()]
    if missing:
        raise RuntimeError("Complete source release is missing required paths:\n" + "\n".join(missing))

    forbidden_paths = split_export._find_forbidden_release_paths(root)
    if forbidden_paths:
        raise RuntimeError(
            "Complete source release contains forbidden generated/binary artifacts:\n"
            + "\n".join(forbidden_paths[:50])
        )

    split_export._validate_staged_workspace_matches(root)


def _validate_complete_release_zip(zip_path: Path = COMPLETE_ZIP_PATH, root: Path = COMPLETE_STAGING_DIR) -> None:
    with zipfile.ZipFile(zip_path, "r") as archive:
        names = set(archive.namelist())
    missing = []
    for rel in sorted(_complete_required_paths()):
        if rel in names:
            continue
        prefix = rel.rstrip("/") + "/"
        if not any(name.startswith(prefix) for name in names):
            missing.append(rel)
    if missing:
        raise RuntimeError("Complete source release zip is missing required entries:\n" + "\n".join(missing))

    forbidden_entries = split_export._find_forbidden_release_zip_entries(names)
    if forbidden_entries:
        raise RuntimeError(
            "Complete source release zip contains forbidden generated/binary artifacts:\n"
            + "\n".join(forbidden_entries[:50])
        )

    split_export._validate_zip_workspace_matches(zip_path, root)


def export_complete_source_release_zip() -> Path:
    """Build split release artifacts, then merge cleaned source and trimmed runtime."""
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    split_export.export_public_source_zip()

    if COMPLETE_STAGING_DIR.exists():
        shutil.rmtree(COMPLETE_STAGING_DIR)
    shutil.copytree(split_export.STAGING_DIR, COMPLETE_STAGING_DIR)
    shutil.copytree(
        split_export.RUNTIME_SOURCE_DIR / "python",
        COMPLETE_STAGING_DIR / "source" / "python",
    )

    _validate_complete_release_tree(COMPLETE_STAGING_DIR)
    split_export._zip_tree(COMPLETE_STAGING_DIR, COMPLETE_ZIP_PATH)
    _validate_complete_release_zip(COMPLETE_ZIP_PATH, COMPLETE_STAGING_DIR)
    return COMPLETE_ZIP_PATH


def main() -> int:
    zip_path = export_complete_source_release_zip()
    print(f"Complete source release directory: {COMPLETE_STAGING_DIR}")
    print(f"Complete source release zip: {zip_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
