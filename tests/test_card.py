import json
from pathlib import Path

from receipts.card import render_card


def test_card_matches_trust_card_structure() -> None:
    manifest = {
        "meta": {"task": "fix the login bug", "agent": "codex", "session_id": "demo", "duration_seconds": 92, "git_branch": "fix/login", "base_commit": "abcdef123"},
        "timeline": {"command_count": 3, "test_executions": [{}, {}]},
        "final": {"changed_files": [{"path": "src/auth/login.py", "additions": 4, "deletions": 1}]},
        "analysis": {"verification": [{"path": "src/auth/login.py", "status": "verified", "test_command": "pytest tests/test_login.py", "test_timestamp": "2026-01-01T14:02:00Z"}], "scope_drift": [], "risk_hints": [{"path": "src/auth/login.py", "reason": "sensitive auth path"}], "network_egress": []},
        "integrity": {"sha256": "1234567890abcdef"},
    }
    card = render_card(manifest)
    assert "## 🧾 Receipts — AI Session Trust Card" in card
    assert "✅ verified" in card
    assert "**Flags**" in card
    assert "Integrity: sha256 `1234…cdef`" in card
