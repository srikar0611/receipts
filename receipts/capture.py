"""POSIX PTY capture and deterministic Git observations for Receipts."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import selectors
import shlex
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from .analysis import parse_notable_commands, parse_test_executions
from .integrity import add_integrity


TRANSCRIPT_LIMIT = 5 * 1024 * 1024
ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def run_git(cwd: Path, *args: str) -> str | None:
    """Return Git stdout or None when cwd is not a usable Git checkout."""
    try:
        result = subprocess.run(
            ["git", *args], cwd=cwd, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, check=False,
        )
    except OSError:
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def git_identity(cwd: Path) -> tuple[str | None, str | None]:
    return run_git(cwd, "branch", "--show-current"), run_git(cwd, "rev-parse", "HEAD")


def parse_status(status: str) -> list[str]:
    paths: list[str] = []
    for line in status.splitlines():
        if len(line) < 4:
            continue
        path = line[3:]
        # Porcelain rename/copy records are "old -> new" when -z is not used.
        if " -> " in path:
            path = path.rsplit(" -> ", 1)[-1]
        paths.append(path)
    return paths


def snapshot_git(cwd: Path, observed_at: str) -> dict[str, Any]:
    # Git's default status collapses an entirely untracked directory to
    # `?? src/`; evidence needs the concrete files, not a guessed expansion.
    status = run_git(cwd, "status", "--porcelain=v1", "--untracked-files=all") or ""
    paths = parse_status(status)
    diff = run_git(cwd, "diff", "--binary") or ""
    path_hashes = {path: file_snapshot_hash(cwd, path) for path in paths}
    return {
        "observed_at": observed_at,
        "paths": paths,
        "diff_sha256": hashlib.sha256(diff.encode("utf-8")).hexdigest(),
        "path_diff_sha256": path_hashes,
    }


def file_snapshot_hash(cwd: Path, path: str) -> str:
    """Hash the available diff or content for one observed path.

    Git does not include untracked files in `git diff`; including their bytes here
    lets the poller distinguish a later edit from an unchanged dirty file.
    """
    diff = run_git(cwd, "diff", "--binary", "--", path) or ""
    local = cwd / path
    content = local.read_bytes() if local.is_file() else b""
    return hashlib.sha256(diff.encode("utf-8") + b"\0" + content).hexdigest()


def update_file_observations(
    snapshots: list[dict[str, Any]], file_observations: dict[str, dict[str, str]], snapshot: dict[str, Any]
) -> None:
    snapshots.append(snapshot)
    for path in snapshot["paths"]:
        path_hash = snapshot["path_diff_sha256"][path]
        observation = file_observations.setdefault(
            path,
            {"path": path, "first_touched_at": snapshot["observed_at"], "last_diff_sha256": path_hash},
        )
        if observation["last_diff_sha256"] != path_hash:
            observation["last_diff_sha256"] = path_hash
            observation["last_modified_observed_at"] = snapshot["observed_at"]
        observation.setdefault("last_modified_observed_at", snapshot["observed_at"])


def detect_agent(command: list[str]) -> str:
    if not command:
        return "other"
    executable = Path(command[0]).name.lower()
    if executable in {"codex", "codex-cli"}:
        return "codex"
    if executable in {"claude", "claude-code"}:
        return "claude"
    if executable.startswith("cursor"):
        return "cursor"
    return "other"


def final_changed_files(cwd: Path, base_commit: str | None, observed_paths: list[str]) -> list[dict[str, Any]]:
    range_arg = base_commit or "HEAD"
    numstat = run_git(cwd, "diff", "--numstat", range_arg) or ""
    by_path: dict[str, dict[str, Any]] = {}
    for line in numstat.splitlines():
        fields = line.split("\t", 2)
        if len(fields) != 3:
            continue
        plus, minus, path = fields
        by_path[path] = {"path": path, "additions": None if plus == "-" else int(plus), "deletions": None if minus == "-" else int(minus)}
    for path in observed_paths:
        if path not in by_path:
            local = cwd / path
            additions = len(local.read_text(encoding="utf-8", errors="replace").splitlines()) if local.is_file() else 0
            by_path[path] = {"path": path, "additions": additions, "deletions": 0}
    return sorted(by_path.values(), key=lambda item: item["path"])


def validate_manifest(manifest: dict[str, Any]) -> None:
    """Small dependency-free schema check used before a manifest is written."""
    required = {"schema_version", "meta", "timeline", "final"}
    missing = required - manifest.keys()
    if missing:
        raise ValueError(f"manifest missing required fields: {', '.join(sorted(missing))}")
    meta = manifest["meta"]
    for key in ("session_id", "started_at", "ended_at", "cwd", "command", "agent"):
        if key not in meta:
            raise ValueError(f"manifest meta missing {key}")
    timeline = manifest["timeline"]
    for key in ("git_snapshots", "file_changes", "test_executions", "notable_commands"):
        if key not in timeline or not isinstance(timeline[key], list):
            raise ValueError(f"manifest timeline missing list {key}")


def attach_git_note(cwd: Path, commit: str | None, session_id: str) -> bool:
    if not commit:
        return False
    try:
        result = subprocess.run(
            ["git", "notes", "--ref=receipts", "add", "-f", "-m", f"Receipts session {session_id}", commit],
            cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
    except OSError:
        return False
    return result.returncode == 0


def capture(command: list[str], cwd: Path, task: str | None = None) -> tuple[Path, int]:
    """Run command in a PTY and persist an evidence manifest. POSIX only."""
    if os.name != "posix":
        raise RuntimeError("receipts run requires a POSIX PTY. On Windows, run it inside WSL.")
    if not command:
        raise ValueError("missing agent command; use: receipts run -- <agent command>")

    cwd = cwd.resolve()
    receipts_dir = cwd / ".receipts"
    receipts_dir.mkdir(exist_ok=True)
    session_id = f"{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
    started_at = utc_now()
    started_monotonic = time.monotonic()
    branch, base_commit = git_identity(cwd)
    snapshots: list[dict[str, Any]] = []
    observations: dict[str, dict[str, str]] = {}
    update_file_observations(snapshots, observations, snapshot_git(cwd, started_at))

    # Import lazily: Windows installations remain importable and receive the
    # clear WSL guidance above rather than an ImportError at CLI startup.
    import pty

    master_fd, slave_fd = pty.openpty()
    process = subprocess.Popen(command, cwd=cwd, stdin=slave_fd, stdout=slave_fd, stderr=slave_fd, close_fds=True)
    os.close(slave_fd)
    selector = selectors.DefaultSelector()
    selector.register(master_fd, selectors.EVENT_READ)
    transcript = bytearray()
    transcript_truncated = False
    next_poll = time.monotonic() + 2
    try:
        while True:
            timeout = max(0, min(0.5, next_poll - time.monotonic()))
            for _key, _mask in selector.select(timeout):
                try:
                    chunk = os.read(master_fd, 4096)
                except OSError:
                    chunk = b""
                if chunk and not transcript_truncated:
                    stamped = f"[{utc_now()}] ".encode("utf-8") + chunk
                    remaining = TRANSCRIPT_LIMIT - len(transcript)
                    transcript.extend(stamped[:remaining])
                    transcript_truncated = len(stamped) > remaining
            now = time.monotonic()
            if now >= next_poll:
                snapshot = snapshot_git(cwd, utc_now())
                update_file_observations(snapshots, observations, snapshot)
                next_poll = now + 2
            if process.poll() is not None:
                # Drain remaining PTY data before final observation.
                while True:
                    try:
                        chunk = os.read(master_fd, 4096)
                    except OSError:
                        break
                    if not chunk:
                        break
                    if not transcript_truncated:
                        stamped = f"[{utc_now()}] ".encode("utf-8") + chunk
                        remaining = TRANSCRIPT_LIMIT - len(transcript)
                        transcript.extend(stamped[:remaining])
                        transcript_truncated = len(stamped) > remaining
                break
    finally:
        selector.close()
        os.close(master_fd)

    ended_at = utc_now()
    final_snapshot = snapshot_git(cwd, ended_at)
    update_file_observations(snapshots, observations, final_snapshot)
    transcript_text = transcript.decode("utf-8", errors="replace")
    clean_text = ANSI_RE.sub("", transcript_text)
    raw_path = receipts_dir / f"session-{session_id}.log"
    clean_path = receipts_dir / f"session-{session_id}.clean.log"
    raw_path.write_text(transcript_text, encoding="utf-8")
    clean_path.write_text(clean_text, encoding="utf-8")
    changed = final_changed_files(cwd, base_commit, list(observations))
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "meta": {
            "session_id": session_id,
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_seconds": round(time.monotonic() - started_monotonic, 3),
            "cwd": str(cwd),
            "command": command,
            "command_display": shlex.join(command),
            "agent": detect_agent(command),
            "task": task,
            "git_branch": branch,
            "base_commit": base_commit,
            "transcript_truncated": transcript_truncated,
        },
        "timeline": {
            "git_snapshots": snapshots,
            "file_changes": sorted(observations.values(), key=lambda item: item["path"]),
            "test_executions": parse_test_executions(clean_text),
            "notable_commands": parse_notable_commands(clean_text),
        },
        "final": {"changed_files": changed},
        "artifacts": {"raw_transcript": raw_path.name, "clean_transcript": clean_path.name},
    }
    from .analysis import analyze_manifest

    manifest["meta"]["git_note_attached"] = attach_git_note(cwd, base_commit, session_id)
    manifest["analysis"] = analyze_manifest(manifest)
    add_integrity(manifest, receipts_dir)
    validate_manifest(manifest)
    manifest_path = receipts_dir / f"session-{session_id}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest_path, process.returncode or 0
