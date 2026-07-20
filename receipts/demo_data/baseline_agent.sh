#!/usr/bin/env sh
# Used by `receipts demo --live --dirty-baseline` to prove that an unchanged
# sensitive file which was dirty before capture is not attributed to the agent.
set -eu
set -x

mkdir -p src/auth tests

cat > src/auth/login.py <<'PY'
def redirect_after_login(next_path: str | None) -> str:
    return next_path if next_path and next_path.startswith("/") else "/dashboard"
PY

cat > tests/test_login.py <<'PY'
import unittest

from src.auth.login import redirect_after_login


class LoginRedirectTests(unittest.TestCase):
    def test_safe_redirect(self) -> None:
        self.assertEqual(redirect_after_login("/settings"), "/settings")


if __name__ == "__main__":
    unittest.main()
PY

# Leave enough time for Receipts' two-second Git poller to observe the edit.
sleep 3
python3 -m unittest -q tests/test_login.py
