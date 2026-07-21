# Receipts for VS Code

Receipts for VS Code is a local Evidence Workbench for real AI coding-session
manifests. It reads .receipts/session-*.json in the opened workspace and
renders the recorded Trust Card directly beside the code under review.

It is intentionally not a cloud service:

- no network calls, account, telemetry, or API key;
- no code, commands, task text, transcripts, or paths leave the workspace;
- it displays stored verification evidence and flags rather than guessing; and
- integrity verification and gating run through the user's visible local
  Receipts command in an integrated terminal.

## Install in under a minute

From the Receipts repository root:

    python tools/package_vscode_extension.py

In desktop VS Code or VS Code Remote - WSL:

1. Open the Command Palette with Ctrl+Shift+P.
2. Select **Extensions: Install from VSIX...**.
3. Choose dist/receipts-vscode-0.1.0.vsix.
4. Open the repository you recorded in VS Code.
5. Select the **Receipts** icon in the Activity Bar.

For a fresh local receipt to inspect:

    receipts demo --live

Then select **Receipts: Refresh Local Evidence** from the Command Palette.

## What you can do

- Open the dark, interactive **Evidence Workbench** for the latest recorded
  manifest.
- Inspect each changed file's exact verified, indirectly exercised,
  NEVER EXECUTED, or unparsed status.
- Open a changed workspace file by clicking its evidence row.
- Run the actual Receipts verify and sensitive-only evidence-gate commands in
  an integrated terminal.
- Open an adjacent replay; when it does not exist, generate it visibly with
  the local CLI.

The sidebar includes an honest empty state when no manifest exists and a
malformed-receipt state when JSON cannot be parsed.

## Requirements and scope

- Desktop VS Code 1.85+ or VS Code Remote - WSL.
- A local Receipts CLI if you use Verify, Gate, or replay generation.
- No runtime npm dependencies.

The extension runs in the workspace extension host. It does not support
browser-only vscode.dev, because that environment cannot access the same
local workspace and terminal evidence.

If Receipts is not on VS Code's PATH, set receipts.command to its absolute
executable path in VS Code Settings.

## Development checks

    cd vscode-receipts
    node --test
    node --check extension.js
    cd ..
    python tools/package_vscode_extension.py --verify

The model tests use fixtures rather than a network service. They verify that
the extension prefers agent-attributed files, preserves unparsed rather than
inventing a status, and prevents a receipt path from escaping the workspace.
