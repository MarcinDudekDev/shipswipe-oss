"""Email-only magic-link login page (also used as the members-only gate)."""

from __future__ import annotations

from stario import datastar as ds
from stario import html as h

from views.layout import document_head


def render_login_page(*, gated: bool = False) -> h.Element:
    """Render the email sign-in page."""
    heading = "Sign in to continue" if gated else "Log in"
    sub = (
        "ShipSwipe is members-only — sign in to discover partners and swipe."
        if gated
        else "Enter your email and we'll send you a magic sign-in link."
    )
    return h.HtmlDocument(
        {"lang": "en"},
        document_head("Log in — ShipSwipe"),
        h.Body(
            h.Main(
                {"id": "main"},
                h.Div(
                    {"class": "container login-layout"},
                    h.Section(
                        ds.signals({"email": "", "sent": False}),
                        {"class": "panel login-card", "aria-labelledby": "login-heading"},
                        h.A({"href": "/", "class": "login-brand"}, "ShipSwipe"),
                        h.H1({"id": "login-heading"}, heading),
                        h.P({"class": "panel-sub"}, sub),
                        h.Form(
                            ds.on("submit", "@post('/auth/request-link'); $sent = true", prevent=True),
                            ds.show("!$sent"),
                            {"class": "login-form"},
                            h.Div(
                                {"class": "form-field"},
                                h.Label({"for": "login-email"}, "Email"),
                                h.Input(
                                    ds.bind("email"),
                                    {
                                        "type": "email", "name": "email", "id": "login-email",
                                        "required": True, "autocomplete": "email",
                                        "placeholder": "you@example.com",
                                    },
                                ),
                            ),
                            h.Button(
                                {"type": "submit", "class": "btn btn-primary cta login-submit"},
                                "Email me a login link →",
                            ),
                        ),
                        h.P(
                            ds.show("$sent"),
                            {"class": "signin-sent", "role": "status", "style": "display:none"},
                            "Check your inbox — your ShipSwipe login link is on its way.",
                        ),
                        h.P(
                            {"class": "login-alt"},
                            "New to ShipSwipe? ",
                            h.A({"href": "/"}, "Create an account →"),
                        ),
                        h.P(
                            {"class": "login-alt"},
                            h.A({"href": "/changelog"}, "See what's new →"),
                        ),
                    ),
                ),
            ),
            h.Footer(
                {"class": "site-footer"},
                h.Div(
                    {"class": "container footer-inner"},
                    h.P("ShipSwipe — swipe your way to a builder-marketer partnership."),
                    h.Nav(
                        {"class": "footer-links", "aria-label": "Footer"},
                        h.A({"href": "/"}, "Home"),
                        h.A({"href": "/changelog"}, "What's new"),
                        h.A({"href": "/privacy"}, "Privacy"),
                        h.A({"href": "/terms"}, "Terms"),
                    ),
                ),
            ),
        ),
    )


def render_verify_confirm_page(*, email: str, token: str) -> h.Element:
    """Magic-link landing: confirm the sign-in with a POST (scanners only GET)."""
    return h.HtmlDocument(
        {"lang": "en"},
        document_head("Sign in — ShipSwipe"),
        h.Body(
            h.Main(
                {"id": "main"},
                h.Div(
                    {"class": "container login-layout"},
                    h.Section(
                        {"class": "panel login-card", "aria-labelledby": "verify-heading"},
                        h.A({"href": "/", "class": "login-brand"}, "ShipSwipe"),
                        h.H1({"id": "verify-heading"}, "Finish signing in"),
                        h.P({"class": "panel-sub"}, f"Sign in as {email}"),
                        h.Form(
                            {
                                "method": "post",
                                "action": "/auth/verify",
                                "class": "login-form",
                            },
                            h.Input(
                                {"type": "hidden", "name": "token", "value": token}
                            ),
                            h.Button(
                                {
                                    "type": "submit",
                                    "class": "btn btn-primary cta login-submit",
                                },
                                "Sign in →",
                            ),
                        ),
                    ),
                ),
            ),
            h.Footer(
                {"class": "site-footer"},
                h.Div(
                    {"class": "container footer-inner"},
                    h.P("ShipSwipe — swipe your way to a builder-marketer partnership."),
                    h.Nav(
                        {"class": "footer-links", "aria-label": "Footer"},
                        h.A({"href": "/"}, "Home"),
                        h.A({"href": "/changelog"}, "What's new"),
                        h.A({"href": "/privacy"}, "Privacy"),
                        h.A({"href": "/terms"}, "Terms"),
                    ),
                ),
            ),
        ),
    )
