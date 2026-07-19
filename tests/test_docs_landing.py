from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_public_landing_surfaces_real_recorded_session_evidence():
    page = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")

    assert "Every AI commit" in page
    assert "6" in page and "files changed" in page
    assert "2" in page and "test runs" in page
    assert "src/auth/login.py" in page
    assert "src/auth/session.py" in page
    assert "src/billing/invoice.py" in page
    assert "NEVER EXECUTED" in page
    assert "fix the login bug" in page
    assert "34d0…ff76" in page


def test_public_landing_is_self_contained_and_links_to_local_replay():
    page = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")

    assert 'href="replay.html"' in page
    assert "https://fonts." not in page
    assert "@import" not in page
    assert "<script" not in page
