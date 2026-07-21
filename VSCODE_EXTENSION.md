# VS Code judge quickstart

Receipts includes an optional local VS Code extension: **Receipts — AI
Evidence**. It is a developer-tool surface for inspecting the exact evidence
recorded by the CLI without uploading a raw receipt.

    python tools/package_vscode_extension.py

Then install dist/receipts-vscode-0.1.0.vsix from the VS Code Command Palette
using **Extensions: Install from VSIX...**.

Open a repository with .receipts/session-*.json, select the Receipts icon in
the Activity Bar, and open an Evidence Workbench. For a deterministic
five-minute walkthrough:

    receipts demo --live

The extension will discover the fresh manifest under .receipts/live-proofs/.
It renders actual local file paths and stored verification states, resolves
those paths against the captured workspace only when that workspace remains
inside the folder you opened, and sends verification or sensitive-only gate
commands only to a visible VS Code task.

It works on desktop VS Code and Remote - WSL. It does not run in browser-only
VS Code because the raw receipt is deliberately local.
