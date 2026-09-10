# Embedded Board Registry

`board-registry` resolves one embedded board identity from offline, structured
serial, debug-probe, and BLE observations. It is designed for agents that must
fail closed instead of selecting the first discovered port or probe.

The tool does not enumerate hardware, open ports, attach targets, or start
component executables. `baud`, `blea`, and `embedded-debugger` remain the owners
of hardware discovery and evidence capture.

## Development

```powershell
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run board-registry validate registry examples/registry.json --json
uv run board-registry resolve examples/registry.json examples/observations.json `
  --require serial --require debug --json
```

Resolution succeeds only when exactly one board has exactly one matching
observation for every required transport. Exit code `3` means no eligible board;
exit code `4` means multiple eligible boards. Invalid schemas and evidence use
exit code `2`.

Selector matching is exact and field-based. A selector may deliberately omit
volatile fields such as a COM port, but every field it does declare must be
present and equal in the observation. Sources must record a lowercase SHA-256
and whether the evidence is point-in-time.

Machine-readable input contracts are published in `schemas/`. The runtime uses
the Python standard library only; JSON Schema is provided for editors, generators,
and independent validation rather than as a runtime dependency.
