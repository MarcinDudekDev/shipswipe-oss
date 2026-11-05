"""Server-rendered discover deck fragments."""

from __future__ import annotations

import uuid

from stario import datastar as ds
from stario import html as h
from stario.html.types import SafeString

from models import Profile


def _swipe_post(direction: str, profile_id: object) -> SafeString:
    """Datastar @post with quoted JS string literals (SafeString avoids HTML entity encoding)."""
    return SafeString(
        ds.post(
            "/swipe",
            payload={
                "targetId": ds.s(str(profile_id)),
                "direction": ds.s(direction),
            },
        )
    )


def _connect_post(match_id: uuid.UUID) -> SafeString:
    """Datastar @post /connect with the match id as a quoted literal."""
    return SafeString(ds.post("/connect", payload={"match_id": ds.s(str(match_id))}))


def _modal_close_button(label: str = "Keep swiping") -> h.Element:
    """Render the dismiss button shared by the modals."""
    return h.Button(
        {
            "data-on:click": SafeString("el.closest('#match-modal').hidden = true"),
            "type": "button",
            "class": "btn btn-secondary",
            "data-action": "close",
        },
        label,
    )


def render_front_card(profile: Profile, *, show_actions: bool = False) -> h.Element:
    """Render the top deck card for a candidate profile."""
    looking_for = profile.looking_for or ""
    building = profile.building or ""
    terms = profile.terms or ""

    children: list[h.Element] = [
        h.Button(
            ds.on("click", "$detailsOpen = !$detailsOpen"),
            {
                "type": "button",
                "class": "card-drawer-toggle",
                "data-action": "details",
                "aria-label": f"View full details for {profile.name}",
            },
            "⋯ Details",
        ),
        h.Header(
            {"class": "card-header"},
            h.Div(
                {"class": "card-identity"},
                h.H2({"class": "card-name"}, profile.name),
            ),
        ),
        h.P(
            {"class": "card-looking"},
            h.Span({"class": "card-looking-label"}, "Looking for"),
            looking_for,
        ),
        h.Div(
            ds.show("$detailsOpen"),
            {
                "style": "display:none",
                "class": "card-drawer-details",
            },
            h.P({"data-field": "building"}, building),
            h.P({"data-field": "terms"}, terms),
        ),
    ]

    if show_actions:
        children.append(
            h.Div(
                {"class": "swipe-actions"},
                h.Button(
                    {
                        "data-on:click": _swipe_post("pass", profile.id),
                        "type": "button",
                        "class": "btn-pass",
                    },
                    "Reject",
                ),
                h.Button(
                    {
                        "data-on:click": _swipe_post("like", profile.id),
                        "type": "button",
                        "class": "btn-like",
                    },
                    "Interested",
                ),
            )
        )

    return h.Article(
        ds.signals({"detailsOpen": False}),
        {"class": "card", "aria-label": profile.name},
        *children,
    )


def render_match_modal(profile: Profile, match_id: uuid.UUID | None = None) -> h.Element:
    """Fresh-match dialog. With a match id the Connect button posts /connect for real;
    without one it degrades to a link to /matches."""
    if match_id is not None:
        connect_control: h.Element = h.Button(
            {
                "data-on:click": _connect_post(match_id),
                "type": "button",
                "class": "btn btn-primary",
                "data-action": "connect",
            },
            "Connect",
        )
    else:
        connect_control = h.A(
            {"href": "/matches", "class": "btn btn-primary", "data-action": "connect"},
            "Connect",
        )

    return h.Div(
        {
            "id": "match-modal",
            "class": "modal",
            "role": "dialog",
            "aria-modal": "true",
            "aria-labelledby": "match-modal-heading",
        },
        h.Div(
            {"class": "modal-card"},
            h.H2(
                {"id": "match-modal-heading", "class": "match-modal-title"},
                f"You and {profile.name} have a connection!",
            ),
            h.P(
                {"class": "match-modal-body"},
                "You're both interested. Connect and start planning your launch together.",
            ),
            h.Div(
                {"class": "modal-actions"},
                connect_control,
                _modal_close_button(),
            ),
        ),
    )


def render_connected_modal(profile: Profile) -> h.Element:
    """Patched into ``#match-modal`` when Connect was clicked from the dialog —
    the discover page has no ``#connect-panel``, so confirm and route to /matches."""
    return h.Div(
        {
            "id": "match-modal",
            "class": "modal",
            "role": "dialog",
            "aria-modal": "true",
            "aria-labelledby": "match-modal-heading",
        },
        h.Div(
            {"class": "modal-card"},
            h.H2(
                {"id": "match-modal-heading", "class": "match-modal-title"},
                f"You're connected with {profile.name}!",
            ),
            h.P(
                {"class": "match-modal-body"},
                "Send them an intro from your matches page to kick things off.",
            ),
            h.Div(
                {"class": "modal-actions"},
                h.A({"href": "/matches", "class": "btn btn-primary"}, "Write your intro →"),
                _modal_close_button(),
            ),
        ),
    )


def render_toast(message: str) -> h.Element:
    """Transient confirmation patched into #toast; auto-fades via CSS animation."""
    return h.Div(
        {"id": "toast", "class": "toast", "role": "status", "aria-live": "polite"},
        message,
    )


def render_deck(candidates: list[Profile], *, show_actions: bool = False) -> h.Element:
    """Render the swipe deck container over a list of candidates."""
    if not candidates:
        return h.Section(
            {"id": "deck", "class": "deck deck-empty"},
            h.Div(
                {"class": "empty-state"},
                h.H2({"class": "empty-state-title"}, "No one new right now"),
                h.P(
                    {"class": "empty-state-message"},
                    "New builders and marketers join all the time — check back soon. "
                    "Meanwhile, polish your profile so the right partners find you.",
                ),
                h.Div(
                    {"class": "empty-state-actions"},
                    h.A({"href": "/profile", "class": "btn btn-secondary"}, "Edit your profile"),
                ),
            ),
        )
    return h.Section(
        {"id": "deck", "class": "deck"},
        render_front_card(candidates[0], show_actions=show_actions),
    )