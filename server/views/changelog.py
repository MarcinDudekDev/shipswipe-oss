"""Public changelog / product updates page.

To add a release: prepend a dict to CHANGELOG (newest first). Keep `date` as a
human "Mon D, YYYY" string and `tag` one of: New, Improved, Fixed.
"""

from __future__ import annotations

from stario import datastar as ds
from stario import html as h

# Newest first. Each change: {"tag": New|Improved|Fixed, "text": "..."}.
CHANGELOG: list[dict] = [
    {
        "date": "Jun 30, 2026",
        "title": "See who you're interested in",
        "changes": [
            {
                "tag": "New",
                "text": "New Interested list — the people you've reached out to now "
                "show up with an “Awaiting response” status instead of disappearing. "
                "They move to Matches the moment they're interested back.",
            },
            {
                "tag": "Improved",
                "text": "Tapping Interested now shows an instant confirmation so it's "
                "clear your interest was sent (a match still needs both sides).",
            },
        ],
    },
    {
        "date": "Jun 30, 2026",
        "title": "Clearer language + reconsider your rejects",
        "changes": [
            {
                "tag": "Improved",
                "text": "Renamed the swipe actions to Reject and Interested (industry "
                "wording) — “Pass” was being read as approval, which cost people the "
                "partners they meant to keep.",
            },
            {
                "tag": "New",
                "text": "New Rejected list with a Reconsider button — changed your mind "
                "about someone you passed on? Send them straight back to your deck.",
            },
        ],
    },
]

_TAG_CLASS = {"New": "badge-new", "Improved": "badge-improved", "Fixed": "badge-fixed"}


def _release(entry: dict) -> h.Element:
    """Render one changelog release entry."""
    items = [
        h.Li(
            {"class": "changelog-item"},
            h.Span(
                {"class": f"changelog-tag {_TAG_CLASS.get(c['tag'], 'badge-new')}"},
                c["tag"],
            ),
            h.Span({"class": "changelog-text"}, c["text"]),
        )
        for c in entry["changes"]
    ]
    return h.Article(
        {"class": "changelog-release"},
        h.Div(
            {"class": "changelog-release-head"},
            h.H2({"class": "changelog-title"}, entry["title"]),
            h.Time({"class": "changelog-date"}, entry["date"]),
        ),
        h.Ul({"class": "changelog-list"}, *items),
    )


def render_changelog_page() -> h.Element:
    """Render the public product-updates page."""
    return h.HtmlDocument(
        {"lang": "en"},
        h.Head(
            h.Meta({"charset": "UTF-8"}),
            h.Meta({"name": "viewport", "content": "width=device-width, initial-scale=1.0"}),
            h.Meta(
                {
                    "name": "description",
                    "content": "What's new on ShipSwipe — product updates, fixes, and "
                    "improvements to the builder-marketer matching network.",
                }
            ),
            h.Title("Updates — ShipSwipe"),
            h.Link({"rel": "icon", "href": "/static/favicon.svg", "type": "image/svg+xml"}),
            h.Link({"rel": "icon", "href": "/static/favicon.ico", "sizes": "any"}),
            h.Link({"rel": "apple-touch-icon", "href": "/static/apple-touch-icon.png"}),
            h.Link({"rel": "stylesheet", "href": "/static/styles.css"}),
            ds.ModuleScript("/static/js/datastar.js"),
        ),
        h.Body(
            h.A({"class": "skip-link", "href": "#main"}, "Skip to content"),
            h.Header(
                {"class": "site-header"},
                h.Div(
                    {"class": "container header-inner"},
                    h.A({"class": "logo", "href": "/"}, "ShipSwipe"),
                    h.Nav(
                        {"class": "site-nav", "aria-label": "Primary"},
                        h.A({"href": "/"}, "Home"),
                        h.A({"href": "/discover", "class": "btn btn-secondary"}, "Open app"),
                    ),
                ),
            ),
            h.Main(
                {"id": "main"},
                h.Section(
                    {"class": "container section-block", "aria-labelledby": "changelog-heading"},
                    h.P({"class": "eyebrow"}, "Product updates"),
                    h.H1({"id": "changelog-heading"}, "What's new on ShipSwipe"),
                    h.P(
                        {"class": "hero-tagline"},
                        "Every improvement we ship — many straight from your feedback. "
                        "Keep it coming.",
                    ),
                    h.Div({"class": "changelog"}, *[_release(e) for e in CHANGELOG]),
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
                        h.A({"href": "/#how-it-works"}, "How it works"),
                        h.A({"href": "/discover"}, "Open app"),
                        h.A({"href": "/privacy"}, "Privacy"),
                        h.A({"href": "/terms"}, "Terms"),
                        h.A({"href": "/login"}, "Log in"),
                    ),
                ),
            ),
        ),
    )
