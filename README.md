# Embedded Board Registry

`board-registry` resolves one embedded board identity from offline, structured
serial, debug-probe, and BLE observations. It is designed for agents that must
fail closed instead of selecting the first discovered port or probe.

The tool does not enumerate hardware, open ports, attach targets, or start
component executables. `baud`, `blea`, and `embedded-debugger` remain the owners
of hardware discovery and evidence capture.

## Offline evidence pipeline

Capture discovery output with each component under that component's own safety
policy. Then adapt and combine the saved files without touching hardware:

```powershell
board-registry adapt baud evidence\baud-list.json > evidence\serial.observations.json
board-registry adapt embedded-debugger evidence\probes-list.json > evidence\debug.observations.json
board-registry adapt blea evidence\ble-scan.json > evidence\ble.observations.json
board-registry merge evidence\serial.observations.json evidence\debug.observations.json `
  > evidence\combined.observations.json
board-registry resolve registry.json evidence\combined.observations.json `
  --require serial --require debug --json
```

Adapters are bound to the current native JSON contracts and reject unknown
fields. Every observation records the absolute source path and SHA-256. Probe
discovery does not prove a target identity, so the debugger adapter never adds a
target name. BLE uses the backend-neutral `identifier` field because its value
may be a MAC address or a platform-specific UUID.

## Development

```powershell
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run board-registry adapt baud path\to\saved-baud-list.json
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
