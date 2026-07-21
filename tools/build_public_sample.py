#!/usr/bin/env python3
"""Regenerate the privacy-safe public showcase assets from the local demo receipt.

This script intentionally reads the rich bundled demo manifest but writes only
the alias-only public projection to ``docs/``.  It is a release/build helper,
not a runtime dependency of the public site.
"""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from receipts.public_feed import export_public_receipt


def main() -> None:
    source = ROOT / "receipts" / "demo_data" / "sample-session.json"
    projection = ROOT / "docs" / "sample-session.json"
    replay = ROOT / "docs" / "replay.html"
    export_public_receipt(
        source,
        projection,
        replay_output=replay,
        publication_kind="curated-sample",
    )
    print(f"Wrote public projection: {projection}")
    print(f"Wrote public replay: {replay}")


if __name__ == "__main__":
    main()
