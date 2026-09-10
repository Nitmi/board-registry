from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from board_registry.core import IDENTITY_FIELDS, OBSERVATIONS_SCHEMA, REGISTRY_SCHEMA

ROOT = Path(__file__).resolve().parents[1]


def load(name: str) -> dict:
    return json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))


def test_registry_schema_tracks_runtime_identity_fields() -> None:
    schema = load("registry.schema.json")
    assert schema["properties"]["schema_version"]["const"] == REGISTRY_SCHEMA
    for transport in ("serial", "debug", "ble"):
        properties = schema["$defs"][f"{transport}Identity"]["properties"]
        assert set(properties) == IDENTITY_FIELDS[transport]


def test_observation_schema_tracks_runtime_version() -> None:
    schema = load("observations.schema.json")
    assert schema["properties"]["schema_version"]["const"] == OBSERVATIONS_SCHEMA


def test_observation_schema_accepts_empty_point_in_time_result() -> None:
    schema = load("observations.schema.json")
    registry_schema = load("registry.schema.json")
    resources = Registry().with_resource(
        registry_schema["$id"], Resource.from_contents(registry_schema)
    )
    Draft202012Validator(schema, registry=resources).validate(
        {"schema_version": OBSERVATIONS_SCHEMA, "observations": []}
    )


def test_published_schemas_accept_bundled_examples() -> None:
    registry_schema = load("registry.schema.json")
    observations_schema = load("observations.schema.json")
    resources = Registry().with_resource(
        registry_schema["$id"], Resource.from_contents(registry_schema)
    )
    Draft202012Validator.check_schema(registry_schema)
    Draft202012Validator.check_schema(observations_schema)
    Draft202012Validator(registry_schema).validate(
        json.loads((ROOT / "examples" / "registry.json").read_text(encoding="utf-8"))
    )
    Draft202012Validator(observations_schema, registry=resources).validate(
        json.loads((ROOT / "examples" / "observations.json").read_text(encoding="utf-8"))
    )
