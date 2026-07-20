#!/usr/bin/env python3
"""Action-local bridge for the Receipts evidence gate."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from receipts.gate import evaluate_gate, render_gate  # noqa: E402
from receipts.integrity import verify_manifest  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate a Receipts evidence policy")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--sensitive-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"receipts action gate: cannot read manifest: {error}", file=sys.stderr)
        return 2
    ok, integrity_message = verify_manifest(manifest, args.manifest.parent)
    if not ok:
        print("Evidence gate: BLOCKED")
        print(f"Integrity: {integrity_message}")
        print("Policy was not evaluated because the receipt failed integrity verification.")
        return 1
    try:
        findings = evaluate_gate(manifest, sensitive_only=args.sensitive_only)
    except ValueError as error:
        print(f"receipts action gate: {error}", file=sys.stderr)
        return 2
    print(render_gate(findings, integrity_message, sensitive_only=args.sensitive_only))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
