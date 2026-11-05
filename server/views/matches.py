"""Matches list page."""

from __future__ import annotations

import uuid

from stario import datastar as ds
from stario import html as h
from stario.html.types import SafeString

from models import Match, Profile
from views.layout import app_nav, document_head


def _connect_post(match_id: uuid.UUID) -> SafeString:
    """Datastar @post with quoted JS string literals (SafeString avoids entity encoding)."""
    return SafeString(ds.post("/connect", payload={"match_id": ds.s(str(match_id))}))


def _intro_post(match_id: uuid.UUID) -> SafeString:
    """@post /intro — ``body`` is the live ``$introBody`` signal, not a literal."""
    return SafeString(
        ds.post(
            "/intro",
            payload={"match_id": ds.s(str(match_id)), "body": "$introBody"},
        )
    )


def render_match_card(match: Match, other: Profile) -> h.Element:
    """Render one match row with its counterpart profile."""
    connected = match.connected_at is not None
    return h.Article(
        {"class": "match-card", "id": f"match-card-{match.id}"},
        h.Div(
            {"class": "match-card-head"},
            h.H2({"class": "match-card-name"}, other.name),
            h.Span({"class": "match-role"}, (other.role or "").title()),
        ),
        h.P(
            {"class": "card-looking"},
            h.Span({"class": "card-looking-label"}, "Looking for"),
            other.looking_for or "—",
        ),
        h.P({"class": "match-building"}, other.building or ""),
        h.Div(
            {"class": "match-card-actions"},
            h.Button(
                {
                    "data-on:click": _connect_post(match.id),
                    "type": "button",
                    "class": "btn-connect",
                    "data-action": "connect",
                    "data-match-id": str(match.id),
                    "aria-label": f"Connect with {other.name}",
                },
                "Connected — write intro" if connected else "Connect",
            ),
        ),
    )


def render_connect_panel(match: Match | None, other: Profile | None) -> h.Element:
    """The single ``#connect-panel`` — populated for the active match, else a hidden shell.

    ``/connect`` patches this node (outer) so the composer and contact context
    appear without a page reload; the discover page has no such node, and the
    patch is harmlessly skipped there.
    """
    if match is None or other is None:
        return h.Section(
            {
                "id": "connect-panel",
                "class": "connect-panel panel",
                "aria-labelledby": "connect-heading",
                "hidden": True,
            },
            h.H2({"id": "connect-heading"}, "Connect"),
        )

    return h.Section(
        ds.signals({"introBody": ""}),
        {
            "id": "connect-panel",
            "class": "connect-panel panel",
            "aria-labelledby": "connect-heading",
        },
        h.H2({"id": "connect-heading"}, f"Connect with {other.name}"),
        h.P(
            {"id": "connect-contact", "class": "connect-contact"},
            f"{other.name} is looking for {other.looking_for or 'a partner'} — "
            "say hello and start planning your launch together.",
        ),
        h.Div(
            {"class": "form-field"},
            h.Label({"for": "intro-message"}, "Intro message"),
            h.Textarea(
                ds.bind("introBody"),
                {
                    "id": "intro-message",
                    "name": "body",
                    "rows": 4,
                    "placeholder": "Write a short intro to your match…",
                },
            ),
        ),
        h.Div(
            {"class": "form-actions"},
            h.Button(
                {
                    "data-on:click": _intro_post(match.id),
                    "type": "button",
                    "class": "btn btn-primary",
                    "data-action": "send-intro",
                },
                "Send intro",
            ),
            h.Button(
                {
                    "data-on:click": SafeString(
                        "el.closest('#connect-panel').hidden = true"
                    ),
                    "type": "button",
                    "class": "btn btn-secondary",
                    "data-action": "close-connect",
                },
                "Close",
            ),
        ),
        h.P(
            {"id": "intro-sent", "class": "intro-sent", "role": "status", "hidden": True},
        ),
    )


def render_intro_status(message: str) -> h.Element:
    """Status region patched into ``#intro-sent`` after ``/intro`` (or a rejection)."""
    return h.P(
        {"id": "intro-sent", "class": "intro-sent", "role": "status"},
        message,
    )


def render_matches_page(rows) -> h.Element:
    """Render the matches page from match/profile rows."""
    if rows:
        # Panel opens for the most recent connected match, if any.
        active_match, active_other = next(
            ((m, o) for m, o in rows if m.connected_at is not None),
            (None, None),
        )
        content = [
            h.Div(
                {"class": "matches-grid"},
                *[render_match_card(match, other) for match, other in rows],
            ),
            render_connect_panel(active_match, active_other),
        ]
    else:
        content = [
            h.Div(
                {"class": "empty-state"},
                h.H2({"class": "empty-state-title"}, "No matches yet"),
                h.P(
                    {"class": "empty-state-message"},
                    "Mark someone as interested who's interested in you too, "
                    "and they'll show up here.",
                ),
                h.Div(
                    {"class": "empty-state-actions"},
                    h.A({"href": "/discover", "class": "btn btn-secondary"}, "Back to Discover"),
                ),
            )
        ]

    return h.HtmlDocument(
        {"lang": "en"},
        document_head("Matches — ShipSwipe"),
        h.Body(
            h.Main(
                {"id": "main"},
                h.Div(
                    {"class": "container matches-layout"},
                    h.Div(
                        {"class": "page-intro"},
                        app_nav(),
                        h.H1("Your matches"),
                        h.P(
                            "People who were interested in you, too. Reach out and start "
                            "planning your launch together."
                        ),
                    ),
                    *content,
                ),
            ),
        ),
    )
