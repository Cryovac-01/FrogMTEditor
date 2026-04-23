"""Typed view models shared by desktop-facing UI surfaces."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional


def _to_str(value: Any) -> str:
    return str(value or "").strip()


@dataclass(frozen=True)
class AssetSummary:
    name: str
    path: str
    part_type: str
    source: str = ""
    title: str = ""
    variant: str = ""
    group_label: str = ""
    can_delete: bool = False

    @classmethod
    def from_row(cls, row: Dict[str, Any], part_type: str) -> "AssetSummary":
        return cls(
            name=_to_str(row.get("name")),
            path=_to_str(row.get("path")),
            part_type=_to_str(part_type).lower(),
            source=_to_str(row.get("source")),
            title=_to_str(row.get("title") or row.get("name")),
            variant=_to_str(row.get("variant")),
            group_label=_to_str(row.get("group_label") or row.get("family")),
            can_delete=bool(row.get("can_delete")),
        )

    @property
    def display_name(self) -> str:
        return self.title or self.name or "Asset"

    @property
    def is_engine(self) -> bool:
        return self.part_type == "engine"

    @property
    def is_tire(self) -> bool:
        return self.part_type == "tire"


@dataclass(frozen=True)
class WorkspaceSummary:
    state_version: str
    engine_count: int
    tire_count: int
    part_count: int
    groups: Dict[str, List[AssetSummary]] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Dict[str, Any], state_version: str = "") -> "WorkspaceSummary":
        raw_groups = payload.get("parts", {}) if isinstance(payload.get("parts"), dict) else payload.get("groups", {})
        groups: Dict[str, List[AssetSummary]] = {}
        for group_name, rows in (raw_groups or {}).items():
            groups[group_name] = [
                AssetSummary.from_row(row, group_name)
                for row in list(rows or [])
                if isinstance(row, dict)
            ]
        engine_count = len(groups.get("Engine", []))
        tire_count = len(groups.get("Tire", []))
        part_count = int(payload.get("part_count") or (engine_count + tire_count))
        version = _to_str(state_version or payload.get("state_version"))
        return cls(
            state_version=version,
            engine_count=engine_count,
            tire_count=tire_count,
            part_count=part_count,
            groups=groups,
        )

    @property
    def all_items(self) -> List[AssetSummary]:
        items: List[AssetSummary] = []
        for bucket in self.groups.values():
            items.extend(bucket)
        return items


@dataclass(frozen=True)
class AssetDocument:
    name: str
    path: str
    part_type: str
    source: str
    state_version: str
    display_name: str
    description: str
    variant: str
    group_label: str
    sound_dir: str
    can_delete: bool
    metadata: Dict[str, Any] = field(default_factory=dict)
    properties: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_detail(cls, detail: Dict[str, Any]) -> "AssetDocument":
        metadata = dict(detail.get("metadata") or {})
        shop = dict(metadata.get("shop") or {})
        sound = dict(metadata.get("sound") or {})
        return cls(
            name=_to_str(detail.get("name")),
            path=_to_str(detail.get("path")),
            part_type=_to_str(detail.get("type")).lower(),
            source=_to_str(detail.get("source")),
            state_version=_to_str(detail.get("state_version")),
            display_name=_to_str(shop.get("display_name") or detail.get("name")),
            description=_to_str(shop.get("description")),
            variant=_to_str(metadata.get("variant")),
            group_label=_to_str(metadata.get("group_label") or metadata.get("family")),
            sound_dir=_to_str(sound.get("dir")),
            can_delete=bool(detail.get("can_delete")),
            metadata=metadata,
            properties=dict(detail.get("properties") or {}),
            raw=dict(detail),
        )

    @property
    def is_engine(self) -> bool:
        return self.part_type == "engine"

    @property
    def is_tire(self) -> bool:
        return self.part_type == "tire"


@dataclass(frozen=True)
class CatalogEntry:
    key: str
    label: str
    path: str = ""
    source: str = ""
    part_type: str = ""
    variant: str = ""
    group_label: str = ""


@dataclass(frozen=True)
class TemplateCatalog:
    part_type: str
    groups: List[CatalogEntry] = field(default_factory=list)
    items: List[CatalogEntry] = field(default_factory=list)

    @classmethod
    def from_payload(cls, payload: Dict[str, Any], part_type: str) -> "TemplateCatalog":
        groups = [
            CatalogEntry(
                key=_to_str(row.get("key") or row.get("name")),
                label=_to_str(row.get("label") or row.get("title") or row.get("name")),
                part_type=part_type,
                variant=_to_str(row.get("variant")),
                group_label=_to_str(row.get("label") or row.get("group_label")),
            )
            for row in list(payload.get("groups") or [])
            if isinstance(row, dict)
        ]
        items = [
            CatalogEntry(
                key=_to_str(row.get("name") or row.get("path")),
                label=_to_str(row.get("title") or row.get("name") or row.get("path")),
                path=_to_str(row.get("path")),
                source=_to_str(row.get("source")),
                part_type=part_type,
                variant=_to_str(row.get("variant")),
                group_label=_to_str(row.get("group_label")),
            )
            for row in list(payload.get("items") or [])
            if isinstance(row, dict)
        ]
        return cls(part_type=part_type, groups=groups, items=items)


@dataclass(frozen=True)
class PackPreview:
    kind: str
    output_path: str
    selection_label: str
    item_count: int
    state_version: str = ""


@dataclass(frozen=True)
class ConflictState:
    detected: bool
    message: str
    state_version: str = ""

    @classmethod
    def from_result(cls, result: Optional[Dict[str, Any]], default_message: str) -> "ConflictState":
        payload = result or {}
        return cls(
            detected=bool(payload.get("conflict")),
            message=_to_str(payload.get("error") or default_message),
            state_version=_to_str(payload.get("state_version")),
        )


def flatten_metadata_rows(mapping: Dict[str, Any], prefix: str = "") -> List[tuple[str, str]]:
    rows: List[tuple[str, str]] = []
    for key in sorted(mapping.keys()):
        value = mapping.get(key)
        full_key = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            rows.extend(flatten_metadata_rows(value, full_key))
            continue
        if isinstance(value, list):
            rendered = ", ".join(_to_str(item) for item in value) if value else "[]"
            rows.append((full_key, rendered))
            continue
        rows.append((full_key, _to_str(value)))
    return rows


def recent_activity(events: Iterable[str], limit: int = 5) -> List[str]:
    return [str(row) for row in list(events)[: max(0, limit)]]
