from src.auth.login import redirect_after_login


def test_safe_redirect():
    assert redirect_after_login("/settings") == "/settings"
