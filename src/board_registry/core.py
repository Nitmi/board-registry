from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

REGISTRY_SCHEMA = "embedded-board-registry.registry.v1"
OBSERVATIONS_SCHEMA = "embedded-board-registry.observations.v1"
RESULT_SCHEMA = "embedded-board-registry.resolve.v1"
SELECTION_SCHEMA = "embedded-board-registry.selection.v1"
TRANSPORTS = frozenset({"serial", "debug", "ble"})
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
IDENTITY_FIELDS = {
    "serial": frozenset({"port", "usb_vid", "usb_pid", "usb_serial", "pnp_interface"}),
    "debug": frozenset({"probe_selector", "vendor_id", "product_id", "serial_number", "target"}),
    "ble": frozenset({"identifier", "local_name", "service_uuid", "manufacturer_id"}),
}


class RegistryError(ValueError):
    pass


def _object_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RegistryError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_object_no_duplicates)
    except RegistryError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RegistryError(f"unable to load {path}: {error}") from error


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise RegistryError(f"unable to hash {path}: {error}") from error
    return digest.hexdigest()


def _string(value: object, field: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} must be a non-empty string")
        return None
    return value


def _identifier(value: object, field: str, errors: list[str]) -> str | None:
    result = _string(value, field, errors)
    if result is not None and ID_PATTERN.fullmatch(result) is None:
        errors.append(f"{field} must match {ID_PATTERN.pattern}")
    return result


def _reject_unknown(
    value: dict[str, Any], allowed: set[str], field: str, errors: list[str]
) -> None:
    for key in sorted(set(value) - allowed):
        errors.append(f"{field}.{key} is not allowed")


def _identity(
    value: object, transport: str | None, field: str, errors: list[str]
) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        errors.append(f"{field} must be a non-empty object")
        return {}
    if transport not in TRANSPORTS:
        return {}
    unknown = sorted(set(value) - IDENTITY_FIELDS[transport])
    for key in unknown:
        errors.append(f"{field}.{key} is not valid for transport {transport}")
    result: dict[str, str] = {}
    for key, item in value.items():
        checked = _string(item, f"{field}.{key}", errors)
        if checked is not None:
            result[key] = checked
    return result


def validate_registry(data: object) -> dict[str, Any]:
    errors: list[str] = []
    board_ids: list[str] = []
    selector_keys: list[tuple[str, tuple[tuple[str, str], ...]]] = []
    if not isinstance(data, dict):
        errors.append("registry root must be an object")
        data = {}
    _reject_unknown(data, {"schema_version", "boards"}, "registry", errors)
    if data.get("schema_version") != REGISTRY_SCHEMA:
        errors.append(f"schema_version must equal {REGISTRY_SCHEMA}")
    boards = data.get("boards")
    if not isinstance(boards, list) or not boards:
        errors.append("boards must be a non-empty array")
        boards = []
    selector_count = 0
    for board_index, board in enumerate(boards):
        prefix = f"boards[{board_index}]"
        if not isinstance(board, dict):
            errors.append(f"{prefix} must be an object")
            continue
        _reject_unknown(board, {"id", "label", "selectors"}, prefix, errors)
        board_id = _identifier(board.get("id"), f"{prefix}.id", errors)
        if board_id is not None:
            board_ids.append(board_id)
        _string(board.get("label"), f"{prefix}.label", errors)
        selectors = board.get("selectors")
        if not isinstance(selectors, list) or not selectors:
            errors.append(f"{prefix}.selectors must be a non-empty array")
            continue
        selector_ids: list[str] = []
        for selector_index, selector in enumerate(selectors):
            selector_count += 1
            selector_prefix = f"{prefix}.selectors[{selector_index}]"
            if not isinstance(selector, dict):
                errors.append(f"{selector_prefix} must be an object")
                continue
            _reject_unknown(selector, {"id", "transport", "identity"}, selector_prefix, errors)
            selector_id = _identifier(selector.get("id"), f"{selector_prefix}.id", errors)
            if selector_id is not None:
                selector_ids.append(selector_id)
            transport = _string(selector.get("transport"), f"{selector_prefix}.transport", errors)
            if transport is not None and transport not in TRANSPORTS:
                errors.append(f"{selector_prefix}.transport must be one of {sorted(TRANSPORTS)}")
            identity = _identity(
                selector.get("identity"),
                transport,
                f"{selector_prefix}.identity",
                errors,
            )
            if board_id is not None and transport in TRANSPORTS and identity:
                selector_keys.append((transport, tuple(sorted(identity.items()))))
        for selector_id, count in Counter(selector_ids).items():
            if count > 1:
                errors.append(f"{prefix} has duplicate selector id: {selector_id}")
    for board_id, count in Counter(board_ids).items():
        if count > 1:
            errors.append(f"duplicate board id: {board_id}")
    for selector_key, count in Counter(selector_keys).items():
        if count > 1:
            errors.append(
                "duplicate exact selector across registry: "
                f"{selector_key[0]} {dict(selector_key[1])}"
            )
    return {
        "ok": not errors,
        "schema_version": REGISTRY_SCHEMA,
        "board_count": len(boards),
        "selector_count": selector_count,
        "hardware_access": False,
        "executables_started": False,
        "errors": errors,
    }


def validate_observations(data: object) -> dict[str, Any]:
    errors: list[str] = []
    observation_ids: list[str] = []
    transports: list[str] = []
    if not isinstance(data, dict):
        errors.append("observations root must be an object")
        data = {}
    _reject_unknown(data, {"schema_version", "observations"}, "observations", errors)
    if data.get("schema_version") != OBSERVATIONS_SCHEMA:
        errors.append(f"schema_version must equal {OBSERVATIONS_SCHEMA}")
    observations = data.get("observations")
    if not isinstance(observations, list):
        errors.append("observations must be an array")
        observations = []
    for index, observation in enumerate(observations):
        prefix = f"observations[{index}]"
        if not isinstance(observation, dict):
            errors.append(f"{prefix} must be an object")
            continue
        _reject_unknown(observation, {"id", "transport", "identity", "source"}, prefix, errors)
        observation_id = _identifier(observation.get("id"), f"{prefix}.id", errors)
        if observation_id is not None:
            observation_ids.append(observation_id)
        transport = _string(observation.get("transport"), f"{prefix}.transport", errors)
        if transport is not None:
            transports.append(transport)
            if transport not in TRANSPORTS:
                errors.append(f"{prefix}.transport must be one of {sorted(TRANSPORTS)}")
        _identity(observation.get("identity"), transport, f"{prefix}.identity", errors)
        source = observation.get("source")
        if not isinstance(source, dict):
            errors.append(f"{prefix}.source must be an object")
            continue
        _reject_unknown(
            source,
            {"path", "sha256", "point_in_time"},
            f"{prefix}.source",
            errors,
        )
        _string(source.get("path"), f"{prefix}.source.path", errors)
        digest = _string(source.get("sha256"), f"{prefix}.source.sha256", errors)
        if digest is not None and SHA256_PATTERN.fullmatch(digest) is None:
            errors.append(f"{prefix}.source.sha256 must be lowercase SHA-256")
        if not isinstance(source.get("point_in_time"), bool):
            errors.append(f"{prefix}.source.point_in_time must be a boolean")
    for observation_id, count in Counter(observation_ids).items():
        if count > 1:
            errors.append(f"duplicate observation id: {observation_id}")
    return {
        "ok": not errors,
        "schema_version": OBSERVATIONS_SCHEMA,
        "observation_count": len(observations),
        "transports": sorted(set(transports) & TRANSPORTS),
        "hardware_access": False,
        "executables_started": False,
        "errors": errors,
    }


def _source_reference(value: object, field: str, errors: list[str]) -> dict[str, str]:
    if not isinstance(value, dict):
        errors.append(f"{field} must be an object")
        return {}
    _reject_unknown(value, {"path", "sha256"}, field, errors)
    path = _string(value.get("path"), f"{field}.path", errors)
    digest = _string(value.get("sha256"), f"{field}.sha256", errors)
    if digest is not None and SHA256_PATTERN.fullmatch(digest) is None:
        errors.append(f"{field}.sha256 must be lowercase SHA-256")
    return {key: item for key, item in (("path", path), ("sha256", digest)) if item is not None}


def validate_selection(data: object) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(data, dict):
        errors.append("selection root must be an object")
        data = {}
    _reject_unknown(
        data,
        {
            "schema_version",
            "ok",
            "status",
            "board_id",
            "required_transports",
            "bindings",
            "inputs",
            "authorization",
            "hardware_access",
            "executables_started",
        },
        "selection",
        errors,
    )
    if data.get("schema_version") != SELECTION_SCHEMA:
        errors.append(f"schema_version must equal {SELECTION_SCHEMA}")
    if data.get("ok") is not True:
        errors.append("selection.ok must equal true")
    if data.get("status") != "selected":
        errors.append("selection.status must equal selected")
    _identifier(data.get("board_id"), "selection.board_id", errors)

    required = data.get("required_transports")
    if not isinstance(required, list) or not required:
        errors.append("selection.required_transports must be a non-empty array")
        required = []
    elif any(not isinstance(item, str) or item not in TRANSPORTS for item in required):
        errors.append(f"selection.required_transports must contain only {sorted(TRANSPORTS)}")
    elif required != sorted(set(required)):
        errors.append("selection.required_transports must be sorted and unique")

    bindings = data.get("bindings")
    binding_transports: list[str] = []
    if not isinstance(bindings, list) or not bindings:
        errors.append("selection.bindings must be a non-empty array")
        bindings = []
    for index, binding in enumerate(bindings):
        prefix = f"selection.bindings[{index}]"
        if not isinstance(binding, dict):
            errors.append(f"{prefix} must be an object")
            continue
        _reject_unknown(
            binding,
            {
                "transport",
                "selector_id",
                "observation_id",
                "selector_identity",
                "observed_identity",
                "source",
            },
            prefix,
            errors,
        )
        transport = _string(binding.get("transport"), f"{prefix}.transport", errors)
        if transport is not None:
            binding_transports.append(transport)
            if transport not in TRANSPORTS:
                errors.append(f"{prefix}.transport must be one of {sorted(TRANSPORTS)}")
        _identifier(binding.get("selector_id"), f"{prefix}.selector_id", errors)
        _identifier(binding.get("observation_id"), f"{prefix}.observation_id", errors)
        selector_identity = _identity(
            binding.get("selector_identity"), transport, f"{prefix}.selector_identity", errors
        )
        observed_identity = _identity(
            binding.get("observed_identity"), transport, f"{prefix}.observed_identity", errors
        )
        if selector_identity and observed_identity and not all(
            observed_identity.get(key) == value for key, value in selector_identity.items()
        ):
            errors.append(f"{prefix}.selector_identity does not match observed_identity")
        source = binding.get("source")
        if not isinstance(source, dict):
            errors.append(f"{prefix}.source must be an object")
        else:
            _reject_unknown(source, {"path", "sha256", "point_in_time"}, f"{prefix}.source", errors)
            _string(source.get("path"), f"{prefix}.source.path", errors)
            digest = _string(source.get("sha256"), f"{prefix}.source.sha256", errors)
            if digest is not None and SHA256_PATTERN.fullmatch(digest) is None:
                errors.append(f"{prefix}.source.sha256 must be lowercase SHA-256")
            if source.get("point_in_time") is not True:
                errors.append(f"{prefix}.source.point_in_time must equal true")
    if binding_transports != required:
        errors.append(
            "selection.bindings must contain exactly one binding per required transport in order"
        )

    inputs = data.get("inputs")
    if not isinstance(inputs, dict):
        errors.append("selection.inputs must be an object")
    else:
        _reject_unknown(inputs, {"registry", "observations"}, "selection.inputs", errors)
        _source_reference(inputs.get("registry"), "selection.inputs.registry", errors)
        _source_reference(inputs.get("observations"), "selection.inputs.observations", errors)

    authorization = data.get("authorization")
    if not isinstance(authorization, dict):
        errors.append("selection.authorization must be an object")
    else:
        _reject_unknown(
            authorization, {"granted", "allowed_operations"}, "selection.authorization", errors
        )
        if authorization.get("granted") is not False:
            errors.append("selection.authorization.granted must equal false")
        if authorization.get("allowed_operations") != []:
            errors.append("selection.authorization.allowed_operations must be empty")
    if data.get("hardware_access") is not False:
        errors.append("selection.hardware_access must equal false")
    if data.get("executables_started") is not False:
        errors.append("selection.executables_started must equal false")
    return {
        "ok": not errors,
        "schema_version": SELECTION_SCHEMA,
        "board_id": data.get("board_id"),
        "required_transports": required,
        "hardware_access": False,
        "executables_started": False,
        "errors": errors,
    }


def merge_observations(documents: list[dict[str, Any]]) -> dict[str, Any]:
    if not documents:
        raise RegistryError("at least one observations document is required")

    observations: list[dict[str, Any]] = []
    for index, document in enumerate(documents):
        validation = validate_observations(document)
        if not validation["ok"]:
            raise RegistryError(
                f"observations document {index + 1} is invalid: " + "; ".join(validation["errors"])
            )
        observations.extend(document["observations"])

    result = {"schema_version": OBSERVATIONS_SCHEMA, "observations": observations}
    validation = validate_observations(result)
    if not validation["ok"]:
        raise RegistryError("merged observations are invalid: " + "; ".join(validation["errors"]))
    return result


def _selector_matches(selector: dict[str, Any], observation: dict[str, Any]) -> bool:
    if selector["transport"] != observation["transport"]:
        return False
    observed = observation["identity"]
    return all(observed.get(key) == value for key, value in selector["identity"].items())


def resolve(
    registry: dict[str, Any], observations: dict[str, Any], required: set[str]
) -> dict[str, Any]:
    registry_validation = validate_registry(registry)
    observation_validation = validate_observations(observations)
    errors = registry_validation["errors"] + observation_validation["errors"]
    if errors:
        raise RegistryError("; ".join(errors))
    if not required:
        required = set(observation_validation["transports"])
    invalid_required = sorted(required - TRANSPORTS)
    if invalid_required:
        raise RegistryError(f"unsupported required transport(s): {invalid_required}")
    if not required:
        raise RegistryError("at least one required transport is needed")

    candidates: list[dict[str, Any]] = []
    evaluations: list[dict[str, Any]] = []
    all_observations = observations["observations"]
    for board in registry["boards"]:
        matched: dict[str, list[dict[str, str]]] = {}
        conflicts: dict[str, int] = {}
        for transport in sorted(required):
            transport_selectors = [
                selector for selector in board["selectors"] if selector["transport"] == transport
            ]
            hits: list[dict[str, str]] = []
            for observation in all_observations:
                matching_selectors = [
                    selector["id"]
                    for selector in transport_selectors
                    if _selector_matches(selector, observation)
                ]
                if matching_selectors:
                    hits.append(
                        {
                            "observation_id": observation["id"],
                            "selector_id": matching_selectors[0],
                        }
                    )
            matched[transport] = hits
            if len(hits) != 1:
                conflicts[transport] = len(hits)
        evaluation = {
            "board_id": board["id"],
            "matched": matched,
            "eligible": not conflicts,
            "match_count_conflicts": conflicts,
        }
        evaluations.append(evaluation)
        if not conflicts:
            candidates.append(evaluation)

    if len(candidates) == 1:
        status = "resolved"
        ok = True
        selected_board = candidates[0]["board_id"]
    elif candidates:
        status = "ambiguous"
        ok = False
        selected_board = None
    else:
        status = "no_match"
        ok = False
        selected_board = None
    return {
        "schema_version": RESULT_SCHEMA,
        "ok": ok,
        "status": status,
        "selected_board_id": selected_board,
        "required_transports": sorted(required),
        "candidate_board_ids": [candidate["board_id"] for candidate in candidates],
        "evaluations": evaluations,
        "hardware_access": False,
        "executables_started": False,
    }


def create_selection(
    registry: dict[str, Any],
    observations: dict[str, Any],
    resolution: dict[str, Any],
    inputs: dict[str, dict[str, str]],
) -> dict[str, Any]:
    if resolution.get("status") != "resolved" or not resolution.get("selected_board_id"):
        raise RegistryError("a uniquely resolved board is required to create a selection")
    board = next(
        item for item in registry["boards"] if item["id"] == resolution["selected_board_id"]
    )
    evaluation = next(
        item
        for item in resolution["evaluations"]
        if item["board_id"] == resolution["selected_board_id"]
    )
    bindings: list[dict[str, Any]] = []
    for transport in resolution["required_transports"]:
        match = evaluation["matched"][transport][0]
        selector = next(item for item in board["selectors"] if item["id"] == match["selector_id"])
        observation = next(
            item
            for item in observations["observations"]
            if item["id"] == match["observation_id"]
        )
        bindings.append(
            {
                "transport": transport,
                "selector_id": selector["id"],
                "observation_id": observation["id"],
                "selector_identity": dict(selector["identity"]),
                "observed_identity": dict(observation["identity"]),
                "source": dict(observation["source"]),
            }
        )
    selection = {
        "schema_version": SELECTION_SCHEMA,
        "ok": True,
        "status": "selected",
        "board_id": board["id"],
        "required_transports": resolution["required_transports"],
        "bindings": bindings,
        "inputs": inputs,
        "authorization": {"granted": False, "allowed_operations": []},
        "hardware_access": False,
        "executables_started": False,
    }
    validation = validate_selection(selection)
    if not validation["ok"]:
        raise RegistryError("generated selection is invalid: " + "; ".join(validation["errors"]))
    return selection
