from __future__ import annotations

import copy

import pytest

from board_registry.core import RegistryError, resolve, validate_observations, validate_registry


@pytest.fixture
def registry() -> dict:
    return {
        "schema_version": "embedded-board-registry.registry.v1",
        "boards": [
            {
                "id": "esp32s3-lab",
                "label": "ESP32-S3 lab board",
                "selectors": [
                    {
                        "id": "usb-serial",
                        "transport": "serial",
                        "identity": {
                            "usb_vid": "303A",
                            "usb_pid": "1001",
                            "usb_serial": "E0:72:A1:D4:1F:DC",
                        },
                    },
                    {
                        "id": "usb-jtag",
                        "transport": "debug",
                        "identity": {
                            "probe_selector": "303a:1001:E0:72:A1:D4:1F:DC",
                            "target": "esp32s3",
                        },
                    },
                ],
            },
            {
                "id": "nrf52840-dk",
                "label": "nRF52840 DK",
                "selectors": [
                    {
                        "id": "jlink",
                        "transport": "debug",
                        "identity": {
                            "probe_selector": "1366:1061:001050275757",
                            "target": "nRF52840_xxAA",
                        },
                    }
                ],
            },
        ],
    }


@pytest.fixture
def observations() -> dict:
    digest = "a" * 64
    return {
        "schema_version": "embedded-board-registry.observations.v1",
        "observations": [
            {
                "id": "serial-1",
                "transport": "serial",
                "identity": {
                    "port": "COM3",
                    "usb_vid": "303A",
                    "usb_pid": "1001",
                    "usb_serial": "E0:72:A1:D4:1F:DC",
                },
                "source": {"path": "baud-list.json", "sha256": digest, "point_in_time": True},
            },
            {
                "id": "probe-1",
                "transport": "debug",
                "identity": {
                    "probe_selector": "303a:1001:E0:72:A1:D4:1F:DC",
                    "target": "esp32s3",
                },
                "source": {"path": "probes.json", "sha256": digest, "point_in_time": True},
            },
        ],
    }


def test_resolves_one_board_across_required_transports(registry: dict, observations: dict) -> None:
    report = resolve(registry, observations, {"serial", "debug"})
    assert report["ok"] is True
    assert report["status"] == "resolved"
    assert report["selected_board_id"] == "esp32s3-lab"
    assert report["hardware_access"] is False


def test_missing_required_transport_does_not_partially_match(
    registry: dict, observations: dict
) -> None:
    observations["observations"] = observations["observations"][:1]
    report = resolve(registry, observations, {"serial", "debug"})
    assert report["status"] == "no_match"
    assert report["selected_board_id"] is None


def test_multiple_matching_observations_fail_closed(registry: dict, observations: dict) -> None:
    duplicate = copy.deepcopy(observations["observations"][0])
    duplicate["id"] = "serial-2"
    duplicate["identity"]["port"] = "COM4"
    observations["observations"].append(duplicate)
    report = resolve(registry, observations, {"serial", "debug"})
    assert report["status"] == "no_match"
    esp = next(item for item in report["evaluations"] if item["board_id"] == "esp32s3-lab")
    assert esp["match_count_conflicts"] == {"serial": 2}


def test_cross_board_ambiguity_is_reported(registry: dict, observations: dict) -> None:
    other = copy.deepcopy(registry["boards"][0])
    other["id"] = "esp32s3-other"
    other["label"] = "Other board"
    for selector in other["selectors"]:
        selector["identity"] = (
            {**selector["identity"], "port": "COM3"}
            if selector["transport"] == "serial"
            else {**selector["identity"], "vendor_id": "303a"}
        )
        if selector["transport"] == "debug":
            observations["observations"][1]["identity"]["vendor_id"] = "303a"
    registry["boards"].append(other)
    report = resolve(registry, observations, {"serial", "debug"})
    assert report["status"] == "ambiguous"
    assert report["candidate_board_ids"] == ["esp32s3-lab", "esp32s3-other"]


def test_duplicate_exact_selector_is_invalid(registry: dict) -> None:
    registry["boards"][1]["selectors"] = [copy.deepcopy(registry["boards"][0]["selectors"][0])]
    report = validate_registry(registry)
    assert report["ok"] is False
    assert any("duplicate exact selector" in error for error in report["errors"])


def test_observation_requires_source_hash(observations: dict) -> None:
    observations["observations"][0]["source"]["sha256"] = "BAD"
    report = validate_observations(observations)
    assert report["ok"] is False
    assert any("lowercase SHA-256" in error for error in report["errors"])


def test_invalid_data_is_rejected_before_resolution(registry: dict, observations: dict) -> None:
    registry["boards"][0]["selectors"][0]["identity"]["unknown"] = "value"
    with pytest.raises(RegistryError, match="not valid"):
        resolve(registry, observations, {"serial"})


@pytest.mark.parametrize(
    ("target", "field"),
    [
        (("registry",), "unexpected"),
        (("board",), "unexpected"),
        (("selector",), "unexpected"),
    ],
)
def test_registry_rejects_unknown_structure_fields(
    registry: dict, target: tuple[str], field: str
) -> None:
    if target == ("registry",):
        registry[field] = True
    elif target == ("board",):
        registry["boards"][0][field] = True
    else:
        registry["boards"][0]["selectors"][0][field] = True
    report = validate_registry(registry)
    assert report["ok"] is False
    assert any("is not allowed" in error for error in report["errors"])


def test_observations_reject_unknown_source_field(observations: dict) -> None:
    observations["observations"][0]["source"]["captured_at"] = "now"
    report = validate_observations(observations)
    assert report["ok"] is False
    assert any("captured_at is not allowed" in error for error in report["errors"])
