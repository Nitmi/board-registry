from __future__ import annotations

import json

from board_registry.cli import main


def write_json(path, value) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_cli_resolve_exit_codes(tmp_path, capsys) -> None:
    registry = {
        "schema_version": "embedded-board-registry.registry.v1",
        "boards": [
            {
                "id": "dk",
                "label": "DK",
                "selectors": [
                    {
                        "id": "jlink",
                        "transport": "debug",
                        "identity": {"probe_selector": "1366:1061:001050275757"},
                    }
                ],
            }
        ],
    }
    observations = {
        "schema_version": "embedded-board-registry.observations.v1",
        "observations": [
            {
                "id": "probe",
                "transport": "debug",
                "identity": {"probe_selector": "1366:1061:001050275757"},
                "source": {"path": "probe.json", "sha256": "b" * 64, "point_in_time": True},
            }
        ],
    }
    registry_path = tmp_path / "registry.json"
    observations_path = tmp_path / "observations.json"
    write_json(registry_path, registry)
    write_json(observations_path, observations)
    assert main(["resolve", str(registry_path), str(observations_path), "--json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["selected_board_id"] == "dk"
    assert output["registry"]["sha256"]

    observations["observations"][0]["identity"]["probe_selector"] = "other"
    write_json(observations_path, observations)
    assert main(["resolve", str(registry_path), str(observations_path), "--json"]) == 3
    assert json.loads(capsys.readouterr().out)["status"] == "no_match"


def test_duplicate_json_field_returns_invalid_input(tmp_path, capsys) -> None:
    path = tmp_path / "registry.json"
    path.write_text('{"schema_version":"x","schema_version":"y"}', encoding="utf-8")
    assert main(["validate", "registry", str(path), "--json"]) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "invalid_input"
