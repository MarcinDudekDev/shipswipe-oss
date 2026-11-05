"""Full discover page HTML."""

from __future__ import annotations

from stario import datastar as ds
from stario import html as h

from models import Profile
from views.deck import render_deck


def render_discover_page(candidates: list[Profile]) -> h.Element:
    """Render the discover page wrapping the deck."""
    layout_children: list[h.Element] = [
        h.Div(
            {"class": "page-intro"},
            h.Nav(
                {"class": "app-nav", "aria-label": "Primary"},
                h.A({"href": "/discover", "class": "app-nav-brand"}, "ShipSwipe"),
                h.Div(
                    {"class": "app-nav-links"},
                    h.A({"href": "/matches"}, "Matches"),
                    h.A({"href": "/interested"}, "Interested"),
                    h.A({"href": "/rejected"}, "Rejected"),
                    h.A({"href": "/profile"}, "Profile"),
                    h.A({"href": "/changelog"}, "What's new"),
                    h.Form(
                        {"method": "post", "action": "/auth/logout", "class": "app-nav-logout"},
                        h.Button({"type": "submit", "class": "btn btn-secondary"}, "Log out"),
                    ),
                ),
            ),
            h.H1({"id": "discover-heading"}, "Discover your next partner"),
            h.P(
                "Review profiles on the opposite side. Mark someone as interested — "
                "if they're interested in you too, you connect instantly. "
                "Changed your mind about a reject? Find it under Rejected."
            ),
        ),
        render_deck(candidates, show_actions=True),
    ]

    return h.HtmlDocument(
        {"lang": "en"},
        h.Head(
            h.Meta({"charset": "UTF-8"}),
            h.Meta(
                {
                    "name": "viewport",
                    "content": "width=device-width, initial-scale=1.0",
                }
            ),
            h.Title("Discover — ShipSwipe"),
            h.Link({"rel": "icon", "href": "/static/favicon.svg", "type": "image/svg+xml"}),
            h.Link({"rel": "icon", "href": "/static/favicon.ico", "sizes": "any"}),
            h.Link({"rel": "apple-touch-icon", "href": "/static/apple-touch-icon.png"}),
            h.Link({"rel": "stylesheet", "href": "/static/styles.css"}),
            ds.ModuleScript("/static/js/datastar.js"),
        ),
        h.Body(
            h.Main(
                {"id": "main"},
                h.Div({"class": "container discover-layout"}, *layout_children),
            ),
            h.Div({"id": "match-modal", "hidden": True}),
            h.Div({"id": "toast"}),
        ),
    )