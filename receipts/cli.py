"""Command line interface for Receipts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .capture import capture
from .integrity import keygen, verify_manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="receipts", description="Evidence for AI coding sessions")
    subcommands = parser.add_subparsers(dest="subcommand", required=True)
    run = subcommands.add_parser("run", help="record an agent command in a POSIX PTY")
    run.add_argument("--task", help="optional plain-language task, recorded for later scope analysis")
    run.add_argument("command", nargs=argparse.REMAINDER, help="command to run (prefix it with --)")
    verify = subcommands.add_parser("verify", help="verify a manifest hash and optional signature")
    verify.add_argument("session", help="manifest path or session id")
    verify.add_argument("--public-key", type=Path, help="Ed25519 public PEM path")
    key = subcommands.add_parser("keygen", help="create an optional Ed25519 keypair in .receipts/keys")
    key.add_argument("--output-dir", type=Path, default=Path(".receipts"), help="directory containing the keys folder")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.subcommand == "run":
        command = list(args.command)
        if command[:1] == ["--"]:
            command.pop(0)
        try:
            path, exit_code = capture(command, Path.cwd(), args.task)
        except (RuntimeError, ValueError) as error:
            print(f"receipts: {error}", file=sys.stderr)
            return 2
        print(f"Receipts recorded: {path}")
        return exit_code
    if args.subcommand == "keygen":
        try:
            private, public = keygen(args.output_dir)
        except RuntimeError as error:
            print(f"receipts: {error}", file=sys.stderr)
            return 2
        print(f"Created private key: {private}")
        print(f"Created public key: {public}")
        return 0
    if args.subcommand == "verify":
        candidate = Path(args.session)
        if not candidate.exists():
            session_id = args.session.removeprefix("session-").removesuffix(".json")
            candidate = Path(".receipts") / f"session-{session_id}.json"
        try:
            manifest = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            print(f"receipts: cannot read manifest: {error}", file=sys.stderr)
            return 2
        ok, message = verify_manifest(manifest, candidate.parent, args.public_key)
        print(f"{'OK' if ok else 'FAILED'}: {message}")
        return 0 if ok else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
