import os
import json
import subprocess
from pathlib import Path

from receipts.analysis import analyze_manifest
from receipts.cli import main
from receipts.demo import _init_live_repo, bundled_manifest, run_demo, run_live_demo
from receipts.integrity import add_integrity
from receipts.replay import render_replay
from receipts.tour import SAMPLE_LABEL, get_tour


MANIFEST = {"meta": {"session_id": "demo", "agent": "codex", "duration_seconds": 1}, "final": {"changed_files": []}, "timeline": {"file_changes": [], "test_executions": [], "notable_commands": []}, "analysis": {"scope_drift": [], "risk_hints": [], "network_egress": []}}


def test_replay_is_single_file_with_embedded_manifest() -> None:
    html = render_replay(MANIFEST)
    assert "application/json" in html
    assert '"session_id": "demo"' in html
    assert "Observed event timeline" in html
    assert "Verify in browser" in html
    assert "Test hash resistance" in html
    assert "DEMO ONLY — local copy altered" in html
    assert "Reset recorded receipt" in html
    assert "Load another receipt" in html
    assert "Static delivery. Interactive evidence." in html
    assert "crypto.subtle.digest" in html


def test_replay_surfaces_the_dirty_worktree_attribution_boundary() -> None:
    manifest = {
        "meta": {
            "session_id": "dirty-demo",
            "agent": "codex",
            "duration_seconds": 1,
            "preexisting_dirty_paths": ["src/billing/legacy.py"],
        },
        "final": {"changed_files": [], "agent_changed_files": []},
        "timeline": {
            "file_changes": [
                {
                    "path": "src/billing/legacy.py",
                    "last_modified_observed_at": "2026-01-01T00:00:00Z",
                    "preexisting_at_start": True,
                    "net_changed_from_start": False,
                }
            ],
            "test_executions": [],
            "notable_commands": [],
        },
        "analysis": {"scope_drift": [], "risk_hints": [], "network_egress": []},
    }
    html = render_replay(manifest)
    assert "Attribution boundary" in html
    assert "pre-existing at start" in html
    assert "agent-attributed paths" in html


def test_tour_falls_back_without_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    label, text = get_tour(MANIFEST)
    assert label == SAMPLE_LABEL
    assert "invoice.py" in text


def test_demo_is_offline_and_writes_replay(tmp_path: Path, capsys) -> None:
    replay = run_demo(tmp_path)
    output = capsys.readouterr().out
    assert replay.exists()
    assert "Receipts — AI Session Trust Card" in output
    assert SAMPLE_LABEL in output


def test_live_demo_uses_a_bundled_agent_and_retains_artifacts(tmp_path: Path, monkeypatch, capsys) -> None:
    observed: dict[str, object] = {}

    def fake_capture(command, cwd, task):
        observed.update(command=command, cwd=cwd, task=task)
        receipts_dir = cwd / ".receipts"
        receipts_dir.mkdir()
        path = receipts_dir / "session-live.json"
        path.write_text(json.dumps(bundled_manifest()), encoding="utf-8")
        return path, 0

    def fake_replay(manifest, output, open_browser):
        assert manifest["integrity"]["sha256"]
        assert open_browser is False
        output.write_text("replay", encoding="utf-8")
        return output

    monkeypatch.setattr("receipts.demo.capture", fake_capture)
    monkeypatch.setattr("receipts.demo.write_replay", fake_replay)
    artifacts = run_live_demo(tmp_path)
    output = capsys.readouterr().out
    assert artifacts.workspace.exists()
    assert artifacts.manifest_path.exists()
    assert artifacts.replay_path.exists()
    assert observed["task"] == "fix the login bug"
    assert observed["command"][0] == "sh"
    assert Path(observed["command"][1]).name.endswith("-agent.sh")
    assert "standard-library unittest" in Path(observed["command"][1]).read_text(encoding="utf-8")
    assert "__init__.py" not in Path(observed["command"][1]).read_text(encoding="utf-8")
    assert "Fresh live proof — not the bundled recording" in output
    assert "Expected policy demonstration" in output


def test_dirty_baseline_live_setup_creates_real_preexisting_worktree_change(tmp_path: Path) -> None:
    workspace = _init_live_repo(tmp_path, dirty_baseline=True)
    status = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all"], cwd=workspace, text=True, capture_output=True, check=True
    ).stdout
    assert "src/billing/legacy.py" in status
    assert "deliberately not agent work" in (workspace / "src/billing/legacy.py").read_text(encoding="utf-8")


def test_dirty_baseline_live_demo_proves_the_boundary(tmp_path: Path, monkeypatch, capsys) -> None:
    observed: dict[str, object] = {}

    def fake_capture(command, cwd, task):
        observed.update(command=command, cwd=cwd, task=task)
        assert (cwd / "src/billing/legacy.py").exists()
        manifest = {
            "schema_version": 1,
            "meta": {
                "session_id": "dirty-live",
                "task": "fix the login bug",
                "agent": "other",
                "preexisting_dirty_paths": ["src/billing/legacy.py"],
            },
            "timeline": {
                "file_changes": [
                    {
                        "path": "src/login.py",
                        "last_modified_observed_at": "2026-01-01T00:00:00Z",
                        "net_changed_from_start": True,
                    }
                ],
                "test_executions": [
                    {
                        "command": "python3 -m unittest -q tests/test_login.py",
                        "result": "passed",
                        "timestamp": "2026-01-01T00:00:01Z",
                    }
                ],
                "notable_commands": [],
                "command_count": 1,
            },
            "final": {
                "changed_files": [
                    {"path": "src/billing/legacy.py", "additions": 3, "deletions": 0},
                    {"path": "src/login.py", "additions": 2, "deletions": 0},
                ],
                "agent_changed_files": [{"path": "src/login.py", "additions": 2, "deletions": 0}],
                "preexisting_changes_removed": [],
            },
        }
        manifest["analysis"] = analyze_manifest(manifest)
        receipts_dir = cwd / ".receipts"
        receipts_dir.mkdir()
        add_integrity(manifest, receipts_dir)
        path = receipts_dir / "session-dirty-live.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return path, 0

    def fake_replay(manifest, output, open_browser):
        output.write_text("replay", encoding="utf-8")
        return output

    monkeypatch.setattr("receipts.demo.capture", fake_capture)
    monkeypatch.setattr("receipts.demo.write_replay", fake_replay)
    artifacts = run_live_demo(tmp_path, dirty_baseline=True)
    output = capsys.readouterr().out

    assert artifacts.manifest_path.exists()
    assert observed["task"] == "fix the login bug"
    assert Path(observed["command"][1]).name.endswith("-agent.sh")
    assert "not attributed to the agent" in Path(observed["command"][1]).read_text(encoding="utf-8")
    assert "Fresh dirty-worktree proof — baseline is not agent work" in output
    assert "Expected attribution demonstration" in output
    assert "Evidence gate: PASS" in output


def test_dirty_baseline_switch_requires_live_mode(capsys) -> None:
    assert main(["demo", "--dirty-baseline"]) == 2
    assert "--dirty-baseline requires --live" in capsys.readouterr().err
