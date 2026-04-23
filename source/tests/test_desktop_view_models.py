from __future__ import annotations

from desktop_view_models import AssetDocument, ConflictState, WorkspaceSummary, flatten_metadata_rows


def test_workspace_summary_and_asset_document_are_built_from_payloads():
    summary = WorkspaceSummary.from_payload(
        {
            "parts": {
                "Engine": [
                    {"name": "DemoEngine", "path": "mod/Engine/DemoEngine", "source": "mod", "variant": "ice_standard"}
                ],
                "Tire": [
                    {"name": "DemoTire", "path": "mod/Tire/DemoTire", "source": "mod", "group_label": "Street"}
                ],
            }
        },
        state_version="v1",
    )

    assert summary.engine_count == 1
    assert summary.tire_count == 1
    assert summary.part_count == 2
    assert summary.groups["Engine"][0].display_name == "DemoEngine"

    document = AssetDocument.from_detail(
        {
            "name": "DemoEngine",
            "path": "mod/Engine/DemoEngine",
            "type": "engine",
            "source": "mod",
            "state_version": "v1",
            "metadata": {
                "variant": "ice_standard",
                "shop": {"display_name": "Demo Engine", "description": "Bench asset"},
                "sound": {"dir": "Engine/V8"},
            },
            "properties": {"MaxTorque": {"display": "400"}},
        }
    )

    assert document.display_name == "Demo Engine"
    assert document.description == "Bench asset"
    assert document.sound_dir == "Engine/V8"
    assert document.is_engine


def test_conflict_state_and_metadata_flattening():
    conflict = ConflictState.from_result({"conflict": True, "error": "Workspace changed", "state_version": "abc"}, "fallback")
    assert conflict.detected is True
    assert conflict.message == "Workspace changed"
    assert conflict.state_version == "abc"

    rows = flatten_metadata_rows({"shop": {"display_name": "Demo", "price": 5000}, "flags": ["generated", "bench"]})
    assert ("shop.display_name", "Demo") in rows
    assert ("shop.price", "5000") in rows
    assert ("flags", "generated, bench") in rows
