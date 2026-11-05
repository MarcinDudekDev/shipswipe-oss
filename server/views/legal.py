"""Public legal pages — Privacy Policy and Terms of Service.

Plain-language, one page each. Both are reachable without an account and are
linked from every site footer so crawlers and members can always find them.
"""

from __future__ import annotations

from stario import html as h

from config import settings
from views.layout import document_head


def _site_header() -> h.Element:
    """Render the shared site header for legal pages."""
    return h.Header(
        {"class": "site-header"},
        h.Div(
            {"class": "container header-inner"},
            h.A({"class": "logo", "href": "/"}, "ShipSwipe"),
            h.Nav(
                {"class": "site-nav", "aria-label": "Primary"},
                h.A({"href": "/#how-it-works"}, "How it works"),
                h.A({"href": "/changelog"}, "What's new"),
                h.A({"href": "/login", "class": "btn btn-secondary"}, "Log in"),
            ),
        ),
    )


def _site_footer() -> h.Element:
    """Render the shared site footer for legal pages."""
    return h.Footer(
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
                h.A({"href": "/login"}, "Log in"),
            ),
        ),
    )


def _section(title: str, *paragraphs) -> h.Element:
    """Plain strings become <p>; pass an element to embed links/lists."""
    return h.Section(
        {"class": "legal-section"},
        h.H2(title),
        *[h.P(p) if isinstance(p, str) else p for p in paragraphs],
    )


def _legal_page(*, title: str, eyebrow: str, heading: str, updated: str,
                sections: list[h.Element]) -> h.Element:
    """Assemble a legal page document from its sections."""
    return h.HtmlDocument(
        {"lang": "en"},
        document_head(title),
        h.Body(
            h.A({"class": "skip-link", "href": "#main"}, "Skip to content"),
            _site_header(),
            h.Main(
                {"id": "main"},
                h.Section(
                    {"class": "container section-block legal-page",
                     "aria-labelledby": "legal-heading"},
                    h.P({"class": "eyebrow"}, eyebrow),
                    h.H1({"id": "legal-heading"}, heading),
                    h.P({"class": "legal-updated"}, f"Last updated: {updated}"),
                    h.Div({"class": "legal-body"}, *sections),
                ),
            ),
            _site_footer(),
        ),
    )


def render_privacy_page() -> h.Element:
    """Render the privacy policy page."""
    return _legal_page(
        title="Privacy Policy — ShipSwipe",
        eyebrow="Legal",
        heading="Privacy Policy",
        updated="September 11, 2026",
        sections=[
            _section(
                "What we store",
                "Your email address — it's how you sign in. ShipSwipe has no "
                "passwords: we email you a magic link and that link proves it's you.",
                "Your profile — the fields you fill in yourself: your name, whether "
                "you're a builder or a marketer, your bio, what you're building, the "
                "partner you're looking for, your preferred partnership terms, and "
                "any tags you add.",
                "Your activity — the swipes you make (rejects and interested), the "
                "matches you belong to, and the intro messages you send.",
            ),
            _section(
                "What we email you",
                "Sign-in links when you ask for them, and a notice when you get a "
                "new match or an intro message. That's the whole list — we don't run "
                "a newsletter or marketing list.",
            ),
            _section(
                "What we never do",
                "We do not sell your personal data, and we do not share it with "
                "advertisers. Your email address is never shown to other members — "
                "they see your profile, and contact details are exchanged only when "
                "you both connect.",
            ),
            _section(
                "Your data, your controls",
                h.P(
                    "You can download everything we hold about you at any time: "
                    "open ",
                    h.A({"href": "/profile"}, "your profile page"),
                    " and use “Download my data”, or fetch it directly from ",
                    h.A({"href": "/account/export"}, "/account/export"),
                    " while signed in. You get a JSON file with your account, "
                    "profile, swipes, matches, and messages.",
                ),
                h.P(
                    "You can delete your account from the same ",
                    h.A({"href": "/profile"}, "profile page"),
                    ". Deletion removes your profile, tags, swipes, matches, and "
                    "messages, and signs you out. It's permanent — there's no undo.",
                ),
            ),
            _section(
                "Where the data lives",
                "Account and profile data is stored in our database on our server; "
                "sign-in sessions live in Redis and expire after 30 days. Magic "
                "sign-in links are single-use and expire quickly.",
            ),
            _section(
                "Questions",
                "Anything about your data — export, deletion, correction, or a "
                "question this page didn't answer — email "
                f"{settings.contact_email} and we'll sort it out.",
            ),
        ],
    )


def render_terms_page() -> h.Element:
    """Render the terms of service page."""
    return _legal_page(
        title="Terms of Service — ShipSwipe",
        eyebrow="Legal",
        heading="Terms of Service",
        updated="September 11, 2026",
        sections=[
            _section(
                "The service",
                "ShipSwipe is a members-only matching network for product builders "
                "and growth marketers. You create a profile, review members on the "
                "opposite side, mark the ones you're interested in, and when the "
                "interest is mutual you can connect and exchange intros.",
            ),
            _section(
                "No guarantee of a partnership",
                "We make the introduction; we don't make the deal. We don't vet, "
                "verify, endorse, or guarantee any member, partnership, or outcome. "
                "Whatever you agree with a match — rev-share, equity, paid work — is "
                "between you and them. Do your own diligence before you commit.",
            ),
            _section(
                "House rules",
                "Keep your profile accurate and your conduct lawful and respectful. "
                "No scraping or bulk-downloading member data, no harvesting contact "
                "details, no spam, no harassment, no fake identities, and no using "
                "ShipSwipe to pitch anything illegal or deceptive.",
            ),
            _section(
                "Accounts",
                "You need an account to use the app, and you're responsible for "
                "what happens under yours. We can suspend or delete accounts that "
                "break these rules or harm other members — with or without warning "
                "when the abuse is clear.",
            ),
            _section(
                "Provided as is",
                "ShipSwipe is provided “as is”, without warranties of any kind. To "
                "the extent the law allows, we're not liable for lost profits, lost "
                "data, or what a match does or doesn't do. These terms are governed "
                "by the laws of England and Wales.",
            ),
            _section(
                "Changes and contact",
                "If these terms change we'll update this page; continuing to use "
                "ShipSwipe after a change means you accept the new terms. Questions "
                f"go to {settings.contact_email}.",
            ),
        ],
    )
