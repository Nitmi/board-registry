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

After a unique resolution, emit a hash-bound transport selection for the next
workflow stage:

```powershell
board-registry select registry.json evidence\combined.observations.json `
  --require serial --require debug > evidence\board-selection.json
board-registry validate selection evidence\board-selection.json --json
```

The `embedded-board-registry.selection.v1` document carries the exact matched
selector, full observed transport identity, source evidence hash, and hashes of
the registry and observations inputs. It always contains
`authorization.granted=false` and an empty `allowed_operations` list. Consumers
may translate its observed serial port, probe selector, or BLE identifier into
their own native identity guards, but the document does not authorize opening,
connecting, attaching, resetting, flashing, or writing.

Probe discovery does not establish a target. Declare the target and firmware
hash separately in the hardware-test contract, then let `embedded-debugger`
perform its own target checks before any target operation.

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

Machine-readable input and selection contracts are published in `schemas/`. The runtime uses
the Python standard library only; JSON Schema is provided for editors, generators,
and independent validation rather than as a runtime dependency.

## Release candidate

The source includes a reproducible Windows x86_64 standalone packaging path.
It binds `board-registry.exe` to the project version, exact Git revision, size,
and SHA-256 in a two-file ZIP. Building, verification, and the standalone smoke
test remain offline with respect to hardware.

```powershell
uv sync --locked --extra binary --extra dev
uv run --extra binary python scripts\package_binary.py build `
  --output-dir build\release --work-dir build\pyinstaller --json
uv run --extra binary python scripts\package_binary.py verify `
  build\release\embedded-board-registry-0.2.1-windows-x86_64.zip `
  --checksum build\release\embedded-board-registry-0.2.1-windows-x86_64.zip.sha256 `
  --json
```

Tag builds require exactly `v0.2.1`, build twice on a GitHub-hosted Windows
runner, compare archives, run the offline resolution example, and attest the
archive. The workflow does not create a GitHub Release or grant write access to
repository contents.
