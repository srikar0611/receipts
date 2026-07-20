"""Offline judge demo using a real dogfooded session bundled with Receipts."""

from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from .card import render_card
from .capture import capture
from .gate import evaluate_gate, render_gate
from .integrity import verify_manifest
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


@dataclass(frozen=True)
class LiveDemoArtifacts:
    """Paths from a retained, fresh proof run."""

    workspace: Path
    manifest_path: Path
    replay_path: Path


def _git(workspace: Path, *args: str) -> None:
    """Run one setup-only Git command with an actionable failure."""
    try:
        result = subprocess.run(
            ["git", *args], cwd=workspace, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
        )
    except OSError as error:
        raise RuntimeError("`receipts demo --live` needs Git on PATH") from error
    if result.returncode:
        message = result.stderr.strip() or result.stdout.strip() or "unknown Git error"
        raise RuntimeError(f"could not prepare live-proof Git repository: {message}")


def _init_live_repo(cwd: Path) -> Path:
    """Create a retained throwaway repository under the caller's receipts dir."""
    proof_root = cwd / ".receipts" / "live-proofs"
    proof_root.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="live-proof-", dir=proof_root))
    _git(workspace, "init", "-q")
    _git(workspace, "config", "user.email", "receipts-live@example.invalid")
    _git(workspace, "config", "user.name", "Receipts live proof")
    (workspace / ".gitkeep").touch()
    _git(workspace, "add", ".gitkeep")
    _git(workspace, "commit", "-qm", "Receipts live-proof baseline")
    return workspace


def _write_live_agent(workspace: Path) -> Path:
    """Copy the fixture beside, never inside, the repository being observed."""
    fixture = resources.files("receipts").joinpath("demo_data", "live_agent.sh")
    # If this lived inside ``workspace``, the harness script itself would be
    # reported as an untracked agent change before capture starts.
    script = workspace.parent / f"{workspace.name}-agent.sh"
    script.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
    script.chmod(0o700)
    return script


def run_live_demo(cwd: Path) -> LiveDemoArtifacts:
    """Record a new session through the same PTY path used by `receipts run`.

    Unlike `run_demo`, this intentionally creates a new Git repository and
    receipt every time. The retained workspace makes every printed fact easy
    to inspect after the command exits.
    """
    workspace = _init_live_repo(cwd.resolve())
    agent = _write_live_agent(workspace)
    try:
        manifest_path, exit_code = capture(["sh", str(agent)], workspace, task="fix the login bug")
    except Exception:
        print(f"Live-proof workspace retained for inspection: {workspace}")
        raise
    if exit_code:
        raise RuntimeError(f"live-proof agent exited with code {exit_code}; workspace retained at {workspace}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    verified, message = verify_manifest(manifest, manifest_path.parent)
    if not verified:
        raise RuntimeError(f"live proof did not verify: {message}")
    findings = evaluate_gate(manifest, sensitive_only=True)
    if not findings:
        raise RuntimeError("live proof fixture did not produce the expected sensitive NEVER EXECUTED finding")
    replay_path = write_replay(manifest, manifest_path.with_suffix(".html"), open_browser=False)
    print("\n## Fresh live proof — not the bundled recording\n")
    print(render_card(manifest), end="")
    print(f"Live-proof workspace retained: {workspace}")
    print(f"Fresh manifest: {manifest_path}")
    print(f"Integrity: OK — {message}")
    print(f"Replay written: {replay_path}")
    print("\nExpected policy demonstration — the command succeeds because this block is the proof:")
    print(render_gate(findings, message, sensitive_only=True))
    return LiveDemoArtifacts(workspace=workspace, manifest_path=manifest_path, replay_path=replay_path)
