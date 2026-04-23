from __future__ import annotations

import native_services


def test_bootstrap_and_flattening_use_consistent_shapes(monkeypatch):
    monkeypatch.setattr(
        native_services,
        "_current_live_state",
        lambda: {
            "version": "live-abc123",
            "engine_count": 1,
            "tire_count": 1,
            "part_count": 2,
        },
    )
    monkeypatch.setattr(
        native_services,
        "get_parts_list",
        lambda: {
            "parts": {
                "Engine": [
                    {
                        "name": "DemoEngine",
                        "source": "mod",
                        "path": "mod/Engine/DemoEngine",
                        "uexp_size": 123,
                        "variant": "ice_standard",
                        "in_shop": True,
                    }
                ],
                "Tire": [
                    {
                        "name": "DemoTire",
                        "source": "vanilla",
                        "path": "vanilla/Tire/DemoTire",
                        "uexp_size": 45,
                        "variant": "",
                        "in_shop": False,
                    }
                ],
            },
            "state_version": "live-abc123",
            "engine_count": 1,
            "tire_count": 1,
            "part_count": 2,
        },
    )
    monkeypatch.setattr(
        native_services,
        "get_engine_templates",
        lambda: {
            "templates": {
                "ice_standard": {
                    "label": "ICE Standard",
                    "variant": "ice_standard",
                    "properties": ["MaxTorque", "MaxRPM"],
                    "engines": [
                        {
                            "name": "13b",
                            "title": "13B",
                            "description": "Baseline template",
                            "group_key": "ice_standard",
                            "group_label": "ICE Standard",
                            "variant": "ice_standard",
                            "properties": ["MaxTorque", "MaxRPM"],
                            "hp": 180.0,
                            "torque": 210.0,
                            "rpm": 7600.0,
                            "weight": 130.0,
                            "price": 4200,
                            "fuel": "Gas",
                        }
                    ],
                }
            }
        },
    )
    monkeypatch.setattr(native_services, "get_tire_templates", lambda: {"templates": {}})
    monkeypatch.setattr(
        native_services,
        "list_sounds",
        lambda: {
            "by_cue": {"v8": [{"dir": "Engine/V8", "source": "mod"}]},
            "bike": [{"dir": "Engine/Bike", "source": "vanilla"}],
            "electric": {"dir": "Engine/EV", "source": "mod"},
        },
    )
    monkeypatch.setattr(native_services, "get_engine_audio_manifest", lambda: {"engines": []})

    service = native_services.NativeEditorService()

    parts = service.list_parts()
    assert parts["count"] == 2
    assert parts["items"][0]["part_type"] == "engine"
    assert parts["items"][0]["title"] == "DemoEngine"
    assert parts["items"][1]["part_type"] == "tire"

    templates = service.get_engine_templates()
    assert templates["count"] == 1
    assert templates["groups"][0]["key"] == "ice_standard"
    assert templates["items"][0]["name"] == "13b"

    bootstrap = service.bootstrap()
    assert bootstrap["state"]["version"] == "live-abc123"
    assert bootstrap["parts"]["count"] == 2
    assert bootstrap["engine_audio"] == {"engines": []}
    assert isinstance(bootstrap["sound_options"], list)
    assert bootstrap["defaults"]["mod_pak_name"] == "ZZZ_FrogMod_P.pak"
    assert bootstrap["defaults"]["template_pak_name"] == "ZZZ_FrogTemplates_P.pak"
