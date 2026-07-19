import os
from pathlib import Path

from receipts.demo import run_demo
from receipts.replay import render_replay
from receipts.tour import SAMPLE_LABEL, get_tour


MANIFEST = {"meta": {"session_id": "demo", "agent": "codex", "duration_seconds": 1}, "final": {"changed_files": []}, "timeline": {"file_changes": [], "test_executions": [], "notable_commands": []}, "analysis": {"scope_drift": [], "risk_hints": [], "network_egress": []}}


def test_replay_is_single_file_with_embedded_manifest() -> None:
    html = render_replay(MANIFEST)
    assert "application/json" in html
    assert '"session_id": "demo"' in html
    assert "Observed event timeline" in html
    assert "Verify in browser" in html
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
