"""Auth gate helpers for protected endpoints."""

from __future__ import annotations

from stario import responses
from stario.http.context import Context
from stario.http.writer import Writer

from models import User


def current_user(c: Context) -> User | None:
    """Return the logged-in User for this request, or None."""
    return c.state.get("user")


def reject_anonymous(c: Context, w: Writer) -> bool:
    """Reject unauthenticated requests (API/mutations). True when blocked."""
    if current_user(c) is None:
        responses.text(w, "Unauthorized", status=401)
        return True
    return False


def require_user_page(c: Context, w: Writer) -> bool:
    """Gate a member PAGE: anonymous gets a friendly sign-in page (HTML 401)."""
    if current_user(c) is not None:
        return False
    from views.login import render_login_page  # lazy: avoid import cycle

    responses.html(w, render_login_page(gated=True), status=401)
    return True