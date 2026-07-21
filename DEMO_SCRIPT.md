# Receipts demo video script (2:59)

## 0:00–0:18 — Start with fresh proof

In a clean WSL/macOS/Linux terminal, run:

```bash
python -m pip install .
receipts demo --live
```

Say: “This is not replaying the website’s sample. Receipts just created a fresh Git repository, wrapped an agent in a real PTY, and recorded a new session.” Point to the newly printed workspace, manifest path, and `Integrity: OK` line.

If asked about a developer's already-dirty checkout, say: “Receipts takes a baseline before launching the agent. Unchanged baseline paths stay inspectable in the raw receipt, but are excluded from agent-attributed counts, flags, verification, and the gate. If the agent changes one again, the replay labels it `pre-existing at start`.”

For a live proof, run `receipts demo --live --dirty-baseline`. It deliberately starts with a dirty `src/billing/legacy.py`, then records a different agent edit. Point to the Trust Card’s **Attribution boundary** and the expected `Evidence gate: PASS`: the sensitive billing path is preserved as raw baseline evidence, but Receipts does not blame the agent for it.

## 0:18–0:38 — Let the policy stop the bad change

Point to the final `Evidence gate: BLOCKED` section. Say: “The command itself succeeded—the block is the result we wanted. The agent changed a sensitive billing file after its final passing test. Receipts did not guess that it was unsafe; it observed that no test ran afterward.”

Copy the manifest path and show the real CI exit code:

```bash
receipts verify /path/to/.receipts/session-<id>.json
receipts gate /path/to/.receipts/session-<id>.json --sensitive-only
echo $?
```

Explain that `1` means the merge policy would block, while the sticky card still gives the reviewer the facts.

## 0:38–1:05 — Show tamper resistance

Open the live proof’s replay path. Click **Verify in browser** to show `sha256 verified in this browser`. Then click **Test hash resistance**. The viewer alters only an in-memory demo copy, immediately shows `sha256 mismatch`, and offers **Reset recorded receipt**.

Say: “The viewer has no server and no upload endpoint. The receipt carries its own evidence, and a later edit is detectable.”

## 1:05–1:28 — Read the Trust Card

Return to the printed card and read the three rows quickly:

- `src/auth/login.py` is directly verified by its convention-mapped test.
- `src/auth/session.py` is only indirectly exercised.
- `src/billing/invoice.py` is red: it changed after the final test, so it was never executed.

Point to the scope-drift and sensitive-path flags. Emphasize that scope drift is labeled as a heuristic.

## 1:28–1:39 — VS Code evidence workbench

In desktop VS Code or Remote-WSL, open the **Receipts** Activity Bar view and select the fresh local session. Click the red billing file to open the real workspace source, then select **Run CLI verification**.

Say: “This is a developer tool, not a hosted mock-up. It reads the full local receipt from this workspace and sends verification through a visible VS Code task. The raw transcript and paths never leave the machine.”

## 1:39–2:06 — The live public evidence workbench

Open the deployed page. If the M11 publisher has run, point to the **LIVE PUBLISHED** badge and the fresh public receipt ID. Say: “This dashboard is not a raw manifest in a browser. GitHub Actions made a fresh PTY receipt, verified it, and published a separately hashed projection with aliases instead of paths, commands, task text, or a transcript.”

Open the forensic replay. Show `file-003` as **NEVER EXECUTED**, click **Verify projection hash**, and point out that the event timing is relative. Say: “The public page is live data, but the sensitive local evidence stays local.”

If no live publication is present, say: “The dashboard is safely showing its verified alias-only fallback. The same trusted workflow can publish a new one from the Actions tab; it never uploads a raw receipt.”

## 2:06–2:29 — Real pull-request enforcement

Show this Action configuration:

```yaml
- uses: your-org/receipts/action@v0
  with:
    github-token: ${{ secrets.GITHUB_TOKEN }}
    enforce: true
    enforce-sensitive-only: true
```

Say: “The Action posts or updates the Trust Card first, then makes a sensitive `NEVER EXECUTED` finding fail the job. That is a review policy built from the agent’s recorded session facts—not another LLM opinion about the diff.”

## 2:29–2:44 — Optional GPT review tour

Run `receipts tour` or point to the demo output. Say: “Without a key, this is explicitly labeled sample output generated with GPT-5.6. With a key, it can provide a risk-ranked review tour. Capture, hash verification, replay, and the evidence gate stay offline.”

## 2:44–2:59 — Close

“Receipts is agent-agnostic evidence over vibes. Before merging AI code, know what it wrote, what it ran, what it never executed—and enforce that fact when it matters.”
