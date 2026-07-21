"""Structural contract tests for the optional Receipts VS Code extension."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "vscode-receipts"


def test_vscode_extension_is_local_workspace_tool_without_runtime_dependencies():
    package = json.loads((EXTENSION / "package.json").read_text(encoding="utf-8"))

    assert package["name"] == "receipts-vscode"
    assert package["extensionKind"] == ["workspace"]
    assert package.get("dependencies", {}) == {}
    assert "receipts.sessions" in package["contributes"]["views"]["receipts"][0]["id"]
    commands = {command["command"] for command in package["contributes"]["commands"]}
    assert {"receipts.openWorkbench", "receipts.verify", "receipts.gate", "receipts.openReplay"} <= commands


def test_vscode_extension_uses_real_manifest_boundaries_and_safe_process_tasks():
    source = (EXTENSION / "extension.js").read_text(encoding="utf-8")
    model = (EXTENSION / "lib" / "receipt-model.js").read_text(encoding="utf-8")

    assert "schema_version !== 1" in model
    assert 'manifest.format === "receipts-public-feed/v1"' in model
    assert "agent_changed_files" in model
    assert "new vscode.ProcessExecution" in source
    assert ".sendText(" not in source
    assert "Not verified in VS Code" in source
    assert "fetch(" not in source
    assert "child_process" not in source


def test_vscode_extension_has_an_offline_installable_vsix_builder():
    builder = (ROOT / "tools" / "package_vscode_extension.py").read_text(encoding="utf-8")
    docs = (ROOT / "VSCODE_EXTENSION.md").read_text(encoding="utf-8")

    assert "zipfile.ZipFile" in builder
    assert "extension.vsixmanifest" in builder
    assert "VSIX verification: PASS" in builder
    assert "Install from VSIX" in docs
