from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .core import (
    TRANSPORTS,
    RegistryError,
    load_json,
    resolve,
    sha256,
    validate_observations,
    validate_registry,
)


def _print(report: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif report.get("ok"):
        print(report.get("status", "valid"))
    else:
        print(report.get("status", "invalid"), file=sys.stderr)
        for error in report.get("errors", []):
            print(f"- {error}", file=sys.stderr)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="board-registry",
        description="Resolve embedded board identity from offline structured evidence.",
    )
    root.add_argument("--version", action="version", version=f"board-registry {__version__}")
    commands = root.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="validate one registry or observation file")
    validate.add_argument("kind", choices=("registry", "observations"))
    validate.add_argument("path", type=Path)
    validate.add_argument("--json", action="store_true")

    match = commands.add_parser("resolve", help="resolve exactly one registered board")
    match.add_argument("registry", type=Path)
    match.add_argument("observations", type=Path)
    match.add_argument(
        "--require",
        action="append",
        choices=sorted(TRANSPORTS),
        default=[],
        help="required transport; repeat for more than one",
    )
    match.add_argument("--json", action="store_true")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "validate":
            data = load_json(args.path)
            report = (
                validate_registry(data) if args.kind == "registry" else validate_observations(data)
            )
            report["path"] = str(args.path.resolve())
            report["sha256"] = sha256(args.path)
            _print(report, args.json)
            return 0 if report["ok"] else 2

        registry = load_json(args.registry)
        observations = load_json(args.observations)
        report = resolve(registry, observations, set(args.require))
        report["registry"] = {
            "path": str(args.registry.resolve()),
            "sha256": sha256(args.registry),
        }
        report["observations"] = {
            "path": str(args.observations.resolve()),
            "sha256": sha256(args.observations),
        }
        _print(report, args.json)
        return {"resolved": 0, "no_match": 3, "ambiguous": 4}[report["status"]]
    except RegistryError as error:
        report = {
            "schema_version": "embedded-board-registry.error.v1",
            "ok": False,
            "status": "invalid_input",
            "hardware_access": False,
            "executables_started": False,
            "errors": [str(error)],
        }
        _print(report, getattr(args, "json", False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
