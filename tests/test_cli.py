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


def test_cli_adapt_and_merge_saved_evidence(tmp_path, capsys) -> None:
    baud_path = tmp_path / "baud.json"
    write_json(baud_path, {"ok": True, "ports": []})

    assert main(["adapt", "baud", str(baud_path)]) == 0
    adapted = json.loads(capsys.readouterr().out)
    assert adapted["observations"] == []

    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    write_json(first_path, adapted)
    write_json(second_path, adapted)
    assert main(["merge", str(first_path), str(second_path)]) == 0
    merged = json.loads(capsys.readouterr().out)
    assert merged == {
        "schema_version": "embedded-board-registry.observations.v1",
        "observations": [],
    }


def test_cli_select_emits_hash_bound_non_authorizing_contract(tmp_path, capsys) -> None:
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
                "identity": {
                    "probe_selector": "1366:1061:001050275757",
                    "vendor_id": "1366",
                    "product_id": "1061",
                },
                "source": {"path": "probe.json", "sha256": "b" * 64, "point_in_time": True},
            }
        ],
    }
    registry_path = tmp_path / "registry.json"
    observations_path = tmp_path / "observations.json"
    write_json(registry_path, registry)
    write_json(observations_path, observations)

    assert main(["select", str(registry_path), str(observations_path), "--require", "debug"]) == 0
    selection = json.loads(capsys.readouterr().out)
    assert selection["schema_version"] == "embedded-board-registry.selection.v1"
    assert selection["board_id"] == "dk"
    assert selection["bindings"][0]["observed_identity"]["vendor_id"] == "1366"
    assert selection["authorization"] == {"granted": False, "allowed_operations": []}
    assert selection["inputs"]["registry"]["sha256"]

    selection_path = tmp_path / "selection.json"
    write_json(selection_path, selection)
    assert main(["validate", "selection", str(selection_path), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_select_preserves_no_match_exit_code(tmp_path, capsys) -> None:
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
                        "identity": {"probe_selector": "expected"},
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
                "identity": {"probe_selector": "other"},
                "source": {"path": "probe.json", "sha256": "b" * 64, "point_in_time": True},
            }
        ],
    }
    registry_path = tmp_path / "registry.json"
    observations_path = tmp_path / "observations.json"
    write_json(registry_path, registry)
    write_json(observations_path, observations)
    assert main(["select", str(registry_path), str(observations_path)]) == 3
    assert json.loads(capsys.readouterr().out)["status"] == "no_match"


def test_cli_select_reports_invalid_input_as_json(tmp_path, capsys) -> None:
    registry_path = tmp_path / "registry.json"
    observations_path = tmp_path / "observations.json"
    registry_path.write_text("{}", encoding="utf-8")
    observations_path.write_text("{}", encoding="utf-8")
    assert main(["select", str(registry_path), str(observations_path)]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "invalid_input"
