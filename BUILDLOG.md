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
