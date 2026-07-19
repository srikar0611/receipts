import copy
from pathlib import Path

from receipts.analysis import analyze_manifest, parse_notable_commands, parse_test_executions
from receipts.integrity import add_integrity, verify_manifest


FIXTURES = Path(__file__).parent / "fixtures"


def test_parser_recognizes_pytest_jest_and_go() -> None:
    for fixture, expected in (("pytest.txt", "pytest"), ("jest.txt", "npm test"), ("go_test.txt", "go test")):
        events = parse_test_executions((FIXTURES / fixture).read_text())
        assert len(events) == 1
        assert expected in events[0]["command"]
        assert events[0]["result"] == "passed"


def test_parser_marks_incomplete_runner_unparsed() -> None:
    events = parse_test_executions("$ pytest -q tests/test_login.py\ncollecting ...\n")
    assert events == [{"timestamp": "unparsed", "command": "pytest -q tests/test_login.py", "result": "unparsed", "summary": ""}]


def test_parser_tolerates_timestamped_pytest_progress() -> None:
    transcript = "[2026-01-01T10:00:00Z] + pytest -q tests/test_login.py\n.[2026-01-01T10:00:01Z] [100%]\n[2026-01-01T10:00:01Z] 1 passed in 0.01s\n"
    events = parse_test_executions(transcript)
    assert events[0]["result"] == "passed"


def test_analysis_has_one_never_executed_and_one_scope_flag() -> None:
    manifest = {
        "meta": {"task": "fix the login bug"},
        "timeline": {
            "file_changes": [
                {"path": "src/auth/login.py", "last_modified_observed_at": "2026-01-01T10:00:00Z"},
                {"path": "src/auth/session.py", "last_modified_observed_at": "2026-01-01T10:02:00Z"},
                {"path": "src/billing/invoice.py", "last_modified_observed_at": "2026-01-01T10:04:00Z"},
                {"path": "src/auth/__pycache__/login.cpython-312.pyc", "last_modified_observed_at": "2026-01-01T10:00:00Z"},
            ],
            "test_executions": [
                {"command": "pytest -q tests/test_login.py", "result": "passed", "timestamp": "2026-01-01T10:01:00Z"},
                {"command": "pytest -q", "result": "passed", "timestamp": "2026-01-01T10:03:00Z"},
            ],
            "notable_commands": [{"command": "curl https://example.invalid", "network_egress": True}],
        },
        "final": {"changed_files": [
            {"path": "src/auth/login.py"}, {"path": "src/auth/session.py"}, {"path": "src/billing/invoice.py"},
        ]},
    }
    analysis = analyze_manifest(manifest)
    assert [item["status"] for item in analysis["verification"]] == ["verified", "indirectly_exercised", "never_executed"]
    assert [item["path"] for item in analysis["scope_drift"]] == ["src/billing/invoice.py"]
    assert {item["path"] for item in analysis["risk_hints"]} == {"src/auth/login.py", "src/auth/session.py", "src/billing/invoice.py"}
    assert len(analysis["network_egress"]) == 1


def test_notable_commands_are_explicit() -> None:
    events = parse_notable_commands("[2026-01-01T00:00:00Z] + git status\n+ curl https://example.invalid\n+ pip install rich\n")
    assert [event["kind"] for event in events] == ["git", "network_egress", "package_install"]


def test_unsigned_integrity_detects_tampering(tmp_path: Path) -> None:
    manifest = {"schema_version": 1, "meta": {"session_id": "demo"}}
    add_integrity(manifest, tmp_path)
    assert verify_manifest(manifest, tmp_path) == (True, "sha256 verified (unsigned)")
    tampered = copy.deepcopy(manifest)
    tampered["meta"]["session_id"] = "changed"
    assert verify_manifest(tampered, tmp_path)[0] is False
