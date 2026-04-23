"""Typed desktop command adapter shared by native hosts."""
from __future__ import annotations

from typing import Any, Dict

from native_services import NativeEditorService, build_property_value_map


SERVICE = NativeEditorService()


def _require_string(args: Dict[str, Any], key: str) -> str:
    value = str(args.get(key, "")).strip()
    if not value:
        raise ValueError(f"Missing required argument: {key}")
    return value


def _load_engine_from_name(name: str) -> Dict[str, Any]:
    return SERVICE.get_part_detail(f"mod/Engine/{name}")


def _load_template_from_name(name: str) -> Dict[str, Any]:
    return SERVICE.get_part_detail(f"template/Engine/{name}")


def _build_engine_draft(detail: Dict[str, Any]) -> Dict[str, Any]:
    metadata = detail.get("metadata") or {}
    shop = metadata.get("shop") or {}
    sound = metadata.get("sound") or {}
    return {
        "kind": "engine",
        "path": detail.get("path", ""),
        "name": detail.get("name", ""),
        "expected_version": detail.get("state_version", ""),
        "display_name": shop.get("display_name") or detail.get("name", ""),
        "description": shop.get("description") or "",
        "price": shop.get("price") or 0,
        "weight": shop.get("weight") or 0.0,
        "sound_dir": sound.get("dir") or "",
        "variant": metadata.get("variant") or "",
        "estimated_hp": metadata.get("estimated_hp"),
        "max_torque_nm": metadata.get("max_torque_nm"),
        "max_rpm": metadata.get("max_rpm"),
        "properties": build_property_value_map(detail),
    }


def _build_template_draft(detail: Dict[str, Any]) -> Dict[str, Any]:
    metadata = detail.get("metadata") or {}
    shop = metadata.get("shop") or {}
    sound = metadata.get("sound") or {}
    return {
        "kind": "template",
        "template": detail.get("name", ""),
        "name": "",
        "expected_version": SERVICE.get_live_state().get("version", ""),
        "display_name": shop.get("display_name") or detail.get("name", ""),
        "description": shop.get("description") or "",
        "price": shop.get("price") or 0,
        "weight": shop.get("weight") or 0.0,
        "sound_dir": sound.get("dir") or "",
        "variant": metadata.get("variant") or "",
        "estimated_hp": metadata.get("estimated_hp"),
        "max_torque_nm": metadata.get("max_torque_nm"),
        "max_rpm": metadata.get("max_rpm"),
        "properties": build_property_value_map(detail),
    }


def dispatch_command(cmd: str, args: Dict[str, Any] | None = None) -> Dict[str, Any]:
    args = args or {}

    if cmd == "ping":
        return SERVICE.get_live_state()

    if cmd == "app_bootstrap":
        return SERVICE.bootstrap()

    if cmd in {"list_engines", "get_parts_list"}:
        return SERVICE.list_parts()["raw"] if cmd == "get_parts_list" else SERVICE.list_parts()

    if cmd == "list_templates":
        return SERVICE.get_engine_templates()

    if cmd == "get_engine_template_catalog":
        return SERVICE.get_engine_templates()["raw"]

    if cmd == "get_tire_template_catalog":
        return SERVICE.get_tire_templates()["raw"]

    if cmd == "load_engine":
        path = str(args.get("path") or "").strip()
        if path:
            return SERVICE.get_part_detail(path)
        return _load_engine_from_name(_require_string(args, "name"))

    if cmd == "get_part_detail":
        return SERVICE.get_part_detail(_require_string(args, "path"))

    if cmd == "load_engine_draft":
        path = str(args.get("path") or "").strip()
        detail = SERVICE.get_part_detail(path) if path else _load_engine_from_name(_require_string(args, "name"))
        return {"detail": detail, "draft": _build_engine_draft(detail)}

    if cmd == "load_template":
        return _load_template_from_name(_require_string(args, "name"))

    if cmd == "load_template_draft":
        detail = _load_template_from_name(_require_string(args, "name"))
        return {"detail": detail, "draft": _build_template_draft(detail)}

    if cmd in {"save_engine", "save_part"}:
        path = str(args.get("path") or "").strip()
        if not path and cmd == "save_engine":
            path = f"mod/Engine/{_require_string(args, 'name')}"
        return SERVICE.save_part(path, dict(args.get("data") or {}))

    if cmd == "create_engine":
        return SERVICE.create_engine(dict(args))

    if cmd == "create_tire":
        return SERVICE.create_tire(dict(args))

    if cmd in {"delete_engine", "delete_tire"}:
        path = str(args.get("path") or "").strip()
        if not path and "name" in args:
            bucket = "Engine" if cmd == "delete_engine" else "Tire"
            path = f"mod/{bucket}/{args['name']}"
        return SERVICE.delete_part(path, str(args.get("expected_version") or ""))

    if cmd in {"list_sounds", "get_sounds_raw"}:
        return SERVICE.list_sounds()

    if cmd in {"get_engine_audio_manifest", "list_engine_audio_manifest"}:
        return SERVICE.get_engine_audio_manifest()

    if cmd == "prepare_engine_audio_workspace":
        return SERVICE.prepare_engine_audio_workspace()

    if cmd == "list_engine_audio_overrides":
        return SERVICE.get_engine_audio_manifest().get("overrides", {})

    if cmd == "toggle_engine_audio_override":
        payload = dict(args)
        return SERVICE.set_engine_audio_override(
            str(payload.get("engine_name") or payload.get("name") or ""),
            bool(payload.get("enabled", True)),
            str(payload.get("override_sound_dir") or ""),
        )

    if cmd == "recommend_price":
        return SERVICE.recommend_engine_price(args.get("torque_nm"), bool(args.get("include_bikes", False)))

    if cmd == "pack_mod":
        return SERVICE.pack_mod(str(args.get("output_path", "") or ""), list(args.get("parts") or []))

    if cmd == "pack_templates":
        return SERVICE.pack_templates(str(args.get("output_path", "") or ""))

    raise ValueError(f"Unknown desktop command: {cmd}")
