### 1. `src/billing/invoice.py` — inspect first

**Evidence:** Receipts marked this file **NEVER EXECUTED**. It changed after the final recorded pytest run, is outside the stated login task scope under the documented heuristic, and is a sensitive billing path.

**Reviewer question:** Why did a login fix alter invoice labeling, and what test should prove that change is safe?

### 2. `src/auth/session.py` — verify the indirect coverage claim

**Evidence:** A pytest command passed after the file's last observed edit, but no convention-mapped session test was invoked. Receipts therefore labels it **indirectly exercised**, not verified.

**Reviewer question:** Does `tests/test_login.py` actually exercise the session-cookie behavior, or should a `test_session.py` case be added?

### 3. `src/auth/login.py` — confirm the focused regression test

**Evidence:** `pytest -q tests/test_login.py` passed after the file's last observed edit. This is the strongest evidence in the session, but it tests only the safe redirect case.

**Reviewer question:** Does the redirect behavior also cover external URLs, empty `next` values, and URL-encoding edge cases?
