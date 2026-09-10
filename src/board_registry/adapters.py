from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from .core import (
    OBSERVATIONS_SCHEMA,
    RegistryError,
    load_json,
    sha256,
    validate_observations,
)


def _object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RegistryError(f"{field} must be an object")
    return value


def _array(value: object, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise RegistryError(f"{field} must be an array")
    return value


def _exact_fields(value: dict[str, Any], allowed: set[str], field: str) -> None:
    missing = sorted(allowed - set(value))
    if missing:
        raise RegistryError(f"{field} is missing field(s): {missing}")
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise RegistryError(f"{field} has unsupported field(s): {unknown}")


def _required_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RegistryError(f"{field} must be a non-empty string")
    return value


def _optional_string(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _required_string(value, field)


def _usb_id(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 0xFFFF:
        raise RegistryError(f"{field} must be a 16-bit integer or null")
    return f"{value:04X}"


def _required_usb_id(value: object, field: str) -> str:
    result = _usb_id(value, field)
    if result is None:
        raise RegistryError(f"{field} must be a 16-bit integer")
    return result


def _optional_int(value: object, field: str, *, minimum: int | None = None) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise RegistryError(f"{field} must be an integer or null")
    if minimum is not None and value < minimum:
        raise RegistryError(f"{field} must be at least {minimum}")
    return value


def _source(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "sha256": sha256(path),
        "point_in_time": True,
    }


def _observation(
    identifier: str, transport: str, identity: dict[str, str], source: dict[str, Any]
) -> dict[str, Any]:
    return {
        "id": identifier,
        "transport": transport,
        "identity": identity,
        "source": source,
    }


def adapt_baud(data: object, source: dict[str, Any]) -> list[dict[str, Any]]:
    root = _object(data, "baud result")
    _exact_fields(root, {"ok", "ports"}, "baud result")
    if root.get("ok") is not True:
        raise RegistryError("baud result must have ok=true")
    ports = _array(root.get("ports"), "baud result.ports")
    source_key = source["sha256"][:12]
    observations: list[dict[str, Any]] = []
    allowed = {
        "device",
        "name",
        "description",
        "hardware_id",
        "vid",
        "pid",
        "serial_number",
        "manufacturer",
        "product",
        "interface",
        "location",
    }
    for index, item in enumerate(ports):
        field = f"baud result.ports[{index}]"
        port = _object(item, field)
        _exact_fields(port, allowed, field)
        for key in (
            "name",
            "description",
            "hardware_id",
            "manufacturer",
            "product",
            "interface",
            "location",
        ):
            _optional_string(port.get(key), f"{field}.{key}")
        identity: dict[str, str] = {"port": _required_string(port.get("device"), f"{field}.device")}
        for key, value in (
            ("usb_vid", _usb_id(port.get("vid"), f"{field}.vid")),
            ("usb_pid", _usb_id(port.get("pid"), f"{field}.pid")),
            (
                "usb_serial",
                _optional_string(port.get("serial_number"), f"{field}.serial_number"),
            ),
            (
                "pnp_interface",
                _optional_string(port.get("interface"), f"{field}.interface"),
            ),
        ):
            if value is not None:
                identity[key] = value
        observations.append(
            _observation(f"baud-{source_key}-{index + 1:04d}", "serial", identity, source)
        )
    return observations


def adapt_debugger(data: object, source: dict[str, Any]) -> list[dict[str, Any]]:
    root = _object(data, "embedded-debugger result")
    _exact_fields(
        root,
        {
            "schema_version",
            "ok",
            "operation",
            "operation_id",
            "data",
            "warnings",
            "artifacts",
        },
        "embedded-debugger result",
    )
    if root.get("schema_version") != "1.0":
        raise RegistryError("embedded-debugger schema_version must equal 1.0")
    if root.get("ok") is not True or root.get("operation") != "probes.list":
        raise RegistryError("embedded-debugger result must be a successful probes.list")
    _required_string(root.get("operation_id"), "embedded-debugger result.operation_id")
    _array(root.get("warnings"), "embedded-debugger result.warnings")
    _array(root.get("artifacts"), "embedded-debugger result.artifacts")
    payload = _object(root.get("data"), "embedded-debugger result.data")
    _exact_fields(payload, {"backend", "probes"}, "embedded-debugger result.data")
    _required_string(payload.get("backend"), "embedded-debugger result.data.backend")
    probes = _array(payload.get("probes"), "embedded-debugger result.data.probes")
    source_key = source["sha256"][:12]
    observations: list[dict[str, Any]] = []
    allowed = {
        "id",
        "vendor_id",
        "product_id",
        "serial",
        "product",
        "interface",
        "probe_type",
        "accessible",
    }
    for index, item in enumerate(probes):
        field = f"embedded-debugger result.data.probes[{index}]"
        probe = _object(item, field)
        _exact_fields(probe, allowed, field)
        _optional_string(probe.get("product"), f"{field}.product")
        _optional_int(probe.get("interface"), f"{field}.interface", minimum=0)
        _optional_string(probe.get("probe_type"), f"{field}.probe_type")
        if not isinstance(probe.get("accessible"), bool):
            raise RegistryError(f"{field}.accessible must be a boolean")
        identity = {
            "probe_selector": _required_string(probe.get("id"), f"{field}.id"),
            "vendor_id": _required_usb_id(probe.get("vendor_id"), f"{field}.vendor_id"),
            "product_id": _required_usb_id(probe.get("product_id"), f"{field}.product_id"),
        }
        serial = _optional_string(probe.get("serial"), f"{field}.serial")
        if serial is not None:
            identity["serial_number"] = serial
        observations.append(
            _observation(f"debugger-{source_key}-{index + 1:04d}", "debug", identity, source)
        )
    return observations


def adapt_blea(data: object, source: dict[str, Any]) -> list[dict[str, Any]]:
    root = _object(data, "BLEA result")
    _exact_fields(
        root,
        {"ok", "operation", "filters", "count", "devices", "duration_ms", "exit_code"},
        "BLEA result",
    )
    if root.get("ok") is not True or root.get("operation") != "scan":
        raise RegistryError("BLEA result must be a successful scan")
    _object(root.get("filters"), "BLEA result.filters")
    count = root.get("count")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise RegistryError("BLEA result.count must be a non-negative integer")
    if root.get("exit_code") != 0:
        raise RegistryError("BLEA result.exit_code must equal 0")
    _optional_int(root.get("duration_ms"), "BLEA result.duration_ms", minimum=0)
    devices = _array(root.get("devices"), "BLEA result.devices")
    if count != len(devices):
        raise RegistryError("BLEA result.count must equal the devices array length")
    source_key = source["sha256"][:12]
    observations: list[dict[str, Any]] = []
    allowed = {
        "identifier",
        "name",
        "local_name",
        "rssi",
        "tx_power",
        "service_uuids",
        "manufacturer_data",
        "service_data",
    }
    for index, item in enumerate(devices):
        field = f"BLEA result.devices[{index}]"
        device = _object(item, field)
        _exact_fields(device, allowed, field)
        _optional_int(device.get("rssi"), f"{field}.rssi")
        _optional_int(device.get("tx_power"), f"{field}.tx_power")
        identity = {"identifier": _required_string(device.get("identifier"), f"{field}.identifier")}
        local_name = _optional_string(device.get("local_name"), f"{field}.local_name")
        name = _optional_string(device.get("name"), f"{field}.name")
        if local_name is not None or name is not None:
            identity["local_name"] = local_name or name or ""
        service_uuids = _array(device.get("service_uuids"), f"{field}.service_uuids")
        for uuid_index, uuid in enumerate(service_uuids):
            _required_string(uuid, f"{field}.service_uuids[{uuid_index}]")
        _object(device.get("manufacturer_data"), f"{field}.manufacturer_data")
        _object(device.get("service_data"), f"{field}.service_data")
        observations.append(
            _observation(f"blea-{source_key}-{index + 1:04d}", "ble", identity, source)
        )
    return observations


ADAPTERS: dict[str, Callable[[object, dict[str, Any]], list[dict[str, Any]]]] = {
    "baud": adapt_baud,
    "embedded-debugger": adapt_debugger,
    "blea": adapt_blea,
}


def adapt(name: str, path: Path) -> dict[str, Any]:
    try:
        adapter = ADAPTERS[name]
    except KeyError as error:
        raise RegistryError(f"unsupported adapter: {name}") from error
    source = _source(path)
    observations = adapter(load_json(path), source)
    result = {"schema_version": OBSERVATIONS_SCHEMA, "observations": observations}
    validation = validate_observations(result)
    if not validation["ok"]:
        raise RegistryError("adapted observations are invalid: " + "; ".join(validation["errors"]))
    return result
