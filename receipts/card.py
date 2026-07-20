"""Deterministic Markdown Trust Card rendering."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any


def _duration(seconds: float | int | None) -> str:
    total = int(seconds or 0)
    minutes, seconds = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def _at(timestamp: str) -> str:
    if not timestamp or timestamp == "unparsed":
        return "an unparsed time"
    return timestamp[11:16] + " UTC" if len(timestamp) >= 16 else timestamp


def _verification_row(item: dict[str, Any]) -> str:
    path = item["path"]
    status = item["status"]
    attribution = " · pre-existing at start" if item.get("preexisting_at_start") else ""
    if status == "verified":
        return f"| `{path}` | ✅ verified — `{item['test_command']}` passed at {_at(item['test_timestamp'])}{attribution} |"
    if status == "indirectly_exercised":
        return f"| `{path}` | 🟡 indirectly exercised — `{item['test_command']}` passed after last observed edit{attribution} |"
    return f"| `{path}` | 🔴 NEVER EXECUTED in this session{attribution} |"


def render_card(manifest: dict[str, Any]) -> str:
    meta = manifest.get("meta", {})
    final = manifest.get("final", {})
    timeline = manifest.get("timeline", {})
    analysis = manifest.get("analysis", {})
    changed = final["agent_changed_files"] if "agent_changed_files" in final else final.get("changed_files", [])
    additions = sum(item.get("additions", 0) or 0 for item in changed)
    deletions = sum(item.get("deletions", 0) or 0 for item in changed)
    task = meta.get("task") or "not recorded"
    branch = meta.get("git_branch") or "detached/no Git branch"
    base = (meta.get("base_commit") or "unknown")[:7]
    command_count = timeline.get("command_count", len(timeline.get("notable_commands", [])))
    test_count = len(timeline.get("test_executions", []))
    lines = [
        "## 🧾 Receipts — AI Session Trust Card",
        f'**Task:** "{task}"  ·  **Agent:** {meta.get("agent", "other")}  ·  **Session:** {_duration(meta.get("duration_seconds"))} · branch `{branch}` · base `{base}`',
        "",
        f"**What the agent actually did:** {command_count} commands · {len(changed)} agent-attributed files changed (+{additions} / −{deletions}) · {test_count} test runs",
        "",
        "| File | Verification |",
        "|---|---|",
    ]
    verification = analysis.get("verification", [])
    lines.extend(_verification_row(item) for item in verification)
    if not verification:
        lines.append("| _No changed source files detected_ | — |")
    preexisting = set(meta.get("preexisting_dirty_paths", []))
    if preexisting:
        changed_again = {
            item.get("path")
            for item in timeline.get("file_changes", [])
            if item.get("preexisting_at_start")
        }
        unchanged = len(preexisting - changed_again)
        boundary = (
            f"> **Attribution boundary:** {len(preexisting)} path(s) were already dirty when recording began; "
            f"{unchanged} remained unchanged and were excluded from agent-attributed counts, flags, and verification."
        )
        if changed_again:
            boundary += f" {len(changed_again)} changed again during this session and are labeled `pre-existing at start`."
        if final.get("preexisting_changes_removed"):
            boundary += f" {len(final['preexisting_changes_removed'])} pre-existing change(s) became clean during the session."
        lines.extend(["", boundary])
    flags: list[str] = []
    for item in analysis.get("scope_drift", []):
        flags.append(f'- 🔴 `{item["path"]}` changed — outside stated task scope (heuristic)')
    for item in analysis.get("risk_hints", []):
        flags.append(f'- ⚠️ Sensitive path touched: `{item["path"]}` ({item["reason"]})')
    for item in analysis.get("network_egress", []):
        flags.append(f'- ⚠️ Network egress observed: `{item["command"]}`')
    if flags:
        lines.extend(["", "**Flags**", *flags])
    integrity = manifest.get("integrity", {})
    digest = integrity.get("sha256", "unavailable")
    short_digest = f"{digest[:4]}…{digest[-4:]}" if len(digest) >= 8 else digest
    signing = "Ed25519 ✓" if integrity.get("signature") else "unsigned"
    session_id = meta.get("session_id", "session")
    lines.extend(["", f"Integrity: sha256 `{short_digest}` · {signing} · [▶ replay this session](session-{session_id}.html)"])
    return "\n".join(lines) + "\n"


def count_explicit_commands(transcript: str) -> int:
    """Count visible `set -x` commands, without pretending shell output is input."""
    count = 0
    for line in transcript.splitlines():
        if "] " in line:
            line = line.split("] ", 1)[1]
        if line.startswith("+ "):
            count += 1
    return count


def load_manifest(session: str | None, cwd: Path) -> tuple[Path, dict[str, Any]]:
    import json

    if session:
        candidate = Path(session)
        if not candidate.exists():
            session_id = session.removeprefix("session-").removesuffix(".json")
            candidate = cwd / ".receipts" / f"session-{session_id}.json"
    else:
        candidates = sorted((cwd / ".receipts").glob("session-*.json"), key=lambda path: path.stat().st_mtime)
        if not candidates:
            raise FileNotFoundError("no manifests found in .receipts")
        candidate = candidates[-1]
    return candidate, json.loads(candidate.read_text(encoding="utf-8"))
