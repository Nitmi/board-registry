from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .adapters import adapt
from .core import (
    TRANSPORTS,
    RegistryError,
    create_selection,
    load_json,
    merge_observations,
    resolve,
    sha256,
    validate_observations,
    validate_registry,
    validate_selection,
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
    validate.add_argument("kind", choices=("registry", "observations", "selection"))
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

    select = commands.add_parser(
        "select", help="emit a non-authorizing transport selection for one resolved board"
    )
    select.add_argument("registry", type=Path)
    select.add_argument("observations", type=Path)
    select.add_argument(
        "--require",
        action="append",
        choices=sorted(TRANSPORTS),
        default=[],
        help="required transport; repeat for more than one",
    )
    select.add_argument("--json", action="store_true")

    adapter = commands.add_parser("adapt", help="convert one saved component discovery result")
    adapter.add_argument("source", choices=("baud", "embedded-debugger", "blea"))
    adapter.add_argument("path", type=Path)
    adapter.add_argument("--json", action="store_true")

    merge = commands.add_parser("merge", help="merge validated observation documents")
    merge.add_argument("paths", nargs="+", type=Path)
    merge.add_argument("--json", action="store_true")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "adapt":
            report = adapt(args.source, args.path)
            _print(report, True)
            return 0
        if args.command == "merge":
            report = merge_observations([load_json(path) for path in args.paths])
            _print(report, True)
            return 0
        if args.command == "validate":
            data = load_json(args.path)
            validators = {
                "registry": validate_registry,
                "observations": validate_observations,
                "selection": validate_selection,
            }
            report = validators[args.kind](data)
            report["path"] = str(args.path.resolve())
            report["sha256"] = sha256(args.path)
            _print(report, args.json)
            return 0 if report["ok"] else 2

        registry = load_json(args.registry)
        observations = load_json(args.observations)
        report = resolve(registry, observations, set(args.require))
        inputs = {
            "registry": {
                "path": str(args.registry.resolve()),
                "sha256": sha256(args.registry),
            },
            "observations": {
                "path": str(args.observations.resolve()),
                "sha256": sha256(args.observations),
            },
        }
        if args.command == "select" and report["status"] == "resolved":
            report = create_selection(registry, observations, report, inputs)
            _print(report, True)
            return 0
        report["registry"] = {
            "path": str(args.registry.resolve()),
            "sha256": sha256(args.registry),
        }
        report["observations"] = {
            "path": str(args.observations.resolve()),
            "sha256": sha256(args.observations),
        }
        _print(report, args.json or args.command == "select")
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
        _print(report, getattr(args, "json", False) or args.command == "select")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
