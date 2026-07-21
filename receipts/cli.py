"""Command line interface for Receipts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .capture import capture
from .card import load_manifest, render_card
from .demo import run_demo, run_live_demo
from .gate import evaluate_gate, render_gate
from .integrity import keygen, verify_manifest
from .public_feed import export_public_receipt
from .replay import write_replay
from .tour import get_tour


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="receipts", description="Evidence for AI coding sessions")
    subcommands = parser.add_subparsers(dest="subcommand", required=True)
    run = subcommands.add_parser("run", help="record an agent command in a POSIX PTY")
    run.add_argument("--task", help="optional plain-language task, recorded for later scope analysis")
    run.add_argument("command", nargs=argparse.REMAINDER, help="command to run (prefix it with --)")
    verify = subcommands.add_parser("verify", help="verify a manifest hash and optional signature")
    verify.add_argument("session", help="manifest path or session id")
    verify.add_argument("--public-key", type=Path, help="Ed25519 public PEM path")
    gate = subcommands.add_parser("gate", help="block untested changed files using recorded receipt evidence")
    gate.add_argument("session", nargs="?", help="manifest path or session id; defaults to newest")
    gate.add_argument("--sensitive-only", action="store_true", help="only block sensitive paths with NEVER EXECUTED evidence")
    gate.add_argument("--public-key", type=Path, help="Ed25519 public PEM path")
    key = subcommands.add_parser("keygen", help="create an optional Ed25519 keypair in .receipts/keys")
    key.add_argument("--output-dir", type=Path, default=Path(".receipts"), help="directory containing the keys folder")
    card = subcommands.add_parser("card", help="render a Markdown Trust Card")
    card.add_argument("session", nargs="?", help="manifest path or session id; defaults to newest")
    card.add_argument("--output", type=Path, help="write Markdown to this file as well as stdout")
    replay = subcommands.add_parser("replay", help="write and open a static HTML session replay")
    replay.add_argument("session", nargs="?", help="manifest path or session id; defaults to newest")
    replay.add_argument("--output", type=Path, help="HTML output path")
    replay.add_argument("--no-open", action="store_true", help="do not request the system browser")
    public = subcommands.add_parser(
        "export-public",
        help="write a privacy-preserving public evidence projection from a verified receipt",
    )
    public.add_argument("session", help="private manifest path or session id")
    public.add_argument("--output", type=Path, required=True, help="destination JSON path for the public projection")
    public.add_argument("--replay-output", type=Path, help="optional self-contained public replay HTML path")
    public.add_argument(
        "--landing-href",
        default="index.html",
        help="safe relative dashboard link inside the public replay (index.html or ../index.html)",
    )
    public.add_argument(
        "--publication-kind",
        choices=("curated-sample", "github-actions-demo", "manual"),
        default="manual",
        help="safe label for the public projection; source task text is never copied",
    )
    public.add_argument("--published-at", help="optional public publication timestamp (not a source-session timestamp)")
    public.add_argument("--public-key", type=Path, help="Ed25519 public PEM for verifying a signed source receipt")
    tour = subcommands.add_parser("tour", help="print a GPT review tour or offline sample")
    tour.add_argument("session", nargs="?", help="manifest path or session id; defaults to newest")
    demo = subcommands.add_parser("demo", help="run the bundled offline judge demo")
    demo.add_argument("--live", action="store_true", help="record a fresh retained PTY proof in a new Git repository")
    demo.add_argument(
        "--dirty-baseline",
        action="store_true",
        help="with --live, prove that pre-existing dirty work is not attributed to the agent",
    )
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
    if args.subcommand == "gate":
        try:
            manifest_path, manifest = load_manifest(args.session, Path.cwd())
        except (OSError, ValueError, json.JSONDecodeError) as error:
            print(f"receipts: cannot read manifest for gate: {error}", file=sys.stderr)
            return 2
        verified, integrity_message = verify_manifest(manifest, manifest_path.parent, args.public_key)
        if not verified:
            print("Evidence gate: BLOCKED")
            print(f"Integrity: {integrity_message}")
            print("Policy was not evaluated because the receipt failed integrity verification.")
            return 1
        try:
            findings = evaluate_gate(manifest, sensitive_only=args.sensitive_only)
        except ValueError as error:
            print(f"receipts: cannot evaluate gate: {error}", file=sys.stderr)
            return 2
        print(render_gate(findings, integrity_message, sensitive_only=args.sensitive_only))
        return 1 if findings else 0
    if args.subcommand == "card":
        try:
            _path, manifest = load_manifest(args.session, Path.cwd())
            card_text = render_card(manifest)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            print(f"receipts: cannot render card: {error}", file=sys.stderr)
            return 2
        if args.output:
            args.output.write_text(card_text, encoding="utf-8")
        print(card_text, end="")
        return 0
    if args.subcommand == "replay":
        try:
            manifest_path, manifest = load_manifest(args.session, Path.cwd())
            output = args.output or manifest_path.with_suffix(".html")
            output = write_replay(manifest, output, open_browser=not args.no_open)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            print(f"receipts: cannot create replay: {error}", file=sys.stderr)
            return 2
        print(f"Replay written: {output}")
        return 0
    if args.subcommand == "export-public":
        candidate = Path(args.session)
        if not candidate.exists():
            session_id = args.session.removeprefix("session-").removesuffix(".json")
            candidate = Path(".receipts") / f"session-{session_id}.json"
        try:
            _projection, source_message = export_public_receipt(
                candidate,
                args.output,
                replay_output=args.replay_output,
                landing_href=args.landing_href,
                publication_kind=args.publication_kind,
                published_at=args.published_at,
                public_key=args.public_key,
            )
        except (OSError, ValueError, json.JSONDecodeError) as error:
            print(f"receipts: cannot export public evidence: {error}", file=sys.stderr)
            return 2
        print(f"Public receipt written: {args.output}")
        if args.replay_output:
            print(f"Public replay written: {args.replay_output}")
        print(f"Source integrity: {source_message}")
        print("Privacy: source paths, task, commands, Git metadata, and transcripts were not published.")
        return 0
    if args.subcommand == "tour":
        try:
            _path, manifest = load_manifest(args.session, Path.cwd())
            label, tour_text = get_tour(manifest)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            print(f"receipts: cannot create tour: {error}", file=sys.stderr)
            return 2
        print(f"## Review tour — {label}\n\n{tour_text}")
        return 0
    if args.subcommand == "demo":
        if args.dirty_baseline and not args.live:
            print("receipts: --dirty-baseline requires --live", file=sys.stderr)
            return 2
        try:
            if args.live:
                run_live_demo(Path.cwd(), dirty_baseline=args.dirty_baseline)
            else:
                run_demo(Path.cwd())
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
            print(f"receipts: cannot run demo: {error}", file=sys.stderr)
            return 2
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
