def redirect_after_login(next_path: str | None) -> str:
    return next_path if next_path and next_path.startswith("/") else "/dashboard"
