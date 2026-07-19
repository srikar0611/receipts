#!/usr/bin/env sh
# A deterministic stand-in for a coding agent used to exercise Receipts capture.
set -eu
set -x

mkdir -p src/auth src/billing tests
cat > src/auth/login.py <<'PY'
def redirect_after_login(next_path: str | None) -> str:
    return next_path if next_path and next_path.startswith("/") else "/dashboard"
PY
cat > tests/test_login.py <<'PY'
from src.auth.login import redirect_after_login


def test_safe_redirect():
    assert redirect_after_login("/settings") == "/settings"
PY
sleep 3
python3 -m pytest -q tests/test_login.py
sleep 1

cat > src/auth/session.py <<'PY'
def session_cookie_name() -> str:
    return "receipt_session"
PY
sleep 3
python3 -m pytest -q tests/test_login.py
sleep 1

# This is intentionally changed after the last test run. M2 must flag it red.
cat > src/billing/invoice.py <<'PY'
def invoice_label(invoice_id: str) -> str:
    return f"Invoice {invoice_id}"
PY
