"""Rejected profiles page — review past rejections and reconsider them."""

from __future__ import annotations

from stario import datastar as ds
from stario import html as h
from stario.html.types import SafeString

from models import Profile
from views.layout import app_nav, document_head


def _reconsider_post(profile_id: object) -> SafeString:
    """Datastar @post with a quoted JS string literal (SafeString avoids entity encoding)."""
    return SafeString(ds.post("/reconsider", payload={"targetId": ds.s(str(profile_id))}))


def _rejected_card(profile: Profile) -> h.Element:
    """Render one rejected profile card with a reconsider action."""
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
        h.Button(
            {
                "data-on:click": _reconsider_post(profile.id),
                "type": "button",
                "class": "btn btn-secondary",
            },
            "↩ Reconsider",
        ),
    )


def render_rejected_list(rejected: list[Profile]) -> h.Element:
    """The list region patched in place after a reconsider."""
    if not rejected:
        return h.Div(
            {"id": "rejected-list", "class": "empty-state"},
            h.H2({"class": "empty-state-title"}, "No rejected profiles"),
            h.P(
                {"class": "empty-state-message"},
                "Profiles you reject show up here so you can bring them back to your "
                "deck if you change your mind.",
            ),
            h.Div(
                {"class": "empty-state-actions"},
                h.A({"href": "/discover", "class": "btn btn-secondary"}, "Back to Discover"),
            ),
        )
    return h.Div(
        {"id": "rejected-list", "class": "matches-grid"},
        *[_rejected_card(p) for p in rejected],
    )


def render_rejected_page(rejected: list[Profile]) -> h.Element:
    """Render the Rejected page."""
    return h.HtmlDocument(
        {"lang": "en"},
        document_head("Rejected — ShipSwipe"),
        h.Body(
            h.Main(
                {"id": "main"},
                h.Div(
                    {"class": "container matches-layout"},
                    h.Div(
                        {"class": "page-intro"},
                        app_nav(),
                        h.H1("Rejected profiles"),
                        h.P(
                            "Changed your mind? Reconsider a profile to send it back to "
                            "your Discover deck."
                        ),
                    ),
                    render_rejected_list(rejected),
                ),
            ),
        ),
    )
