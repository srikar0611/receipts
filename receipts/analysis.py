"""Conservative, offline analysis of recorded Receipts manifests."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any


TEST_COMMAND_RE = re.compile(
    r"(?:^|\s)(?:python(?:3)?\s+-m\s+)?(pytest|unittest|jest|vitest|go\s+test|cargo\s+test|npm\s+(?:run\s+)?test|pnpm\s+(?:run\s+)?test|yarn\s+test|make\s+test)(?:\s|$)",
    re.IGNORECASE,
)
PROMPT_RE = re.compile(r"^(?:\$|\+|#|>|PS\s+[^>]+>)\s*")
TIMESTAMP_RE = re.compile(r"^\[([^\]]+)\]\s?")
TOKEN_RE = re.compile(r"[a-z0-9]{2,}")


def parse_test_executions(transcript: str) -> list[dict[str, str]]:
    """Parse only clear runner invocations and summaries; otherwise say unparsed."""
    events: list[dict[str, str]] = []
    pending: dict[str, str] | None = None
    last_timestamp = "unparsed"
    for raw_line in transcript.splitlines():
        timestamp_match = TIMESTAMP_RE.match(raw_line)
        if timestamp_match:
            last_timestamp = timestamp_match.group(1)
            raw_line = raw_line[timestamp_match.end():]
        line = PROMPT_RE.sub("", raw_line).strip()
        if not line:
            continue
        if TEST_COMMAND_RE.search(line):
            if pending:
                events.append(pending)
            pending = {"timestamp": last_timestamp, "command": line, "result": "unparsed", "summary": ""}
            continue
        if pending:
            result = result_from_summary(line)
            if result:
                pending["result"] = result
                pending["summary"] = line
                events.append(pending)
                pending = None
    if pending:
        events.append(pending)
    return events


def result_from_summary(line: str) -> str | None:
    lower = line.lower()
    if re.search(r"\b(?:\d+\s+failed|failures?:|fail\s+\S+|test result:\s+failed)\b", lower):
        return "failed"
    # Python's standard-library unittest runner prints a bare ``OK`` after its
    # summary. It is explicit runner output, so it is safe to record as passed.
    if lower == "ok":
        return "passed"
    if re.search(r"\b(?:\d+\s+passed|tests:\s+.*\bpassed\b|pass\s+\S+|ok\s+\S+|test result:\s+ok)\b", lower):
        return "passed"
    return None


def parse_notable_commands(transcript: str) -> list[dict[str, str | bool]]:
    """Record explicit, visible command lines only; no shell-output inference."""
    events: list[dict[str, str | bool]] = []
    timestamp = "unparsed"
    for raw_line in transcript.splitlines():
        match = TIMESTAMP_RE.match(raw_line)
        if match:
            timestamp = match.group(1)
            raw_line = raw_line[match.end():]
        command = PROMPT_RE.sub("", raw_line).strip()
        kind = ""
        if re.match(r"git\s+", command):
            kind = "git"
        elif re.search(r"\b(?:pip|pip3|npm|pnpm|yarn|cargo)\s+(?:install|add)\b", command):
            kind = "package_install"
        elif re.match(r"(?:curl|wget)\s+", command):
            kind = "network_egress"
        if kind:
            events.append({"timestamp": timestamp, "command": command, "kind": kind, "network_egress": kind == "network_egress"})
    return events


def _time(value: str) -> datetime | None:
    if value == "unparsed":
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def is_source_file(path: str) -> bool:
    pure = PurePosixPath(path)
    name = pure.name.lower()
    if "__pycache__" in pure.parts or name.endswith((".pyc", ".pyo")):
        return False
    if any(part.lower() in {"test", "tests", "__tests__"} for part in pure.parts):
        return False
    if re.match(r"test_.*\.py$", name) or re.search(r"\.(test|spec)\.[jt]sx?$", name) or name.endswith("_test.go"):
        return False
    return pure.suffix.lower() in {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java"}


def mapped_test_names(path: str) -> set[str]:
    name = PurePosixPath(path).name
    if name.endswith(".py"):
        return {f"test_{name}"}
    if name.endswith((".ts", ".tsx", ".js", ".jsx")):
        stem, suffix = name.rsplit(".", 1)
        return {f"{stem}.test.{suffix}", f"{stem}.spec.{suffix}"}
    if name.endswith(".go"):
        return {f"{name[:-3]}_test.go"}
    return set()


def test_is_mapped_to(path: str, command: str) -> bool:
    command_files = {PurePosixPath(token).name for token in re.findall(r"[\w./-]+\.(?:py|[jt]sx?|go)", command)}
    return bool(mapped_test_names(path) & command_files)


def agent_changed_files(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Return net session changes, retaining compatibility with older receipts.

    Presence matters here: an explicit empty list proves that a dirty starting
    worktree produced no net agent-attributed change. Do not use ``or`` as a
    fallback, because that would reintroduce pre-existing files into policy.
    """
    final = manifest.get("final", {})
    if "agent_changed_files" in final:
        return final["agent_changed_files"]
    return final.get("changed_files", [])


def agent_file_changes(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Return timeline changes that remain in the session's final delta."""
    changed = manifest.get("timeline", {}).get("file_changes", [])
    final = manifest.get("final", {})
    if "agent_changed_files" not in final:
        return changed
    paths = {item["path"] for item in agent_changed_files(manifest)}
    return [item for item in changed if item.get("path") in paths]


def verification_gap(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    tests = manifest.get("timeline", {}).get("test_executions", [])
    changed = agent_file_changes(manifest)
    result: list[dict[str, Any]] = []
    for change in changed:
        path = change["path"]
        if not is_source_file(path):
            continue
        changed_at = _time(change.get("last_modified_observed_at", "unparsed"))
        # An unknown timestamp cannot prove ordering. Treat it as insufficient
        # evidence rather than upgrading a file's verification state.
        later_passes = [
            event for event in tests
            if event.get("result") == "passed"
            and changed_at is not None
            and (event_time := _time(event.get("timestamp", "unparsed"))) is not None
            and event_time >= changed_at
        ]
        mapped = [event for event in later_passes if test_is_mapped_to(path, event.get("command", ""))]
        attribution = {"preexisting_at_start": True} if change.get("preexisting_at_start") else {}
        if mapped:
            event = mapped[-1]
            result.append({"path": path, "status": "verified", "test_command": event["command"], "test_timestamp": event["timestamp"], **attribution})
        elif later_passes:
            event = later_passes[-1]
            result.append({"path": path, "status": "indirectly_exercised", "test_command": event["command"], "test_timestamp": event["timestamp"], **attribution})
        else:
            result.append({"path": path, "status": "never_executed", "test_command": "", "test_timestamp": "", **attribution})
    return result


STOPWORDS = {"the", "a", "an", "fix", "bug", "issue", "please", "for", "with", "and", "this", "that"}
TASK_ALIASES = {"login": {"auth", "authentication"}, "auth": {"login", "authentication"}, "authentication": {"auth", "login"}}


def task_tokens(task: str | None) -> set[str]:
    tokens = {token for token in TOKEN_RE.findall((task or "").lower()) if token not in STOPWORDS}
    for token in list(tokens):
        tokens.update(TASK_ALIASES.get(token, set()))
    return tokens


def scope_drift(manifest: dict[str, Any]) -> list[dict[str, str]]:
    tokens = task_tokens(manifest.get("meta", {}).get("task"))
    if not tokens:
        return []
    flags: list[dict[str, str]] = []
    for item in agent_changed_files(manifest):
        path = item["path"]
        if not is_source_file(path):
            continue
        path_tokens = set(TOKEN_RE.findall(path.lower()))
        if not tokens & path_tokens:
            flags.append({"path": path, "reason": "heuristic: path has no token overlap with stated task"})
    return flags


def sensitive_paths(manifest: dict[str, Any]) -> list[dict[str, str]]:
    flags: list[dict[str, str]] = []
    for item in agent_changed_files(manifest):
        path = item["path"]
        parts = [part.lower() for part in PurePosixPath(path).parts]
        name = parts[-1] if parts else ""
        if "__pycache__" in parts or name.endswith((".pyc", ".pyo")):
            continue
        reason = ""
        if any(part.startswith("auth") for part in parts):
            reason = "sensitive auth path"
        elif any(part.startswith("billing") for part in parts):
            reason = "sensitive billing path"
        elif "migrations" in parts:
            reason = "migration path"
        elif name.startswith(".env"):
            reason = "environment file"
        elif ".github" in parts and "workflows" in parts:
            reason = "GitHub workflow"
        elif name in {"package.json", "pyproject.toml"} or name.endswith((".lock", "lock.json")):
            reason = "dependency or project manifest"
        if reason:
            flags.append({"path": path, "reason": reason})
    return flags


def analyze_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    notable = manifest.get("timeline", {}).get("notable_commands", [])
    return {
        "verification": verification_gap(manifest),
        "scope_drift": scope_drift(manifest),
        "risk_hints": sensitive_paths(manifest),
        "network_egress": [event for event in notable if event.get("network_egress")],
    }
