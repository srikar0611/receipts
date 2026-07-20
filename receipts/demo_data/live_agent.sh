#!/usr/bin/env sh
# A dependency-free, deterministic coding-agent stand-in for `receipts demo --live`.
# It uses Python's standard-library unittest runner so a clean `pip install .`
# can record real test executions without downloading pytest or contacting a service.
set -eu
set -x

mkdir -p src/auth src/billing tests

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

# Leave enough time for Receipts' two-second Git poller to observe this change.
sleep 3
python3 -m unittest -q tests/test_login.py
sleep 1

cat > src/auth/session.py <<'PY'
def session_cookie_name() -> str:
    return "receipt_session"
PY

sleep 3
python3 -m unittest -q tests/test_login.py
sleep 1

# Intentionally after the final test: the live gate should block this change.
cat > src/billing/invoice.py <<'PY'
def invoice_label(invoice_id: str) -> str:
    return f"Invoice {invoice_id}"
PY
