from __future__ import annotations

import json

import pytest

from board_registry.adapters import adapt
from board_registry.core import RegistryError, merge_observations, resolve, validate_observations


def write_json(path, value) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def baud_result() -> dict:
    return {
        "ok": True,
        "ports": [
            {
                "device": "COM3",
                "name": "COM3",
                "description": "USB Serial Device",
                "hardware_id": "USB VID:PID=303A:1001",
                "vid": 0x303A,
                "pid": 0x1001,
                "serial_number": "E0:72:A1:D4:1F:DC",
                "manufacturer": "Espressif",
                "product": "USB JTAG/serial debug unit",
                "interface": "MI_00",
                "location": "1-1",
            }
        ],
    }


def debugger_result() -> dict:
    return {
        "schema_version": "1.0",
        "ok": True,
        "operation": "probes.list",
        "operation_id": "op-1",
        "data": {
            "backend": "probe-rs",
            "probes": [
                {
                    "id": "303a:1001:E0:72:A1:D4:1F:DC",
                    "vendor_id": 0x303A,
                    "product_id": 0x1001,
                    "serial": "E0:72:A1:D4:1F:DC",
                    "product": "EspJtag",
                    "interface": 0,
                    "probe_type": "EspJtag",
                    "accessible": True,
                }
            ],
        },
        "warnings": [],
        "artifacts": [],
    }


def blea_result(devices: list[dict] | None = None) -> dict:
    if devices is None:
        devices = [
            {
                "identifier": "AA:BB:CC:DD:EE:FF",
                "name": "Sensor",
                "local_name": "Sensor-v1",
                "rssi": -52,
                "tx_power": None,
                "service_uuids": ["180f"],
                "manufacturer_data": {},
                "service_data": {},
            }
        ]
    return {
        "ok": True,
        "operation": "scan",
        "filters": {},
        "count": len(devices),
        "devices": devices,
        "duration_ms": 1000,
        "exit_code": 0,
    }


def test_baud_adapter_maps_stable_usb_identity_and_binds_source(tmp_path) -> None:
    path = tmp_path / "baud.json"
    write_json(path, baud_result())
    report = adapt("baud", path)
    observation = report["observations"][0]

    assert observation["id"].startswith("baud-")
    assert observation["identity"] == {
        "port": "COM3",
        "usb_vid": "303A",
        "usb_pid": "1001",
        "usb_serial": "E0:72:A1:D4:1F:DC",
        "pnp_interface": "MI_00",
    }
    assert observation["source"]["path"] == str(path.resolve())
    assert len(observation["source"]["sha256"]) == 64
    assert observation["source"]["point_in_time"] is True


def test_debugger_adapter_does_not_invent_target_identity(tmp_path) -> None:
    path = tmp_path / "probes.json"
    write_json(path, debugger_result())
    identity = adapt("embedded-debugger", path)["observations"][0]["identity"]

    assert identity == {
        "probe_selector": "303a:1001:E0:72:A1:D4:1F:DC",
        "vendor_id": "303A",
        "product_id": "1001",
        "serial_number": "E0:72:A1:D4:1F:DC",
    }
    assert "target" not in identity


def test_blea_adapter_uses_cross_platform_identifier(tmp_path) -> None:
    path = tmp_path / "scan.json"
    write_json(path, blea_result())
    identity = adapt("blea", path)["observations"][0]["identity"]

    assert identity == {
        "identifier": "AA:BB:CC:DD:EE:FF",
        "local_name": "Sensor-v1",
    }


def test_empty_ble_scan_is_a_valid_observation_document(tmp_path) -> None:
    path = tmp_path / "empty-scan.json"
    write_json(path, blea_result([]))
    report = adapt("blea", path)

    assert report["observations"] == []
    assert validate_observations(report)["ok"] is True


@pytest.mark.parametrize("field", ["unexpected", "future_contract_field"])
def test_adapter_rejects_unknown_native_fields(tmp_path, field: str) -> None:
    result = baud_result()
    result[field] = True
    path = tmp_path / "bad.json"
    write_json(path, result)

    with pytest.raises(RegistryError, match="unsupported field"):
        adapt("baud", path)


def test_merge_then_resolve_cross_transport_identity(tmp_path) -> None:
    baud_path = tmp_path / "baud.json"
    debugger_path = tmp_path / "probes.json"
    write_json(baud_path, baud_result())
    write_json(debugger_path, debugger_result())
    observations = merge_observations(
        [adapt("baud", baud_path), adapt("embedded-debugger", debugger_path)]
    )
    registry = {
        "schema_version": "embedded-board-registry.registry.v1",
        "boards": [
            {
                "id": "esp32s3-lab",
                "label": "ESP32-S3 lab board",
                "selectors": [
                    {
                        "id": "serial",
                        "transport": "serial",
                        "identity": {
                            "usb_vid": "303A",
                            "usb_pid": "1001",
                            "usb_serial": "E0:72:A1:D4:1F:DC",
                        },
                    },
                    {
                        "id": "debug",
                        "transport": "debug",
                        "identity": {"probe_selector": "303a:1001:E0:72:A1:D4:1F:DC"},
                    },
                ],
            }
        ],
    }

    report = resolve(registry, observations, {"serial", "debug"})
    assert report["status"] == "resolved"
    assert report["selected_board_id"] == "esp32s3-lab"


def test_merge_rejects_duplicate_source_observations(tmp_path) -> None:
    path = tmp_path / "baud.json"
    write_json(path, baud_result())
    document = adapt("baud", path)

    with pytest.raises(RegistryError, match="duplicate observation id"):
        merge_observations([document, document])
