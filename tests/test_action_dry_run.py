import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run_dry_action(tmp_path: Path, comments: str) -> str:
    event = tmp_path / "event.json"
    card = tmp_path / "card.md"
    mock = tmp_path / "mock-curl"
    event.write_text(json.dumps({"pull_request": {"number": 42}}))
    card.write_text("## card\n")
    mock.write_text(f"#!/usr/bin/env bash\necho '{comments}'\n")
    mock.chmod(0o755)
    environment = os.environ | {
        "GITHUB_EVENT_PATH": str(event), "GITHUB_REPOSITORY": "owner/repo", "GITHUB_TOKEN": "test-token",
        "RECEIPTS_CARD_PATH": str(card), "RECEIPTS_DRY_RUN": "true", "CURL_BIN": str(mock),
    }
    result = subprocess.run(["bash", str(ROOT / "action" / "post_comment.sh")], text=True, capture_output=True, env=environment, check=True)
    return result.stdout


def test_action_dry_run_mocks_github_api_create(tmp_path: Path) -> None:
    output = _run_dry_action(tmp_path, "[]")
    assert "DRY RUN: POST https://api.github.com/repos/owner/repo/issues/42/comments" in output


def test_action_dry_run_mocks_github_api_update(tmp_path: Path) -> None:
    output = _run_dry_action(tmp_path, '[{"id": 99, "body": "<!-- receipts-trust-card --> old"}]')
    assert "DRY RUN: PATCH https://api.github.com/repos/owner/repo/issues/42/comments/99" in output
