from __future__ import annotations

import desktop_api


class FakeService:
    def get_live_state(self):
        return {"version": "abc123", "engine_count": 1, "tire_count": 0, "part_count": 1}

    def bootstrap(self):
        return {
            "state": self.get_live_state(),
            "parts": {"count": 1},
            "sounds": {"by_cue": {}},
            "sound_options": [],
            "engine_audio": {"engines": []},
            "defaults": {"paks_dir": "C:/Game/Paks", "mod_pak_name": "mod.pak", "template_pak_name": "templates.pak"},
        }

    def list_parts(self):
        return {"raw": {"parts": {"Engine": []}}, "items": [], "count": 0}

    def get_engine_templates(self):
        return {
            "raw": {"templates": {"grp": {"engines": []}}},
            "groups": [{"key": "grp", "label": "Group", "variant": "", "properties": [], "count": 0}],
            "items": [
                {
                    "name": "Demo",
                    "title": "Demo",
                    "description": "",
                    "group_key": "grp",
                    "group_label": "Group",
                    "variant": "",
                    "properties": [],
                    "hp": 0.0,
                    "torque": 0.0,
                    "rpm": 0.0,
                    "weight": 0.0,
                    "price": 0,
                    "fuel": "Gas",
                }
            ],
            "count": 1,
        }

    def get_tire_templates(self):
        return {"raw": {"templates": {}}, "groups": [], "items": [], "count": 0}

    def get_part_detail(self, path):
        if path == "mod/Engine/DemoEngine":
            return {
                "path": path,
                "name": "DemoEngine",
                "state_version": "abc123",
                "metadata": {
                    "shop": {
                        "display_name": "Demo Deluxe",
                        "description": "Demo description",
                        "price": 4200,
                        "weight": 123.4,
                    },
                    "sound": {"dir": "Engine/Demo", "cue": "DemoCue", "valid": True},
                    "variant": "ice_standard",
                    "estimated_hp": 180.0,
                    "max_torque_nm": 210.0,
                    "max_rpm": 7600.0,
                },
                "properties": {
                    "MaxTorque": {"raw": 2100000, "display": "210.0", "unit": "Nm"},
                    "MaxRPM": {"raw": 7600, "display": "7600", "unit": "RPM"},
                },
                "asset_info": {"torque_curve_name": "DemoCurve"},
            }
        if path == "template/Engine/DemoTemplate":
            return {
                "path": path,
                "name": "DemoTemplate",
                "state_version": "abc123",
                "metadata": {
                    "shop": {"display_name": "Template Label", "description": "Template description", "price": 5000, "weight": 130.0},
                    "sound": {"dir": "Engine/Template", "cue": "TemplateCue", "valid": True},
                    "variant": "ice_standard",
                    "estimated_hp": 180.0,
                    "max_torque_nm": 210.0,
                    "max_rpm": 7600.0,
                },
                "properties": {
                    "MaxTorque": {"raw": 2100000, "display": "210.0", "unit": "Nm"},
                    "MaxRPM": {"raw": 7600, "display": "7600", "unit": "RPM"},
                },
            }
        return {"error": "not found"}

    def list_sounds(self):
        return {"by_cue": {}, "bike": [], "electric": []}

    def get_engine_audio_manifest(self):
        return {"engines": []}

    def prepare_engine_audio_workspace(self):
        return {"prepared": True}

    def recommend_engine_price(self, torque_nm, include_bikes=False):
        return {"price": 1234, "torque_nm": torque_nm, "include_bikes": include_bikes}

    def save_part(self, path, data):
        return {"path": path, "data": data}

    def create_engine(self, data):
        return {"created": data}

    def create_tire(self, data):
        return {"created": data}

    def delete_part(self, path, expected_version=""):
        return {"deleted": path, "expected_version": expected_version}

    def pack_mod(self, output_path, parts=None):
        return {"output_path": output_path, "parts": list(parts or [])}

    def pack_templates(self, output_path):
        return {"output_path": output_path}


def test_dispatch_command_preserves_typed_draft_shapes(monkeypatch):
    monkeypatch.setattr(desktop_api, "SERVICE", FakeService())

    assert desktop_api.dispatch_command("ping") == {"version": "abc123", "engine_count": 1, "tire_count": 0, "part_count": 1}

    bootstrap = desktop_api.dispatch_command("app_bootstrap")
    assert bootstrap["defaults"]["template_pak_name"] == "templates.pak"

    templates = desktop_api.dispatch_command("list_templates")
    assert templates["count"] == 1
    assert templates["items"][0]["name"] == "Demo"

    engine_draft = desktop_api.dispatch_command("load_engine_draft", {"name": "DemoEngine"})
    assert engine_draft["detail"]["name"] == "DemoEngine"
    assert engine_draft["draft"]["kind"] == "engine"
    assert engine_draft["draft"]["path"] == "mod/Engine/DemoEngine"
    assert engine_draft["draft"]["display_name"] == "Demo Deluxe"
    assert engine_draft["draft"]["properties"]["MaxTorque"] == "2100000"

    template_draft = desktop_api.dispatch_command("load_template_draft", {"name": "DemoTemplate"})
    assert template_draft["detail"]["name"] == "DemoTemplate"
    assert template_draft["draft"]["kind"] == "template"
    assert template_draft["draft"]["expected_version"] == "abc123"
    assert template_draft["draft"]["sound_dir"] == "Engine/Template"
