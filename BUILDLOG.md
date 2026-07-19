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
