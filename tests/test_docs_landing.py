import json
from pathlib import Path

from receipts.public_feed import verify_public_projection


ROOT = Path(__file__).resolve().parents[1]


def test_public_landing_surfaces_live_public_projection_and_offline_proof():
    page = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")

    assert "Review what the agent" in page
    assert "Live public feed. Local-first proof." in page
    assert "Forensic replay" in page
    assert "Verify this receipt" in page
    assert "Not a hardcoded demo" in page
    assert "receipts demo --live" in page
    assert "Raw session data never leaves the local recorder" in page
    assert 'src="dashboard.js"' in page


def test_public_landing_uses_only_local_assets_and_safe_live_fallback_contract():
    page = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "docs" / "dashboard.js").read_text(encoding="utf-8")

    assert 'href="replay.html#red-flag"' in page
    assert "https://fonts." not in page
    assert "@import" not in page
    assert 'src="https://' not in page
    assert 'LIVE_RECEIPT_URL = "live/latest.json"' in script
    assert 'FALLBACK_RECEIPT_URL = "sample-session.json"' in script
    assert 'fetch(url, { cache: "no-store" })' in script
    assert "path_mode === \"aliased\"" in script
    assert 'crypto.subtle.digest("SHA-256"' in script


def test_public_dashboard_uses_a_hashed_alias_only_sample_projection():
    published = json.loads((ROOT / "docs" / "sample-session.json").read_text(encoding="utf-8"))

    assert verify_public_projection(published) == (True, "public projection sha256 verified")
    assert published["receipt"]["path_mode"] == "aliased"
    assert all(item["id"].startswith("file-") for item in published["files"])
