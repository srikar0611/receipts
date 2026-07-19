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
