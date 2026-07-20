from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from receipts.analysis import analyze_manifest
from receipts.capture import (
    final_changed_files,
    finalize_file_observations,
    snapshot_git,
    split_final_changes,
    update_file_observations,
)
from receipts.gate import evaluate_gate


def _snapshot(timestamp: str, states: dict[str, str]) -> dict[str, Any]:
    return {
        "observed_at": timestamp,
        "paths": sorted(states),
        "path_diff_sha256": states,
    }


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, text=True, check=True, capture_output=True
    ).stdout.strip()


def _build_manifest(
    *, baseline: dict[str, str], final: dict[str, str], observations: dict[str, dict[str, Any]], raw_changed: list[dict[str, Any]], tests: list[dict[str, str]] | None = None
) -> dict[str, Any]:
    full, agent_changed, removed = split_final_changes(raw_changed, baseline, _snapshot("2026-01-01T00:00:03Z", final))
    manifest: dict[str, Any] = {
        "meta": {"task": "fix the login bug", "preexisting_dirty_paths": sorted(baseline)},
        "timeline": {
            "file_changes": sorted(observations.values(), key=lambda item: item["path"]),
            "test_executions": tests or [],
            "notable_commands": [],
        },
        "final": {
            "changed_files": full,
            "agent_changed_files": agent_changed,
            "preexisting_changes_removed": removed,
        },
    }
    manifest["analysis"] = analyze_manifest(manifest)
    return manifest


def test_unchanged_preexisting_dirty_file_is_not_attributed_or_gated() -> None:
    baseline = {"src/billing/legacy.py": "baseline"}
    snapshots = [_snapshot("2026-01-01T00:00:00Z", baseline)]
    observations: dict[str, dict[str, Any]] = {}
    states: dict[str, str | None] = dict(baseline)
    final = {"src/billing/legacy.py": "baseline", "src/login.py": "agent-edit"}
    update_file_observations(
        snapshots, observations, states, _snapshot("2026-01-01T00:00:01Z", final), baseline
    )
    finalize_file_observations(observations, baseline, _snapshot("2026-01-01T00:00:03Z", final))
    manifest = _build_manifest(
        baseline=baseline,
        final=final,
        observations=observations,
        raw_changed=[
            {"path": "src/billing/legacy.py", "additions": 3, "deletions": 0},
            {"path": "src/login.py", "additions": 2, "deletions": 0},
        ],
        tests=[
            {
                "command": "pytest -q tests/test_login.py",
                "result": "passed",
                "timestamp": "2026-01-01T00:00:02Z",
            }
        ],
    )

    assert set(observations) == {"src/login.py"}
    assert [item["path"] for item in manifest["final"]["changed_files"]] == [
        "src/billing/legacy.py",
        "src/login.py",
    ]
    assert [item["path"] for item in manifest["final"]["agent_changed_files"]] == ["src/login.py"]
    assert [item["status"] for item in manifest["analysis"]["verification"]] == ["verified"]
    assert manifest["analysis"]["scope_drift"] == []
    assert manifest["analysis"]["risk_hints"] == []
    assert evaluate_gate(manifest, sensitive_only=True) == []


def test_preexisting_file_changed_again_is_labeled_and_analyzed() -> None:
    baseline = {"src/billing/legacy.py": "baseline"}
    snapshots = [_snapshot("2026-01-01T00:00:00Z", baseline)]
    observations: dict[str, dict[str, Any]] = {}
    states: dict[str, str | None] = dict(baseline)
    final = {"src/billing/legacy.py": "agent-edit"}
    update_file_observations(
        snapshots, observations, states, _snapshot("2026-01-01T00:00:01Z", final), baseline
    )
    finalize_file_observations(observations, baseline, _snapshot("2026-01-01T00:00:03Z", final))
    manifest = _build_manifest(
        baseline=baseline,
        final=final,
        observations=observations,
        raw_changed=[{"path": "src/billing/legacy.py", "additions": 4, "deletions": 1}],
    )

    change = observations["src/billing/legacy.py"]
    assert change["preexisting_at_start"] is True
    assert change["first_touched_at"] == "2026-01-01T00:00:01Z"
    assert change["net_changed_from_start"] is True
    assert manifest["final"]["agent_changed_files"][0]["preexisting_at_start"] is True
    assert manifest["analysis"]["verification"] == [
        {
            "path": "src/billing/legacy.py",
            "status": "never_executed",
            "test_command": "",
            "test_timestamp": "",
            "preexisting_at_start": True,
        }
    ]
    assert [item["path"] for item in manifest["analysis"]["scope_drift"]] == ["src/billing/legacy.py"]
    assert [item["path"] for item in manifest["analysis"]["risk_hints"]] == ["src/billing/legacy.py"]
    assert [finding.path for finding in evaluate_gate(manifest, sensitive_only=True)] == ["src/billing/legacy.py"]


def test_transient_preexisting_edit_is_timeline_evidence_not_a_final_gate_finding() -> None:
    baseline = {"src/billing/legacy.py": "baseline"}
    snapshots = [_snapshot("2026-01-01T00:00:00Z", baseline)]
    observations: dict[str, dict[str, Any]] = {}
    states: dict[str, str | None] = dict(baseline)
    update_file_observations(
        snapshots,
        observations,
        states,
        _snapshot("2026-01-01T00:00:01Z", {"src/billing/legacy.py": "agent-edit"}),
        baseline,
    )
    final = {"src/billing/legacy.py": "baseline"}
    update_file_observations(
        snapshots, observations, states, _snapshot("2026-01-01T00:00:02Z", final), baseline
    )
    finalize_file_observations(observations, baseline, _snapshot("2026-01-01T00:00:03Z", final))
    manifest = _build_manifest(
        baseline=baseline,
        final=final,
        observations=observations,
        raw_changed=[{"path": "src/billing/legacy.py", "additions": 3, "deletions": 0}],
    )

    assert observations["src/billing/legacy.py"]["net_changed_from_start"] is False
    assert manifest["final"]["agent_changed_files"] == []
    assert manifest["analysis"]["verification"] == []
    assert manifest["analysis"]["scope_drift"] == []
    assert manifest["analysis"]["risk_hints"] == []
    assert evaluate_gate(manifest, sensitive_only=True) == []


def test_removed_preexisting_change_is_retained_as_boundary_evidence() -> None:
    baseline = {"src/billing/legacy.py": "baseline"}
    snapshots = [_snapshot("2026-01-01T00:00:00Z", baseline)]
    observations: dict[str, dict[str, Any]] = {}
    states: dict[str, str | None] = dict(baseline)
    final: dict[str, str] = {}
    update_file_observations(
        snapshots, observations, states, _snapshot("2026-01-01T00:00:01Z", final), baseline
    )
    finalize_file_observations(observations, baseline, _snapshot("2026-01-01T00:00:03Z", final))
    manifest = _build_manifest(
        baseline=baseline,
        final=final,
        observations=observations,
        raw_changed=[],
    )

    assert observations["src/billing/legacy.py"]["last_observed_state"] == "clean"
    assert manifest["final"]["agent_changed_files"] == []
    assert manifest["final"]["preexisting_changes_removed"] == ["src/billing/legacy.py"]


def test_baseline_attribution_survives_an_agent_commit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "receipts-test@example.invalid")
    _git(repo, "config", "user.name", "Receipts Test")
    (repo / "src" / "billing").mkdir(parents=True)
    (repo / "src" / "billing" / "legacy.py").write_text("label = 'base'\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "baseline")
    base = _git(repo, "rev-parse", "HEAD")

    # This was already in the worktree when the receipt began.
    (repo / "src" / "billing" / "legacy.py").write_text("label = 'human draft'\n", encoding="utf-8")
    baseline = snapshot_git(repo, "2026-01-01T00:00:00Z", base)

    # The wrapped agent adds a separate file and commits both the prior state and
    # its own work. Snapshotting against the initial base keeps both visible.
    (repo / "src" / "login.py").write_text("def redirect():\n    return '/home'\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "agent commit")
    final = snapshot_git(repo, "2026-01-01T00:00:02Z", base)
    raw = final_changed_files(repo, base, final["paths"])
    full, agent_changed, removed = split_final_changes(raw, baseline["path_diff_sha256"], final)

    assert set(final["paths"]) == {"src/billing/legacy.py", "src/login.py"}
    assert {item["path"] for item in full} == {"src/billing/legacy.py", "src/login.py"}
    assert [item["path"] for item in agent_changed] == ["src/login.py"]
    assert removed == []
