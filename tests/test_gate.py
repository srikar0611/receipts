import json
import subprocess
import sys
from pathlib import Path

from receipts.cli import main
from receipts.gate import evaluate_gate, render_gate
from receipts.integrity import add_integrity


ROOT = Path(__file__).resolve().parents[1]


def _manifest(*, path: str = "src/billing/invoice.py", status: str = "never_executed", sensitive: bool = True) -> dict:
    return {
        "schema_version": 1,
        "meta": {"session_id": "gate-demo"},
        "timeline": {"file_changes": [], "test_executions": [], "notable_commands": []},
        "final": {"changed_files": [{"path": path}]},
        "analysis": {
            "verification": [{"path": path, "status": status, "test_command": "", "test_timestamp": ""}],
            "risk_hints": [{"path": path, "reason": "sensitive billing path"}] if sensitive else [],
            "scope_drift": [{"path": path, "reason": "heuristic: path has no token overlap with stated task"}] if sensitive else [],
            "network_egress": [],
        },
    }


def _write_receipt(tmp_path: Path, manifest: dict) -> Path:
    add_integrity(manifest, tmp_path)
    path = tmp_path / "session-gate-demo.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_gate_blocks_sensitive_never_executed_file() -> None:
    findings = evaluate_gate(_manifest(), sensitive_only=True)
    assert findings[0].path == "src/billing/invoice.py"
    assert findings[0].details == (
        "no passing test was observed after the final edit",
        "sensitive billing path",
        "scope-drift heuristic",
    )
    report = render_gate(findings, "sha256 verified (unsigned)", sensitive_only=True)
    assert "Evidence gate: BLOCKED" in report
    assert "NEVER EXECUTED" in report


def test_sensitive_only_does_not_hide_default_policy_failure() -> None:
    manifest = _manifest(path="src/formatting/labels.py", sensitive=False)
    assert len(evaluate_gate(manifest)) == 1
    assert evaluate_gate(manifest, sensitive_only=True) == []


def test_gate_passes_when_recorded_verification_is_present() -> None:
    findings = evaluate_gate(_manifest(status="verified"))
    assert findings == []
    assert "Evidence gate: PASS" in render_gate(findings, "sha256 verified (unsigned)")


def test_cli_gate_refuses_tampered_receipt(tmp_path: Path, capsys) -> None:
    receipt = _write_receipt(tmp_path, _manifest())
    tampered = json.loads(receipt.read_text(encoding="utf-8"))
    tampered["meta"]["session_id"] = "altered"
    receipt.write_text(json.dumps(tampered), encoding="utf-8")
    assert main(["gate", str(receipt)]) == 1
    output = capsys.readouterr().out
    assert "Evidence gate: BLOCKED" in output
    assert "sha256 mismatch" in output


def test_action_gate_bridge_blocks_and_passes(tmp_path: Path) -> None:
    blocked = _write_receipt(tmp_path, _manifest())
    blocked_result = subprocess.run(
        [sys.executable, str(ROOT / "action" / "evaluate_gate.py"), str(blocked), "--sensitive-only"],
        text=True,
        capture_output=True,
    )
    assert blocked_result.returncode == 1
    assert "src/billing/invoice.py" in blocked_result.stdout

    passing = _write_receipt(tmp_path, _manifest(status="verified"))
    passing_result = subprocess.run(
        [sys.executable, str(ROOT / "action" / "evaluate_gate.py"), str(passing), "--sensitive-only"],
        text=True,
        capture_output=True,
    )
    assert passing_result.returncode == 0
    assert "Evidence gate: PASS" in passing_result.stdout
