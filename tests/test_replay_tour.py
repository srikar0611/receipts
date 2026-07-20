import os
import json
from pathlib import Path

from receipts.demo import bundled_manifest, run_demo, run_live_demo
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
