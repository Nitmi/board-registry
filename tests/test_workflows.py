from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTION = re.compile(r"uses:\s+([^\s]+)")
PINNED = re.compile(r"[^@\s]+@[0-9a-f]{40}$")


def workflow(name: str) -> str:
    return (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")


def test_all_external_actions_are_pinned_to_commits() -> None:
    for name in ("ci.yml", "binary-release.yml"):
        actions = ACTION.findall(workflow(name))
        assert actions, name
        assert all(PINNED.fullmatch(action) for action in actions), (name, actions)


def test_release_workflow_is_tag_bound_and_narrow() -> None:
    content = workflow("binary-release.yml")
    for permission in (
        "contents: read",
        "id-token: write",
        "attestations: write",
        "artifact-metadata: write",
    ):
        assert permission in content
    assert "contents: write" not in content
    assert "pull_request:" not in content
    assert '- "v*.*.*"' in content
    assert "check-tag --tag" in content
    assert "Independent archive hashes differ" in content
    assert "actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6" in content
    assert "Offline resolution smoke check failed" in content
    assert 'python-version: "3.13.13"' in content
    assert "Offline selection smoke check failed" in content
    assert "Offline selection contract assertion failed" in content
    assert "validate selection" in content
