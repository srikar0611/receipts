"""Offline judge demo using a real dogfooded session bundled with Receipts."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

from .card import render_card
from .replay import write_replay
from .tour import get_tour


def bundled_manifest() -> dict:
    data = resources.files("receipts").joinpath("demo_data", "sample-session.json").read_text(encoding="utf-8")
    return json.loads(data)


def run_demo(cwd: Path) -> Path:
    manifest = bundled_manifest()
    print(render_card(manifest), end="")
    # Demo must be bulletproof in headless CI/WSL; explicit `receipts replay`
    # still asks the system browser to open the file.
    replay_path = write_replay(manifest, cwd / ".receipts" / "sample-replay.html", open_browser=False)
    print(f"Replay written: {replay_path}")
    label, tour = get_tour(manifest)
    print(f"\n## Review tour — {label}\n\n{tour}")
    return replay_path
