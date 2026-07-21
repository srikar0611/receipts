"""Privacy and integrity tests for the optional public live-evidence feed."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from receipts.integrity import add_integrity
from receipts.public_feed import (
    PUBLIC_FORMAT,
    export_public_receipt,
    render_public_replay,
    sanitize_manifest,
    verify_public_projection,
)


ROOT = Path(__file__).resolve().parents[1]


def rich_private_manifest(tmp_path: Path) -> dict:
    """A realistic hostile fixture: every marked string must stay private."""
    manifest = {
        "schema_version": 1,
        "meta": {
            "session_id": "private-session-42",
            "started_at": "2026-07-21T08:00:00.000Z",
            "ended_at": "2026-07-21T08:00:12.800Z",
            "duration_seconds": 12.8,
            "cwd": "/home/alice/private-customer-repo",
            "command": ["codex", "fix", "--token=super-secret-token"],
            "command_display": "codex fix --token=super-secret-token",
            "agent": "codex",
            "task": "Fix Acme customer's private invoice redirect",
            "git_branch": "customer/acme-private-fix",
            "base_commit": "aabbccddeeff00112233445566778899",
            "preexisting_dirty_paths": ["src/billing/customer_acme.py"],
            "transcript_truncated": False,
        },
        "timeline": {
            "git_snapshots": [{"paths": ["src/auth/login.py"], "diff_sha256": "private-diff-hash"}],
            "file_changes": [
                {
                    "path": "src/auth/login.py",
                    "last_modified_observed_at": "2026-07-21T08:00:02.000Z",
                    "last_diff_sha256": "private-file-hash",
                    "preexisting_at_start": False,
                },
                {
                    "path": "src/billing/customer_acme.py",
                    "last_modified_observed_at": "2026-07-21T08:00:12.700Z",
                    "last_diff_sha256": "private-billing-hash",
                    "preexisting_at_start": True,
                },
            ],
            "test_executions": [
                {
                    "timestamp": "2026-07-21T08:00:04.000Z",
                    "command": "pytest tests/test_login.py --token=super-secret-token",
                    "result": "passed",
                    "summary": "1 passed for Acme customer",
                },
                {"timestamp": "unparsed", "command": "curl https://private.example/?token=super-secret-token", "result": "unparsed"},
            ],
            "notable_commands": [{"command": "curl https://private.example/?token=super-secret-token", "network_egress": True}],
            "command_count": 9,
        },
        "final": {
            "changed_files": [
                {"path": "src/auth/login.py", "additions": 2, "deletions": 1},
                {"path": "src/billing/customer_acme.py", "additions": 4, "deletions": 0},
            ],
            "agent_changed_files": [
                {"path": "src/auth/login.py", "additions": 2, "deletions": 1},
                {"path": "src/billing/customer_acme.py", "additions": 4, "deletions": 0},
            ],
            "preexisting_changes_removed": [],
        },
        "artifacts": {"raw_transcript": "session-private.log", "clean_transcript": "session-private.clean.log"},
        "analysis": {
            "verification": [
                {"path": "src/auth/login.py", "status": "verified"},
                {"path": "src/billing/customer_acme.py", "status": "never_executed"},
            ],
            "scope_drift": [{"path": "src/billing/customer_acme.py", "reason": "private scope heuristic"}],
            "risk_hints": [{"path": "src/billing/customer_acme.py", "reason": "private sensitive billing path"}],
            "network_egress": [{"command": "curl https://private.example/?token=super-secret-token"}],
        },
    }
    add_integrity(manifest, tmp_path)
    return manifest


def test_sanitizer_produces_alias_only_projection_and_leaks_no_private_strings(tmp_path: Path) -> None:
    manifest = rich_private_manifest(tmp_path)

    projection = sanitize_manifest(manifest, publication_kind="github-actions-demo", published_at="2026-07-21T09:00:00Z")
    body = json.dumps(projection, sort_keys=True)

    assert projection["format"] == PUBLIC_FORMAT
    assert projection["receipt"]["path_mode"] == "aliased"
    assert [item["id"] for item in projection["files"]] == ["file-001", "file-002"]
    assert projection["files"][1]["verification"] == "never_executed"
    assert projection["files"][1]["risk_categories"] == ["sensitive_path", "scope_drift"]
    assert projection["files"][1]["preexisting_at_start"] is True
    assert projection["summary"]["preexisting_dirty_count"] == 1
    assert projection["tests"] == [
        {"id": "test-001", "runner": "pytest", "result": "passed", "offset_ms": 4000},
        {"id": "test-002", "runner": "recorded test runner", "result": "unparsed", "offset_ms": None},
    ]
    assert projection["summary"]["network_egress_observed"] is True
    for private in (
        "private-customer-repo",
        "private-session-42",
        "super-secret-token",
        "customer_acme.py",
        "Acme",
        "aabbccddeeff",
        "private.example",
        "session-private",
        "private-diff-hash",
        "2026-07-21T08:00",
    ):
        assert private not in body
    assert verify_public_projection(projection) == (True, "public projection sha256 verified")


def test_sanitizer_is_deterministic_and_public_hash_detects_mutation(tmp_path: Path) -> None:
    manifest = rich_private_manifest(tmp_path)

    first = sanitize_manifest(manifest)
    second = sanitize_manifest(copy.deepcopy(manifest))
    assert first == second

    altered = copy.deepcopy(first)
    altered["files"][0]["verification"] = "never_executed"
    assert verify_public_projection(altered) == (False, "public projection sha256 mismatch")


def test_export_refuses_tampered_private_source_before_writing_projection(tmp_path: Path) -> None:
    manifest = rich_private_manifest(tmp_path)
    source = tmp_path / "session-private.json"
    source.write_text(json.dumps(manifest), encoding="utf-8")
    manifest["meta"]["task"] = "changed after hashing"
    source.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="source receipt failed integrity verification"):
        export_public_receipt(source, tmp_path / "latest.json")
    assert not (tmp_path / "latest.json").exists()


def test_public_replay_embeds_only_public_projection(tmp_path: Path) -> None:
    manifest = rich_private_manifest(tmp_path)
    projection = sanitize_manifest(manifest)
    html = render_public_replay(projection)

    assert "Alias-only evidence projection" in html
    assert "Verify projection hash" in html
    assert "crypto.subtle.digest" in html
    assert "file-001" in html
    assert "customer_acme.py" not in html
    assert "super-secret-token" not in html
    assert 'href="index.html"' in html
    assert 'href="../index.html"' in render_public_replay(projection, landing_href="../index.html")
    with pytest.raises(ValueError, match="landing href"):
        render_public_replay(projection, landing_href="https://untrusted.example")


def test_checked_in_public_sample_is_a_sanitized_derivative_not_the_private_demo_manifest() -> None:
    bundled = json.loads((ROOT / "receipts" / "demo_data" / "sample-session.json").read_text(encoding="utf-8"))
    published = json.loads((ROOT / "docs" / "sample-session.json").read_text(encoding="utf-8"))
    public_html = (ROOT / "docs" / "replay.html").read_text(encoding="utf-8")

    assert published != bundled
    assert verify_public_projection(published) == (True, "public projection sha256 verified")
    for private in (str(bundled["meta"]["cwd"]), bundled["meta"]["command_display"], "src/billing/invoice.py"):
        assert private not in json.dumps(published)
        assert private not in public_html
