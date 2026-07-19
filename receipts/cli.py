"""Command line interface for Receipts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .capture import capture


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="receipts", description="Evidence for AI coding sessions")
    subcommands = parser.add_subparsers(dest="subcommand", required=True)
    run = subcommands.add_parser("run", help="record an agent command in a POSIX PTY")
    run.add_argument("--task", help="optional plain-language task, recorded for later scope analysis")
    run.add_argument("command", nargs=argparse.REMAINDER, help="command to run (prefix it with --)")
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
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
