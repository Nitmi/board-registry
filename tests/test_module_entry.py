from __future__ import annotations

import subprocess
import sys


def test_module_entry_reports_version() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "board_registry", "--version"],
        capture_output=True,
        check=False,
        encoding="utf-8",
        errors="replace",
        timeout=10,
    )
    assert completed.returncode == 0
    assert completed.stdout.strip() == "board-registry 0.1.0"
    assert completed.stderr == ""
