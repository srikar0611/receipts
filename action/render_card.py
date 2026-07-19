#!/usr/bin/env python3
"""Action-local bridge so the composite action has no package-install step."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from receipts.card import render_card  # noqa: E402

print(render_card(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))), end="")
