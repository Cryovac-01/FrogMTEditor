from __future__ import annotations

from pathlib import Path

import pytest

from api import routes
from parsers.pak_reader import extract_file, read_pak
from parsers.uexp_engines_dt import FOOTER, _find_type_a_rows
from template_engines import load_template_specs, sort_key


EXPECTED_TEMPLATE_COUNT = 219
EXPECTED_PAK_FILE_COUNT = 440


@pytest.fixture(scope="module")
def template_pack(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict]:
    output_path = tmp_path_factory.mktemp("template_pack") / "Frog_Mod_Editor_Templates_P.pak"
    result = routes.pack_templates(str(output_path))
    assert result.get("success"), result
    return output_path, result


def test_pack_templates_exports_and_registers_every_template(template_pack: tuple[Path, dict]):
    output_path, result = template_pack

    assert result["template_count"] == EXPECTED_TEMPLATE_COUNT
    assert result["expected_template_count"] == EXPECTED_TEMPLATE_COUNT
    assert result["materialized_template_count"] == EXPECTED_TEMPLATE_COUNT
    assert result["pak_engine_count"] == EXPECTED_TEMPLATE_COUNT
    assert result["registered_template_count"] == EXPECTED_TEMPLATE_COUNT
    assert result["preloaded_template_count"] == EXPECTED_TEMPLATE_COUNT
    assert result["pak_file_count"] == EXPECTED_PAK_FILE_COUNT
    assert result["file_count"] == EXPECTED_PAK_FILE_COUNT
    assert result["missing_templates"] == []
    assert result["shop_tail_policy"] == "universal_ice_standard"
    assert "219 engines, 219 registered templates, 219 preloaded templates" in result["message"]

    diagnostics = routes.inspect_template_pack(str(output_path))
    assert diagnostics["valid"], diagnostics
    assert diagnostics["expected_template_count"] == EXPECTED_TEMPLATE_COUNT
    assert diagnostics["pak_engine_count"] == EXPECTED_TEMPLATE_COUNT
    assert diagnostics["registered_template_count"] == EXPECTED_TEMPLATE_COUNT
    assert diagnostics["preloaded_template_count"] == EXPECTED_TEMPLATE_COUNT
    assert diagnostics["datatable_row_count"] >= EXPECTED_TEMPLATE_COUNT
    for asset_name in ("VW19TDI150HP", "wartsila46f20000", "EVRimacNeveraR"):
        assert asset_name in diagnostics["pak_engine_assets"]

    datatable_uasset = extract_file(str(output_path), "MotorTown/Content/DataAsset/VehicleParts/Engines.uasset")
    datatable_uexp = extract_file(str(output_path), "MotorTown/Content/DataAsset/VehicleParts/Engines.uexp")
    idx_to_name, _name_to_idx = routes._parse_name_lookup(datatable_uasset)
    rows = _find_type_a_rows(datatable_uexp)
    tail_lengths = {}
    for index, row in enumerate(rows):
        name = idx_to_name.get(row["fname_idx"])
        if name not in {"L86", "VW19TDI150HP", "scaniadc13500", "EVRimacNeveraR"}:
            continue
        row_end = rows[index + 1]["row_start"] if index + 1 < len(rows) else len(datatable_uexp) - len(FOOTER)
        tail_lengths[name] = row_end - row["tail_start"]
    assert tail_lengths == {
        "L86": 368,
        "VW19TDI150HP": 368,
        "scaniadc13500": 368,
        "EVRimacNeveraR": 368,
    }


def test_template_pack_verification_rejects_missing_expected_pak_entry(template_pack: tuple[Path, dict]):
    output_path, _result = template_pack
    pak = read_pak(str(output_path))
    pak["entries"] = [
        entry
        for entry in pak["entries"]
        if entry["path"] != "MotorTown/Content/Cars/Parts/Engine/EVRimacNeveraR.uexp"
    ]
    pak["file_count"] = len(pak["entries"])

    specs = sorted(load_template_specs(routes.TEMPLATES_ENGINE_DIR, routes.ENGINE_DISPLAY_NAMES), key=sort_key)
    diagnostics = routes._verify_template_pack_contents(pak, routes._expected_template_pack_specs(specs))

    assert not diagnostics["valid"]
    assert "EVRimacNeveraR" in diagnostics["missing_templates"]
    assert "EVRimacNeveraR" in diagnostics["missing_pak_templates"]
    assert diagnostics["last_registered_template"]
