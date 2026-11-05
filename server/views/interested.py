"""Interested page — people you've expressed interest in, awaiting their response."""

from __future__ import annotations

from stario import html as h

from models import Profile
from views.layout import app_nav, document_head


def _interested_card(profile: Profile) -> h.Element:
    """Render one pending-interest card."""
    return h.Article(
        {"class": "match-card"},
        h.Div(
            {"class": "match-card-head"},
            h.H2({"class": "match-card-name"}, profile.name),
            h.Span({"class": "match-role"}, (profile.role or "").title()),
        ),
        h.P(
            {"class": "card-looking"},
            h.Span({"class": "card-looking-label"}, "Looking for"),
            profile.looking_for or "—",
        ),
        h.P({"class": "match-building"}, profile.building or ""),
        h.Span({"class": "pending-status"}, "Awaiting response"),
    )


def render_interested_list(interested: list[Profile]) -> h.Element:
    """Render the pending-interest card list."""
    if not interested:
        return h.Div(
            {"id": "interested-list", "class": "empty-state"},
            h.H2({"class": "empty-state-title"}, "No pending interest"),
            h.P(
                {"class": "empty-state-message"},
                "When you mark someone as interested, they wait here until they're "
                "interested back — then they move to Matches and you can connect.",
            ),
            h.Div(
                {"class": "empty-state-actions"},
                h.A({"href": "/discover", "class": "btn btn-secondary"}, "Back to Discover"),
            ),
        )
    return h.Div(
        {"id": "interested-list", "class": "matches-grid"},
        *[_interested_card(p) for p in interested],
    )


def render_interested_page(interested: list[Profile]) -> h.Element:
    """Render the Interested page."""
    return h.HtmlDocument(
        {"lang": "en"},
        document_head("Interested — ShipSwipe"),
        h.Body(
            h.Main(
                {"id": "main"},
                h.Div(
                    {"class": "container matches-layout"},
                    h.Div(
                        {"class": "page-intro"},
                        app_nav(),
                        h.H1("People you're interested in"),
                        h.P(
                            "You've marked these partners as interested. They'll move to "
                            "Matches the moment they're interested in you too — until then "
                            "it's awaiting their response."
                        ),
                    ),
                    render_interested_list(interested),
                ),
            ),
        ),
    )
