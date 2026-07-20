"""Deterministic merge policy for evidence already present in a receipt."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GateFinding:
    """One changed file that the policy refuses to wave through."""

    path: str
    details: tuple[str, ...]


def _analysis_list(manifest: dict[str, Any], key: str) -> list[dict[str, Any]]:
    analysis = manifest.get("analysis")
    if not isinstance(analysis, dict):
        raise ValueError("manifest has no recorded analysis; re-record it with Receipts 0.1.0 or newer")
    value = analysis.get(key)
    if not isinstance(value, list):
        raise ValueError(f"manifest analysis is missing `{key}`")
    return [item for item in value if isinstance(item, dict)]


def evaluate_gate(manifest: dict[str, Any], *, sensitive_only: bool = False) -> list[GateFinding]:
    """Return files with no passing test observed after their final edit.

    This intentionally consumes the hash-protected analysis stored in the
    session manifest. It does not inspect the current checkout, re-run tests,
    or infer behavior from a diff.
    """
    verification = _analysis_list(manifest, "verification")
    risk_by_path = {str(item.get("path")): str(item.get("reason")) for item in _analysis_list(manifest, "risk_hints") if item.get("path")}
    scope_by_path = {str(item.get("path")): str(item.get("reason")) for item in _analysis_list(manifest, "scope_drift") if item.get("path")}
    findings: list[GateFinding] = []
    for item in verification:
        if item.get("status") != "never_executed":
            continue
        path = item.get("path")
        if not isinstance(path, str) or not path:
            continue
        sensitive_reason = risk_by_path.get(path)
        if sensitive_only and not sensitive_reason:
            continue
        details = ["no passing test was observed after the final edit"]
        if sensitive_reason:
            details.append(sensitive_reason)
        if path in scope_by_path:
            details.append("scope-drift heuristic")
        findings.append(GateFinding(path=path, details=tuple(details)))
    return findings


def render_gate(findings: list[GateFinding], integrity_message: str, *, sensitive_only: bool = False) -> str:
    """Render a small CI-friendly decision report without overstating certainty."""
    policy = "block sensitive changed source files with no passing test observed after their final edit" if sensitive_only else "block changed source files with no passing test observed after their final edit"
    lines = [f"Evidence gate: {'BLOCKED' if findings else 'PASS'}", f"Integrity: {integrity_message}", f"Policy: {policy}."]
    if findings:
        lines.append("")
        lines.extend(f"- {finding.path} — NEVER EXECUTED ({'; '.join(finding.details)})" for finding in findings)
        lines.append(f"\nResult: {len(findings)} blocking finding{'s' if len(findings) != 1 else ''}.")
    else:
        lines.append("\nResult: no blocking NEVER EXECUTED files under this policy.")
    return "\n".join(lines)
