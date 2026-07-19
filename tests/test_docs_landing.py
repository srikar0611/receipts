import json
from pathlib import Path

from receipts.integrity import manifest_sha256


ROOT = Path(__file__).resolve().parents[1]


def test_public_landing_surfaces_real_recorded_session_evidence():
    page = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")

    assert "Review what the agent" in page
    assert "Static delivery. Interactive evidence." in page
    assert "Forensic replay" in page
    assert "Verify this receipt" in page
    assert 'src="dashboard.js"' in page


def test_public_landing_uses_only_local_dashboard_assets():
    page = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "docs" / "dashboard.js").read_text(encoding="utf-8")

    assert 'href="replay.html"' in page
    assert "https://fonts." not in page
    assert "@import" not in page
    assert 'src="https://' not in page
    assert 'fetch("sample-session.json"' in script
    assert 'crypto.subtle.digest("SHA-256"' in script


def test_public_dashboard_uses_the_real_hashed_sample_manifest():
    bundled = json.loads((ROOT / "receipts" / "demo_data" / "sample-session.json").read_text(encoding="utf-8"))
    published = json.loads((ROOT / "docs" / "sample-session.json").read_text(encoding="utf-8"))

    assert published == bundled
    assert manifest_sha256(published) == published["integrity"]["sha256"]
