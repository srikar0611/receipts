# Receipts build log

## 2026-07-19 — M1 capture-core start

- **Request:** Build the first milestone of Receipts: an offline, agent-agnostic session recorder.
- **Decision:** Use only Python stdlib (`pty`, `selectors`, `subprocess`, `hashlib`) for capture. The package will be POSIX-only at runtime and explicitly direct Windows users to WSL.
- **Why:** A terminal recording tool needs a real PTY to preserve the agent session; stdlib `pty` is reliable on macOS/Linux and avoids a native dependency.
- **Evidence boundary:** Polling timestamps are observations at a two-second cadence, not claims of an exact editor-save instant. The manifest labels them as observed timestamps.
- **GPT-5.6 reasoning contribution:** Chose a snapshot-plus-per-file summary so reviewers can inspect both raw observation history and the simple facts used later by deterministic analysis.
- **Refinement:** Track a per-file observed content/diff hash, rather than treating every dirty `git status` poll as a new edit. This preserves the distinction between a file that stayed dirty and a file that changed again.
- **Development environment:** WSL needed the distro's `python3.12-venv` package before an isolated development environment could be created. This is a local development prerequisite only; Receipts itself retains no runtime dependency beyond the stdlib.
- **Acceptance finding:** The first real fake-agent run captured test executions but Git's default porcelain output collapsed untracked directories. Switched to `--untracked-files=all` so manifests name observed files exactly; no heuristic expansion is used.
- **M1 acceptance proof:** A fresh temporary Git repository was recorded with `receipts run --task "fix the login bug" -- sh tools/fake_agent.sh`. Session `20260719T174301Z-10e44a2c` captured `src/auth/login.py`, `src/auth/session.py`, and `src/billing/invoice.py`, plus two passing pytest executions with parsed timestamps. The asserted capture acceptance passed.
- **Forward note:** Pytest creates `__pycache__` files in the fake repository. M2's changed-*source*-file analysis will explicitly exclude generated cache paths rather than silently treating them as source.

## 2026-07-19 — M2 deterministic analysis start

- **Request:** Add offline verification-gap, scope/risk analysis, integrity, and test parsing.
- **Decision:** Analysis only promotes evidence directly present in the manifest/transcript. Unknown timestamps and runner output remain `unparsed`; no inferred test pass is fabricated.
- **Decision:** Scope drift is explicitly heuristic. `login` and `auth` are treated as transparent aliases so auth/session edits are not falsely characterized as unrelated to a login task; billing remains outside that scope.
- **Decision:** Hash every canonical manifest body. Only sign automatically when a project-local `.receipts/keys/ed25519-private.pem` exists; cryptography stays optional.
- **Test proof:** Six offline pytest tests passed, covering pytest/Jest/Go parser fixtures, incomplete output, timestamped progress, verification tiers, scope/risk hints, notable commands, and tamper detection.
- **Acceptance proof:** A fresh fake-agent session yielded `verified` for `src/auth/login.py`, `indirectly_exercised` for `src/auth/session.py`, and `never_executed` for `src/billing/invoice.py`. It had exactly one heuristic scope-drift flag (`src/billing/invoice.py`) and `receipts verify` returned `OK: sha256 verified (unsigned)`.
- **Optional dependency proof:** Without cryptography installed, `receipts keygen` fails safely and explicitly instructs `pip install cryptography`; core hashing and verification remain usable offline.

## 2026-07-19 — M3 Trust Card and Action start

- **Request:** Render reviewer-facing Trust Cards and create a sticky PR-comment Action.
- **Decision:** The card presents only recorded manifest facts and uses the M2 statuses verbatim. It never re-evaluates a diff or asks a model for a conclusion.
- **Decision:** The composite Action has no Node or third-party dependency. Its shell poster can inject a `curl` binary, so the POST/PATCH decision is locally testable without a GitHub request.
- **Test isolation:** The root pytest configuration collects only Receipts' own `tests/` directory. The walkthrough sample is intentionally a separate mini-project, not part of the package test suite.
- **Acceptance proof:** A fresh recorded session rendered the Trust Card with 11 visible commands, 6 changed files, two test runs, and the expected verified / indirect / NEVER EXECUTED rows. The card also displayed one scope flag, sensitive-path flags, and its truncated SHA-256 receipt.
- **Action proof:** Nine tests passed. The local Action test injected a mock curl binary and asserted both `POST /issues/42/comments` (first comment) and `PATCH /issues/42/comments/99` (sticky update); no GitHub network request was made.

## 2026-07-19 — M4 replay, tour, and demo start

- **Request:** Create a replay, a GPT-5.6 review tour with offline fallback, and a zero-setup demo.
- **Decision:** Replay is a single local HTML file with the manifest embedded as JSON and client-side rendering only. It works without a server, build step, or network access.
- **Decision:** `tour` uses the Responses endpoint only when `OPENAI_API_KEY` exists. It sends `store: false`; otherwise (or on an API failure) it labels and prints a bundled GPT-5.6 sample rather than fabricating a live result.
- **GPT-5.6 reasoning contribution:** Wrote the bundled tour by analyzing the real fake-agent evidence pattern: billing is unexecuted and scope-drifted; session has only indirect coverage; login has direct focused coverage.
- **Dogfood proof:** `receipts run` wrapped `tools/fake_agent.sh` in a fresh Git repo and produced the bundled sample manifest and transcript. Offline `receipts demo` verified the manifest hash, printed the card, wrote `sample-replay.html`, and printed the labeled sample tour. Demo deliberately does not launch a browser, avoiding WSL/headless launcher noise; `receipts replay` retains that behavior.
- **Acceptance proof:** Twelve offline tests passed. With `OPENAI_API_KEY` explicitly unset, the demo produced the expected verified / indirect / NEVER EXECUTED card rows, replay path, and sample tour; no network operation occurred.
- **Live-tour limitation:** The stdlib Responses API path is implemented with `store: false`, but it is intentionally untested here because no API credits/key are available. Any live request error falls back to the explicitly labeled sample rather than failing the core workflow.

## 2026-07-20 — M5 ship materials start

- **Request:** Ship README, demo script, Pages artifact, and clean-clone proof.
- **Decision:** Judge quickstart begins with `receipts demo`, not agent capture, because it proves the thesis without credentials, setup, or network access.
- **Decision:** Documentation states heuristic and observation boundaries alongside the pitch. The demo is compelling only if reviewers can see where certainty ends.
- **Clean-clone proof:** On 2026-07-20, a fresh `git clone` into `/tmp/tmp.aQziKCoigA/receipts` created a new venv, completed `python -m pip install .` by building `receipts-0.1.0-py3-none-any.whl`, and ran `env -u OPENAI_API_KEY receipts demo` successfully. The installed wheel included the bundled manifest and sample tour, wrote `sample-replay.html`, and made no API request.

## 2026-07-20 — M6 AWS public-demo launch start

- **Request:** Use AWS credits to make Receipts more judge-visible without turning the offline-first CLI into a hosted platform.
- **Decision:** Publish only the curated `docs/` artifacts through a private S3 bucket behind CloudFront HTTPS. The product recorder, verifier, card, replay, and bundled demo remain local and require no AWS account at runtime.
- **Security decision:** Use GitHub Actions OIDC with a least-privilege role instead of long-lived AWS access keys. The template requires the exact GitHub OIDC `sub` claim as an input, so a different repository or branch cannot assume the role by accident.
- **Current GitHub caveat:** Repositories created after 15 July 2026 can use immutable OIDC subjects containing owner and repository IDs. The deployment guide makes this explicit rather than assuming the older `repo:owner/repo` format.
- **Cost decision:** No EC2, RDS, NAT Gateway, ECS, database, or model endpoint. A $5 monthly budget and forecast alerts are the first setup step; AWS billing alerts are monitoring, not an instant circuit breaker.
- **GPT-5.6 reasoning contribution:** Chose a private-origin static showcase because it gives judges a public HTTPS replay while preserving the central claim that Receipts works with zero runtime network dependency.
- **Acceptance proof:** The expanded offline suite passed on the attached WSL environment: `14 passed in 2.61s`. The M6 structural test verifies public S3 access blocking, OAC-only origin configuration, HTTPS redirect, an exact OIDC subject condition, and the absence of long-lived AWS credential variables in the deployment workflow. JSON syntax and the same security invariants were also checked locally before the WSL run.
- **Deployment boundary:** No AWS resource was created while building M6. The user must intentionally run the documented CloudFormation deployment after checking their credit terms and creating cost alerts; live CloudFront validation belongs to that account-scoped setup.

## 2026-07-20 — M7 public-demo experience start

- **Request:** The deployed page looked like a sparse placeholder rather than a convincing product experience for judges.
- **Decision:** Replace the single-link splash with a responsive, dependency-free evidence-first landing page. Its focal point is the recorded Trust Snapshot, followed by the concrete Trust Card, workflow, and replay path.
- **Evidence discipline:** Every metric and verification label shown on the page comes from the bundled real sample manifest: 11 commands, 6 changed files, 2 passing pytest runs, and one `src/billing/invoice.py` `NEVER EXECUTED` gap. No synthetic risk score or fictional telemetry was added.
- **UX decision:** Use a high-contrast dark developer-tool surface with structured panels, cyan only for actions/evidence, and red only for the observed verification gap. The page has no fonts, scripts, analytics, or runtime dependencies.
- **GPT-5.6 reasoning contribution:** Center the reviewer’s first question—“what did the agent not prove?”—instead of burying the differentiator behind a generic marketing hero.

## 2026-07-20 — M8 interactive evidence workbench start

- **Request:** The public page was visually improved but still felt like a passive static brochure; the replay needed to demonstrate product capability rather than merely display a report.
- **Decision:** Treat static HTML as the portable delivery container, not the interaction model. The landing page now reads a published, real sample manifest and independently computes its SHA-256 in the browser. The replay renderer becomes a single-file forensic workbench with filtering, timeline scrubbing, event inspection, local receipt loading, manifest download, and browser-side integrity checking.
- **Evidence discipline:** The published JSON is a semantic copy of the bundled real recorded manifest and is tested against its SHA-256. The key red finding is calculated from timestamps: `src/billing/invoice.py` was observed 3.3 seconds after the final passing pytest run, with no later test execution recorded.
- **Privacy decision:** “Load another receipt” uses only the browser File API. There is no upload endpoint, account, server-side parser, or telemetry.
- **GPT-5.6 reasoning contribution:** Reframed the jury question: a portable artifact is stronger when it can be independently inspected and verified without a service that could modify the evidence after capture.

## 2026-07-20 — M9 fresh proof and evidence gate start

- **Request:** Move beyond a polished recorded sample and prove that Receipts can generate new evidence and enforce it, so a jury cannot reasonably dismiss the product as hardcoded HTML.
- **Decision:** Add `receipts demo --live`, which creates a retained temporary Git repository under `.receipts/live-proofs/` and calls the existing `capture()` PTY path. It does not construct a manifest by hand: Git polling, transcript parsing, deterministic analysis, integrity hashing, and replay generation all run again for each invocation.
- **Zero-setup decision:** The live fixture uses the Python standard-library `unittest` runner, and the conservative parser now recognizes its explicit `OK` result. This keeps the fresh proof offline after `pip install .`; no runtime `pytest` download, API call, or AWS service is required.
- **Policy decision:** Add `receipts gate`, which verifies the manifest hash/signature before consuming its recorded analysis. It blocks changed files marked `NEVER EXECUTED`; `--sensitive-only` limits the policy to the manifest's own sensitive-path hints. A mismatch blocks before policy evaluation.
- **Action decision:** The composite Action posts/updates the sticky Trust Card before optional enforcement, so a blocked job still leaves reviewers with the observed evidence. Enforcement is opt-in and sensitive-only by default to keep the policy honest and focused.
- **Tamper-demo decision:** The replay's hash-resistance control alters only an in-memory clone, labels it `DEMO ONLY`, proves the hash mismatch in the browser, and lets the viewer reset the original embedded receipt. No upload, network request, or production evidence mutation occurs.
- **GPT-5.6 reasoning contribution:** Focused the proof on fresh session IDs, fresh hashes, a deterministic exit code, and a visible tamper failure—claims a static brochure cannot satisfy without the underlying recorder and verifier.
- **Live acceptance proof:** In the attached WSL environment, `python -m pytest -q && receipts demo --live` passed all `25` tests and then created fresh session `20260720T173517Z-867eaa69` in a retained Git repository. Its canonical SHA-256 verified unsigned, `src/auth/login.py` was convention-mapped verified, `src/auth/session.py` was indirectly exercised, and the intentionally final `src/billing/invoice.py` edit was `NEVER EXECUTED`. The expected sensitive-only policy report blocked precisely that billing file. An initial fixture run exposed unnecessary package `__init__.py` files in the card; the fixture was simplified and the final accepted run contains only the three meaningful source findings.
- **Final gate proof:** After the fixture cleanup, WSL again passed `25` tests and recorded session `20260720T173833Z-a395308e`. `receipts verify` returned `OK: sha256 verified (unsigned)`, while `receipts gate <manifest> --sensitive-only` printed `Evidence gate: BLOCKED` for only `src/billing/invoice.py` and exited with status `1`. This is the intended CI enforcement behavior, not a demo failure.

## 2026-07-20 — M10 dirty-worktree attribution boundary start

- **Request:** Strengthen Receipts beyond a fixed demo by ensuring it does not attribute a developer's existing uncommitted work to the wrapped agent.
- **Decision:** Take a Git baseline before the PTY starts and keep two deliberately distinct final facts: `final.changed_files` remains the complete diff against the starting commit, while `final.agent_changed_files` contains only paths whose final observed state differs from the session-start state.
- **Evidence boundary:** Existing worktree changes are not called “human changes,” because a receipt sees repository state rather than authorship. They are labeled **pre-existing worktree changes**. Unchanged baseline paths stay inspectable in snapshots and the full diff, but are excluded from the Trust Card counts, risk flags, verification tiers, and evidence gate.
- **Transient and destructive-work decision:** A pre-existing path changed during the session is retained in the timeline with `preexisting_at_start`; a transient edit reverted before session end does not create a gate finding. If a dirty baseline path becomes clean, the receipt records it in `final.preexisting_changes_removed` rather than silently losing that fact.
- **Live-proof decision:** Add `receipts demo --live --dirty-baseline`, a second fresh PTY run that begins with an already-dirty sensitive billing path and expects the gate to pass. It turns the attribution rule into a judge-visible proof rather than leaving it as a hidden schema behavior.
- **GPT-5.6 reasoning contribution:** Separated the question “what was already present in the worktree?” from “what net delta did this observed session leave behind?” That distinction is essential for a provenance product: a reviewer must be able to see the raw context without falsely blaming the agent for it.
- **Local regression proof:** Python compilation passed; deterministic attribution tests passed; and a real temporary Git repository confirmed that a pre-existing billing edit stays in `final.changed_files` after an agent commit while only the new `src/login.py` enters `final.agent_changed_files`. The attached WSL environment remains the acceptance environment for the full pytest suite and live PTY proof.
- **M10 acceptance proof:** In the attached WSL environment, `python -m pytest -q` passed **35 tests in 1.85s**. Fresh dirty-baseline session `20260720T181836Z-90ec39a6` recorded one pre-existing dirty billing path, displayed the Trust Card attribution boundary, and produced `Evidence gate: PASS`. `receipts verify` returned `OK: sha256 verified (unsigned)` and the sensitive-only gate reported no blocking `NEVER EXECUTED` findings, proving the existing billing work was preserved as raw evidence without being attributed to the agent.

## 2026-07-21 — M11 privacy-safe live evidence feed start

- **Request:** Make the deployed demo visibly fresh and interactive without turning Receipts into a broad hosted SaaS or exposing a developer's raw terminal session.
- **Security finding:** The original public sample was a full capture manifest. Although it was a harmless bundled demo, that schema can carry working directories, task text, full argv, Git identifiers, transcript artifact names, paths, command summaries, URLs, and content-derived hashes. A real receipt must never be published that way.
- **Decision:** Add `receipts export-public`. It verifies the source receipt first, then creates a separate `receipts-public-feed/v1` projection with stable `file-001` aliases, agent category, counts, generic risk categories, verification states, and relative event offsets. It omits the raw task, source paths and their mapping, commands, summaries, Git data, artifacts, transcripts, wall-clock session times, source hash, and signature. The projection gets its own canonical SHA-256; that hash does not pretend to verify hidden source data.
- **Public-view decision:** Replace public `docs/sample-session.json` and `docs/replay.html` with the alias-only derivative. The deployed dashboard tries `live/latest.json` first, verifies its public hash in-browser, and visibly falls back to the separately verified safe sample on absence or failure. Full raw replays remain local CLI artifacts.
- **AWS authority decision:** Split the existing broad static-site role from a new OIDC live-feed publisher role. The normal deploy role has an explicit deny for `live/*` and its sync excludes that prefix. The new role can only put `live/latest.json` and `live/latest.html`; it cannot list, read, delete, invalidate, or administer the bucket. CloudFront uses CachingDisabled only for `live/*`.
- **Publication decision:** A manual master-only GitHub workflow records a fresh synthetic PTY proof in a trusted runner, verifies source and projection hashes, then publishes only the two fixed safe objects. It is a latest-published feed, not a multi-tenant service, terminal stream, or automatic user-data uploader.
- **GPT-5.6 reasoning contribution:** Reframed “make it live” as an evidence-boundary problem. Freshness matters only if it does not leak the very session facts the product asks developers to trust. The resulting design proves a new capture path while making publication an explicit, least-privilege, privacy-preserving act.
- **Local validation:** `public_feed.py`, the CLI, the public-sample builder, and M11 test modules compiled successfully. A deterministic harness passed 11 M11 checks: sanitizer privacy/aliasing, deterministic public hashing, tampered-source refusal, tampered-public-object detection, safe replay rendering, checked-in public sample validation, dashboard fallback contract, CloudFormation role/cache boundaries, and both deployment workflow contracts. A direct CLI integration also exported a public JSON + replay from the bundled source and verified both source and public SHA-256 values.
- **Environment boundary:** The desktop host's WSL bridge has no installed distribution and its Python sandbox cannot download pytest, so the full WSL `python -m pytest -q` acceptance remains intentionally deferred to the attached user terminal before the M11 commit. No claim of a full-suite pass is made here until that terminal output exists.
- **M11 acceptance proof:** In the attached WSL environment, `python -m pytest -q` passed **41 tests in 3.55s**. `receipts demo --live` then recorded fresh session `20260721T170725Z-4b6594e1`, whose source SHA-256 verified unsigned and whose expected sensitive-only gate blocked the final untested source change. `receipts export-public` converted that verified source into `/tmp/receipts-m11-public/latest.json` and `latest.html`; `receipts verify` verified the public JSON. The public object reported format `receipts-public-feed/v1`, aliases `file-001` through `file-003`, and statuses `verified`, `indirectly_exercised`, and `never_executed`—without publishing raw paths, task text, commands, Git metadata, or transcripts.

## 2026-07-21 — M12 VS Code local evidence workbench

- **User request:** Add a VS Code tool so Receipts is useful inside a
  developer's normal review environment.
- **Decision:** Build an optional local-only extension rather than a browser
  extension. It discovers genuine `.receipts/session-*.json` files in the
  opened workspace and renders stored Trust Card evidence, verification
  states, attribution boundaries, and flags in an Activity Bar workbench.
- **Why:** A browser cannot safely run a local terminal command. VS Code
  already has the workspace, source files, and integrated terminal needed for
  review. The extension is deliberately a reader and command handoff: it
  displays only recorded evidence, opens local files, and starts Verify/Gate/
  Replay as visible, argument-safe VS Code process tasks rather than
  duplicating or fabricating the CLI's judgments.
- **GPT-5.6 reasoning contribution:** Keep the new surface offline and
  dependency-free at runtime, retain M10's attribution boundary, distinguish
  full private manifests from alias-only M11 public feeds, and label a hash as
  recorded—not verified—until the canonical CLI verifier runs. A dark
  navy/glass/cyan workbench gives judges a tangible developer-tool experience
  without turning the raw receipt into a SaaS upload.
- **Acceptance target:** Native Node tests cover strict manifest fidelity,
  exact stored verification rows (with no invented row when analysis is
  absent), agent-attribution preference, and captured-workspace path
  containment. A stdlib VSIX builder creates an installable package with no
  `node_modules`. A manual VS Code / WSL smoke opens a fresh M11 receipt and
  runs the real gate.
