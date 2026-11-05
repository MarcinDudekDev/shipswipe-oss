"""Profile completion / edit screen — a real HTML form."""

from __future__ import annotations

from stario import html as h

from models import Profile

_TERMS = [
    ("rev-share", "Rev-share"),
    ("equity", "Equity"),
    ("paid", "Paid"),
    ("flexible", "Flexible"),
]


def _head() -> h.Element:
    """Render the profile page <head>."""
    return h.Head(
        h.Meta({"charset": "UTF-8"}),
        h.Meta({"name": "viewport", "content": "width=device-width, initial-scale=1.0"}),
        h.Title("Your profile — ShipSwipe"),
        h.Link({"rel": "icon", "href": "/static/favicon.svg", "type": "image/svg+xml"}),
        h.Link({"rel": "icon", "href": "/static/favicon.ico", "sizes": "any"}),
        h.Link({"rel": "apple-touch-icon", "href": "/static/apple-touch-icon.png"}),
        h.Link({"rel": "stylesheet", "href": "/static/styles.css"}),
    )


def _nav() -> h.Element:
    """Render the profile page nav."""
    return h.Nav(
        {"class": "app-nav", "aria-label": "Primary"},
        h.A({"href": "/discover", "class": "app-nav-brand"}, "ShipSwipe"),
        h.Div(
            {"class": "app-nav-links"},
            h.A({"href": "/discover"}, "Discover"),
            h.A({"href": "/matches"}, "Matches"),
            h.A({"href": "/interested"}, "Interested"),
            h.A({"href": "/rejected"}, "Rejected"),
            h.A({"href": "/changelog"}, "What's new"),
            h.Form(
                {"method": "post", "action": "/auth/logout", "class": "app-nav-logout"},
                h.Button({"type": "submit", "class": "btn btn-secondary"}, "Log out"),
            ),
        ),
    )


def _text_field(label: str, name: str, value: str, placeholder: str = "",
                *, required: bool = False, hint: str | None = None) -> h.Element:
    """Render a labeled text input for the profile form."""
    attrs = {"type": "text", "name": name, "id": f"pf-{name}", "value": value or ""}
    if placeholder:
        attrs["placeholder"] = placeholder
    if required:
        attrs["required"] = True
    children = [h.Label({"for": f"pf-{name}"}, label), h.Input(attrs)]
    if hint:
        children.append(h.P({"class": "field-hint"}, hint))
    return h.Div({"class": "form-field"}, *children)


def render_profile_page(
    profile: Profile | None,
    *,
    role_default: str = "builder",
    complete: bool = True,
    tags: str = "",
) -> h.Element:
    """Render the profile editor form."""
    role = profile.role if profile else role_default
    name = profile.name if profile else ""
    bio = (profile.bio if profile else "") or ""
    building = (profile.building if profile else "") or ""
    looking_for = (profile.looking_for if profile else "") or ""
    terms = profile.terms if profile else "flexible"

    role_options = [
        h.Option({"value": r, **({"selected": True} if role == r else {})}, label)
        for r, label in (("builder", "Builder"), ("marketer", "Marketer"))
    ]
    terms_options = [
        h.Option({"value": v, **({"selected": True} if terms == v else {})}, label)
        for v, label in _TERMS
    ]

    intro = (
        "Finish your profile so matches see who you are and what you need."
        if not complete
        else "Update your profile any time."
    )

    return h.HtmlDocument(
        {"lang": "en"},
        _head(),
        h.Body(
            h.Main(
                {"id": "main"},
                h.Div(
                    {"class": "container profile-edit"},
                    h.Div({"class": "page-intro"}, _nav()),
                    h.Section(
                        {"class": "panel profile-card", "aria-labelledby": "profile-heading"},
                        h.H1({"id": "profile-heading"}, "Your profile"),
                        h.P({"class": "panel-sub"}, intro),
                        h.Form(
                            {"method": "post", "action": "/profile", "class": "profile-form"},
                            h.Div(
                                {"class": "form-field"},
                                h.Label({"for": "pf-role"}, "I'm a…"),
                                h.Select({"name": "role", "id": "pf-role"}, *role_options),
                            ),
                            _text_field("Your name", "name", name, "Alex Rivera", required=True),
                            _text_field("What are you building?", "building", building,
                                        "e.g. B2B invoicing tool", required=True),
                            _text_field("Looking for", "looking_for", looking_for,
                                        "The partner you want", required=True),
                            h.Div(
                                {"class": "form-field"},
                                h.Label({"for": "pf-terms"}, "Partnership terms"),
                                h.Select({"name": "terms", "id": "pf-terms"}, *terms_options),
                            ),
                            h.Div(
                                {"class": "form-field"},
                                h.Label({"for": "pf-bio"}, "Short bio"),
                                h.Textarea({"name": "bio", "id": "pf-bio", "rows": "3"}, bio),
                            ),
                            _text_field("Tags", "tags", tags, "React, SEO, Bootstrapped",
                                        hint="Comma-separated."),
                            h.Button(
                                {"type": "submit", "class": "btn btn-primary cta profile-submit"},
                                "Save & start swiping →",
                            ),
                        ),
                    ),
                    h.Section(
                        {"class": "panel account-card", "aria-labelledby": "account-heading"},
                        h.H2({"id": "account-heading"}, "Your data & account"),
                        h.P(
                            {"class": "panel-sub"},
                            "Everything we hold about you is yours — download it any "
                            "time, or delete the whole account and all its data.",
                        ),
                        h.P(
                            {"class": "account-actions"},
                            h.A(
                                {"href": "/account/export", "class": "btn btn-secondary"},
                                "Download my data",
                            ),
                        ),
                        h.Form(
                            {"method": "post", "action": "/account/delete",
                             "class": "delete-form"},
                            h.Div(
                                {"class": "form-field"},
                                h.Label(
                                    {"for": "delete-confirm"},
                                    "Delete my account — type DELETE to confirm",
                                ),
                                h.Input(
                                    {
                                        "type": "text", "name": "confirm",
                                        "id": "delete-confirm", "required": True,
                                        "autocomplete": "off", "placeholder": "DELETE",
                                    },
                                ),
                                h.P(
                                    {"class": "field-hint"},
                                    "Permanent — removes your profile, swipes, "
                                    "matches, and messages. No undo.",
                                ),
                            ),
                            h.Button(
                                {"type": "submit", "class": "btn btn-danger"},
                                "Delete my account",
                            ),
                        ),
                        h.P(
                            {"class": "account-legal"},
                            h.A({"href": "/privacy"}, "Privacy"),
                            " · ",
                            h.A({"href": "/terms"}, "Terms"),
                        ),
                    ),
                ),
            ),
        ),
    )
