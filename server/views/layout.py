"""Shared page chrome: document head + app nav."""

from __future__ import annotations

from stario import datastar as ds
from stario import html as h


def document_head(title: str) -> h.Element:
    """Render the shared <head> for a page title."""
    return h.Head(
        h.Meta({"charset": "UTF-8"}),
        h.Meta({"name": "viewport", "content": "width=device-width, initial-scale=1.0"}),
        h.Title(title),
        h.Link({"rel": "icon", "href": "/static/favicon.svg", "type": "image/svg+xml"}),
        h.Link({"rel": "icon", "href": "/static/favicon.ico", "sizes": "any"}),
        h.Link({"rel": "apple-touch-icon", "href": "/static/apple-touch-icon.png"}),
        h.Link({"rel": "stylesheet", "href": "/static/styles.css"}),
        ds.ModuleScript("/static/js/datastar.js"),
    )


def app_nav() -> h.Element:
    """Render the authenticated in-app navigation bar."""
    return h.Nav(
        {"class": "app-nav", "aria-label": "Primary"},
        h.A({"href": "/discover", "class": "app-nav-brand"}, "ShipSwipe"),
        h.Div(
            {"class": "app-nav-links"},
            h.A({"href": "/discover"}, "Discover"),
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
    )
