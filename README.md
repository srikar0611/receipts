# 🧾 Receipts

**Every AI commit comes with receipts.**

Receipts is an open, agent-agnostic provenance layer for AI-generated code. It wraps a coding-agent terminal session, records the commands, changed files, and test evidence it can observe, then produces an integrity-protected review artifact. The headline finding is deliberately simple: **what did the agent write but never execute?**

See the deployed evidence dashboard at [receipts-demo](https://d2hw2ynyop1ius.cloudfront.net/). It first checks for the **latest published GitHub Actions demo receipt**, then safely falls back to a verified recorded sample. Run `receipts demo --live` to make a new full receipt on your own machine.

The dashboard is intentionally **interactive without a hosted application backend**: it recomputes the public projection's SHA-256 in the browser. The live feed contains only stable file aliases, verification statuses, counts, and relative timing; the raw local manifest, task, command line, source paths, Git metadata, and transcript are never uploaded. Static delivery keeps a full private replay portable; the captured session facts are the product.

## Judge quickstart — under 60 seconds

The recorded showcase needs no API key and makes no network request.

```bash
git clone <your-fork-url> receipts
cd receipts
python3 -m venv .venv
. .venv/bin/activate                 # Windows: use WSL; see below
python -m pip install .
receipts demo
```

You will see a Trust Card, a path to a local static replay HTML file, and a clearly labeled **sample output (generated with GPT-5.6)** review tour. The bundled manifest was recorded by actually wrapping [`tools/fake_agent.sh`](tools/fake_agent.sh), not written by hand.

### Fresh proof — not the bundled sample

Run this immediately after the quickstart (about 12 seconds):

```bash
receipts demo --live
```

This creates a retained Git repository under `.receipts/live-proofs/`, wraps a dependency-free deterministic agent through the same POSIX PTY recorder as `receipts run`, and emits a **new** session ID and SHA-256 every time. Its standard-library `unittest` test run is real; its billing edit is intentionally made after the final test. The command prints `Evidence gate: BLOCKED` as the expected proof that the policy caught the untested sensitive change, while `demo --live` itself exits successfully.

### Dirty-worktree proof — no false agent blame

```bash
receipts demo --live --dirty-baseline
```

This creates a fresh repository with an already-dirty `src/billing/legacy.py`, then records a separate login change and its test. The raw manifest retains the billing path as baseline evidence, but the Trust Card excludes it from agent counts, flags, verification, and the sensitive-only gate. The command ends with `Evidence gate: PASS`; that pass is the proof that Receipts did not falsely blame the agent for existing work.

To demonstrate the CI exit code separately, copy the printed manifest path:

```bash
receipts verify /path/to/.receipts/session-<id>.json
receipts gate /path/to/.receipts/session-<id>.json --sensitive-only
# exits 1: the demo's intentional billing change is NEVER EXECUTED
```

## 60-second pitch

Code review is drowning in agent output. Diff reviewers tell you what changed; enterprise firewalls tell you what policy allowed. Neither tells a reviewer the session facts: what the agent was asked, what it changed, what it ran, and whether it tested a file *after* editing it.

Receipts supplies that missing evidence. A reviewer gets one Trust Card and can replay the observed timeline. A changed billing file with no test after its last observed edit is not a hunch—it is a red `NEVER EXECUTED` receipt.

## Use it with any coding agent

```bash
# macOS/Linux/WSL
receipts run --task "fix the login redirect bug" -- codex "fix the login redirect bug"
receipts card
receipts replay
receipts verify session-<id>
receipts gate session-<id>
```

`run` accepts any executable: `codex`, `claude`, a shell script, or another coding agent. It records the exact argv and labels the executable as `codex`, `claude`, `cursor`, or `other`.

`replay` writes a single static HTML file beside the manifest and asks the system browser to open it. Use `--no-open` in CI/headless environments.

### Optional public live-feed projection

Never upload a raw `session-*.json` manifest to a public site. It may contain a task, working directory, full command line, Git identifiers, source paths, and transcript artifact names. Instead, verify it first and generate a separately hashed, alias-only projection:

```bash
receipts export-public /path/to/.receipts/session-<id>.json \
  --output public/latest.json \
  --replay-output public/latest.html \
  --publication-kind manual

receipts verify public/latest.json
```

The public object has no mapping from `file-001` aliases back to source paths. It preserves only the useful review facts: agent category, duration, counts, relative test/edit ordering, verification status, generic risk categories, and its own SHA-256. `export-public` refuses a source receipt whose integrity check fails.

### Optional signed receipts

All manifests carry a canonical SHA-256 hash. Ed25519 signing is optional and never required for the core flow:

```bash
python -m pip install cryptography
receipts keygen
receipts run --task "harden auth" -- codex "harden auth"
receipts verify session-<id>
```

`keygen` writes project-local keys under `.receipts/keys/`; the private key is not committed by the provided `.gitignore`.

### Optional GPT review tour

Without an API key, `receipts tour` prints the bundled sample. With `OPENAI_API_KEY`, it uses the Responses API for a risk-ranked tour. The core recorder, verifier, card, replay, and demo are all offline. The live request sets `store: false`; live API availability and model access remain account-dependent.

## What a session records

```mermaid
flowchart LR
  A[Agent terminal command] --> B[POSIX PTY wrapper]
  B --> C[Timestamped raw + ANSI-stripped transcripts]
  B --> D[Git status poller every 2 seconds]
  C --> E[Test + notable command parser]
  D --> F[File observations + final diff]
  E --> G[Deterministic analysis]
  F --> G
  G --> H[Canonical SHA-256 / optional Ed25519]
  H --> I[Manifest · Trust Card · Replay · PR comment]
```

Each `.receipts/session-<id>.json` contains:

- session metadata: timestamps, cwd, full argv, agent label, branch, base commit, task;
- Git snapshots, the dirty-worktree baseline, and per-file first/last observed changes;
- parsed test invocations and results for pytest, Python unittest, Jest, Vitest, Go, Cargo, npm/pnpm/yarn, and Make;
- notable Git, package-install, and `curl`/`wget` commands;
- the full final diff against the starting commit **and** the net agent-attributed delta from session start, analysis, hash, and optional signature.

## Deterministic review signals

| Signal | Evidence rule |
|---|---|
| ✅ verified | A convention-mapped test passed after the file’s last observed edit. |
| 🟡 indirectly exercised | Some passing suite ran after the last observed edit, but no mapped test was seen. |
| 🔴 NEVER EXECUTED | No passing test was observed after the file’s last observed edit. |
| Scope drift | Heuristic token mismatch between task and changed source path. |
| Risk hint | Sensitive path, dependency/project manifest, migration, workflow, environment file, or observed network egress. |

## GitHub Action

The composite Action finds the newest manifest and creates or updates one sticky PR comment marked `<!-- receipts-trust-card -->`.

```yaml
- uses: your-org/receipts/action@v0
  with:
    github-token: ${{ secrets.GITHUB_TOKEN }}
```

See [`examples/receipts-pr.yml`](examples/receipts-pr.yml). The action’s POST and PATCH behavior is covered by an offline mocked-API test.

To make the receipt an enforceable merge check, keep the sticky comment and add the optional gate:

```yaml
- uses: your-org/receipts/action@v0
  with:
    github-token: ${{ secrets.GITHUB_TOKEN }}
    enforce: true
    enforce-sensitive-only: true
```

The Action posts/updates the Trust Card first, then fails the job when a **sensitive** changed source file is recorded as `NEVER EXECUTED`. This is a narrow evidence policy, not a claim that all other changes are safe or behaviorally covered.

## Optional: public AWS demo

Receipts does not need a cloud backend. If you want a judge-ready public link, AWS deploys the curated static `docs/` site through a private S3 bucket and CloudFront HTTPS. The S3 origin remains private; GitHub Actions receives short-lived AWS credentials through an exact-subject OIDC role, rather than stored AWS access keys.

M11 adds an optional **manual live-feed publisher**. On `master`, [`.github/workflows/publish-live-evidence.yml`](.github/workflows/publish-live-evidence.yml) records a fresh synthetic PTY proof on a trusted GitHub runner, verifies the private source manifest, creates an alias-only public projection, verifies that projection, then writes only `live/latest.json` and `live/latest.html`. A separate AWS role has `PutObject` permission for exactly those two keys; the normal site deploy role is explicitly denied access to `live/*`. CloudFront disables caching for that prefix, so each feed view fetches the latest object.

The full cost-guardrail, CloudFormation update, GitHub OIDC variables, verification, and cleanup guide is in [`AWS_DEPLOY.md`](AWS_DEPLOY.md). Do not deploy raw `.receipts/` content or user session data to this public showcase.

## Comparison

| Approach | Primary question | What Receipts adds |
|---|---|---|
| Diff re-reviewers (e.g. CodeRabbit) | “What looks wrong in this diff?” | Session facts: commands, test ordering, and unexecuted changes. |
| Enterprise agent firewalls (e.g. LlamaFirewall, Aegis) | “Should this agent action be allowed?” | Post-session reviewer evidence, independent of agent vendor. |
| Session attach tools (e.g. Warp) | “How do I work in this terminal now?” | A durable, tamper-evident receipt attached to the resulting change. |

## Honest limitations

- **macOS/Linux/WSL only.** Receipts uses stdlib `pty`; Windows-native support is intentionally out of scope. Run it in WSL on Windows.
- **Polling observes, not omniscience.** File times are observed at a two-second Git-poll cadence, not editor-save timestamps.
- **Dirty worktrees have an attribution boundary.** Receipts snapshots existing Git changes before launching the agent. Paths that remain unchanged are retained as baseline evidence but excluded from agent counts, flags, and verification. A pre-existing path that changes again is labeled rather than assumed to be wholly agent-authored.
- **Transcript parsing is conservative.** If a runner command or result cannot be identified confidently, it is marked `unparsed`, never guessed.
- **Verification is convention-based.** Mapping covers `test_x.py ↔ x.py`, `x.test.ts`/`x.spec.ts ↔ x.ts`, and `x_test.go ↔ x.go`; indirect coverage is not a proof of behavioral coverage.
- **Scope drift is a heuristic.** It uses task/path tokens with a small `login ↔ auth` alias, and must be read as a prompt for review—not an authorization decision.
- **Integrity proves manifest mutation, not every external fact.** Hashing makes later manifest edits detectable; it cannot prove an unobserved process or side effect never occurred.
- **The evidence gate is deliberately narrow.** It blocks changed files with no passing test observed after their final edit; `--sensitive-only` limits that further to recorded sensitive-path hints. It does not prove correctness or replace human review.
- **Live tour is optional.** No key means no network call and a labeled bundled sample; the live API branch is not exercised by the offline demo.
- **The public live feed is curated, not SaaS.** It is a latest-published static object for the trusted GitHub Actions synthetic demo, not a multi-tenant service or a terminal stream. It deliberately aliases paths and withholds raw receipt data. For a real project, publish only after explicit review and consent.

## How Codex & GPT-5.6 built this

We worked milestone by milestone and committed each one separately:

1. **Capture core:** GPT-5.6 chose a POSIX PTY plus Git snapshot model so the receipt retains raw evidence and a compact per-file summary. A real fake-agent recording exposed Git’s untracked-directory collapse, which we fixed using `--untracked-files=all` rather than guessing file contents.
2. **Deterministic analysis:** GPT-5.6 designed the three-tier verification gap and conservative parser fixtures. A real PTY transcript exposed timestamp injection around pytest progress; the parser was fixed against the ANSI-stripped transcript and regression-tested.
3. **Reviewer artifacts:** GPT-5.6 rendered the card from recorded facts only and made sticky-comment create/update logic mockable without calling GitHub.
4. **Demo:** GPT-5.6 analyzed the real dogfooded session to write the sample tour. It deliberately labels the output as generated with GPT-5.6, rather than pretending an offline call was live.
5. **Public demo (optional):** GPT-5.6 kept the live showcase separate from the product's core. It deploys only the curated static demo through private S3, CloudFront HTTPS, and a least-privilege GitHub OIDC role—no server, database, or long-lived AWS key.
6. **Attribution boundary:** GPT-5.6 separated the raw worktree diff from the net session delta. This prevents a dirty developer checkout from being silently credited to the agent while preserving it as inspectable baseline evidence.
7. **Live public evidence:** GPT-5.6 separated the public feed from the raw receipt. The publisher verifies a fresh PTY-generated source receipt first, creates a separately hashed alias-only projection, and uses a distinct prefix-scoped AWS OIDC role to publish just the latest projection and safe replay.

The full chronological decision record is in [`BUILDLOG.md`](BUILDLOG.md).

## Development

```bash
python -m pip install pytest
python -m pytest -q
```

The current suite covers transcript fixtures, verification analysis, integrity/tamper checks, Trust Card rendering, mocked Action create/update behavior, replay embedding, tour fallback, and the offline demo.
