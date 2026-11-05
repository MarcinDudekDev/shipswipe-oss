"""ShipSwipe — Stario backend entry point.

Run (dev):   uv run stario watch main:bootstrap --port 8787
Run (prod):  uv run stario serve main:bootstrap --unix-socket /run/shipswipe.sock

Serves the members-only matching app: magic-link auth, the swipe deck,
matches and intros, and the account endpoints (export/delete).
"""

import dataclasses
from pathlib import Path

from stario import App, Context, Span, StaticAssets, Writer, html as h, responses
from stario import datastar as ds

from auth.middleware import set_baseline_headers
from config import settings

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
_og_url = settings.base_url.rstrip("/") + "/"
_og_image_url = settings.base_url.rstrip("/") + "/og-image.png"
_OG_IMAGE_BYTES: bytes | None = None


def _og_image_bytes() -> bytes:
    """Return the cached OG share image bytes, reading the file once."""
    global _OG_IMAGE_BYTES
    if _OG_IMAGE_BYTES is None:
        _OG_IMAGE_BYTES = (STATIC_DIR / "og-cover.png").read_bytes()
    return _OG_IMAGE_BYTES


def _role_pill(role: str, label: str) -> h.Element:
    """One side-choice radio styled as a pill; bound to the reactive $role signal."""
    return h.Label(
        ds.class_("selected", f"$role === '{role}'"),
        {"class": "role-pill"},
        h.Input(
            ds.bind("role"),
            {"type": "radio", "name": "role", "value": role, "class": "role-pill-input"},
        ),
        label,
    )


def _register_form() -> h.Element:
    """Reactive registration: side -> name -> email -> POST /auth/request-link.

    Datastar adjusts the copy live to the chosen side, then submitting sends the
    magic link (the chosen role + name ride along and become the profile on verify).
    """
    looking_for = (
        "$role === 'builder' "
        "? 'You build it — find a marketer to grow it.' "
        ": 'You grow it — find a builder worth promoting.'"
    )
    return h.Section(
        ds.signals({"role": "builder", "name": "", "email": "", "sent": False}),
        {"id": "signin", "class": "panel register-card", "aria-labelledby": "register-heading"},
        h.Form(
            ds.on("submit", "@post('/auth/request-link'); $sent = true", prevent=True),
            ds.show("!$sent"),
            {"class": "register-form"},
            h.H2({"id": "register-heading"}, "Create your account"),
            h.Fieldset(
                {"class": "role-fieldset"},
                h.Legend("I'm a…"),
                h.Div(
                    {"class": "role-pills", "role": "radiogroup"},
                    _role_pill("builder", "Builder"),
                    _role_pill("marketer", "Marketer"),
                ),
            ),
            h.P({"class": "register-reactive", "data-text": looking_for}),
            h.Div(
                {"class": "form-field"},
                h.Label({"for": "reg-name"}, "Your name"),
                h.Input(
                    ds.bind("name"),
                    {
                        "type": "text", "name": "name", "id": "reg-name",
                        "required": True, "autocomplete": "name", "placeholder": "Alex Rivera",
                    },
                ),
            ),
            h.Div(
                {"class": "form-field"},
                h.Label({"for": "reg-email"}, "Email"),
                h.Input(
                    ds.bind("email"),
                    {
                        "type": "email", "name": "email", "id": "reg-email",
                        "required": True, "autocomplete": "email", "placeholder": "you@example.com",
                    },
                ),
            ),
            h.Button(
                {"type": "submit", "class": "btn btn-primary cta register-submit"},
                "Join as a ", h.Span({"data-text": "$role"}), " →",
            ),
            h.P({"class": "register-fineprint"}, "No password — we email you a magic sign-in link."),
        ),
        h.P(
            ds.show("$sent"),
            {"class": "signin-sent", "role": "status", "style": "display:none"},
            "Check your inbox — your ShipSwipe sign-in link is on its way.",
        ),
        h.P(
            {"class": "register-alt"},
            "Already have an account? ",
            h.A({"href": "/login"}, "Log in →"),
        ),
    )


def _stat(value: int, label: str, key: str) -> h.Element:
    """Render one animated landing-page stat counter."""
    return h.Div(
        {"class": "stat"},
        h.P({"class": "stat-value", "data-stat": key}, str(value)),
        h.P({"class": "stat-label"}, label),
    )


def _landing_page(stats: dict[str, int]) -> h.Element:
    """Render the full public landing document."""
    return h.HtmlDocument(
        {"lang": "en"},
        h.Head(
            h.Meta({"charset": "UTF-8"}),
            h.Meta({"name": "viewport", "content": "width=device-width, initial-scale=1.0"}),
            h.Meta(
                {
                    "name": "description",
                    "content": "ShipSwipe pairs product builders with growth marketers. "
                    "Sign in, swipe to match, and connect with your launch partner.",
                }
            ),
            h.Meta({"property": "og:title", "content": "ShipSwipe — You build it. They grow it."}),
            h.Meta(
                {
                    "property": "og:description",
                    "content": "Swipe-to-match network pairing product builders with growth marketers — find your launch partner.",
                }
            ),
            h.Meta({"property": "og:type", "content": "website"}),
            h.Meta({"property": "og:url", "content": _og_url}),
            h.Meta({"property": "og:image", "content": _og_image_url}),
            h.Meta({"property": "og:image:width", "content": "1200"}),
            h.Meta({"property": "og:image:height", "content": "630"}),
            h.Meta({"property": "og:image:alt", "content": "ShipSwipe — where builders meet marketers"}),
            h.Meta({"name": "twitter:card", "content": "summary_large_image"}),
            h.Meta({"name": "twitter:image", "content": _og_image_url}),
            h.Title("ShipSwipe — You build it. They grow it."),
            h.Link({"rel": "icon", "href": "/static/favicon.svg", "type": "image/svg+xml"}),
            h.Link({"rel": "icon", "href": "/static/favicon.ico", "sizes": "any"}),
            h.Link({"rel": "apple-touch-icon", "href": "/static/apple-touch-icon.png"}),
            h.Link({"rel": "stylesheet", "href": "/static/styles.css"}),
            ds.ModuleScript("/static/js/datastar.js"),
            h.Script({"src": "/static/js/stats.js", "defer": True}),
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
                        h.A({"href": "#how-it-works"}, "How it works"),
                        h.A({"href": "/changelog"}, "What's new"),
                        h.A({"href": "/login", "class": "btn btn-secondary"}, "Log in"),
                    ),
                ),
            ),
            h.Main(
                {"id": "main"},
                h.Section(
                    {"class": "container hero-simple", "aria-labelledby": "hero-heading"},
                    h.P({"class": "eyebrow"}, "Builder ↔ Marketer matching"),
                    h.H1({"id": "hero-heading"}, "Where builders meet marketers."),
                    h.P(
                        {"class": "hero-tagline"},
                        "The swipe-to-match network that pairs product ",
                        h.Strong("builders"),
                        " with growth ",
                        h.Strong("marketers"),
                        " — find the launch partner your product is missing.",
                    ),
                    _register_form(),
                ),
                h.Section(
                    {"class": "container section-block", "aria-labelledby": "segments-heading"},
                    h.H2({"id": "segments-heading", "class": "section-lead"}, "Two sides, one launch"),
                    h.Div(
                        {"class": "segment-cards"},
                        h.Article(
                            {"class": "segment-card"},
                            h.H2("For builders"),
                            h.P(
                                "Get distribution without hiring an agency — match with a growth "
                                "partner who owns your launch channels and audience reach."
                            ),
                        ),
                        h.Article(
                            {"class": "segment-card"},
                            h.H2("For marketers"),
                            h.P(
                                "Get a vetted product worth promoting on rev-share, equity, paid, "
                                "or flexible terms — skip the cold outreach grind."
                            ),
                        ),
                    ),
                ),
                h.Section(
                    {"class": "container section-block stats-section", "aria-labelledby": "stats-heading"},
                    h.H2({"id": "stats-heading", "class": "section-lead"}, "The matchmaking so far"),
                    h.Div(
                        {"class": "stats-grid"},
                        _stat(stats.get("builders", 0), "Builders", "builders"),
                        _stat(stats.get("marketers", 0), "Marketers", "marketers"),
                        _stat(stats.get("matches", 0), "Matches made", "matches"),
                    ),
                ),
                h.Section(
                    {"class": "container section-block", "id": "how-it-works", "aria-labelledby": "hiw-heading"},
                    h.H2({"id": "hiw-heading"}, "How it works"),
                    h.Ol(
                        {"class": "steps-grid"},
                        h.Li(
                            {"class": "step"},
                            h.H3("Sign in with a magic link"),
                            h.P(
                                "Drop your email above, click the link we send, and create your "
                                "profile — tell us whether you build or grow and what partner you need."
                            ),
                        ),
                        h.Li(
                            {"class": "step"},
                            h.H3("Review the opposite side"),
                            h.P(
                                "Builders see marketers; marketers see builders. Reject the ones "
                                "that don't fit and mark the right partners as interested."
                            ),
                        ),
                        h.Li(
                            {"class": "step"},
                            h.H3("Connect and ship"),
                            h.P(
                                "When you're both interested, you connect. Exchange contact details "
                                "and send an intro to start shipping together."
                            ),
                        ),
                    ),
                ),
                h.Section(
                    {"class": "container section-block proof-section", "aria-labelledby": "proof-heading"},
                    h.H2({"id": "proof-heading"}, "Why founders use ShipSwipe"),
                    h.Div(
                        {"class": "proof-grid"},
                        h.Blockquote(
                            {"class": "proof"},
                            h.P(
                                "\"My B2B invoicing SaaS was stuck at 12 beta users. One match later, "
                                "my growth partner ran SEO that brought 340 signups in 8 weeks.\""
                            ),
                            h.Footer("— Maya C., indie builder"),
                        ),
                        h.Blockquote(
                            {"class": "proof"},
                            h.P(
                                "\"I scale micro-SaaS past $10k MRR but needed a product worth "
                                "promoting. Matched with a builder in 4 days — rev-share on the first call.\""
                            ),
                            h.Footer("— Elena V., growth marketer"),
                        ),
                    ),
                ),
                h.Section(
                    {"class": "container section-block final-cta", "aria-labelledby": "final-cta-heading"},
                    h.H2({"id": "final-cta-heading"}, "Find your launch partner today"),
                    h.P(
                        "Builders and marketers are matching right now. Sign in to create your "
                        "profile and start swiping."
                    ),
                    h.A({"href": "#signin", "class": "btn btn-primary cta"}, "Sign in to start →"),
                ),
            ),
            h.Footer(
                {"class": "site-footer"},
                h.Div(
                    {"class": "container footer-inner"},
                    h.P("ShipSwipe — swipe your way to a builder-marketer partnership."),
                    h.Nav(
                        {"class": "footer-links", "aria-label": "Footer"},
                        h.A({"href": "/#how-it-works"}, "How it works"),
                        h.A({"href": "/changelog"}, "What's new"),
                        h.A({"href": "/privacy"}, "Privacy"),
                        h.A({"href": "/terms"}, "Terms"),
                        h.A({"href": "/login"}, "Log in"),
                    ),
                ),
            ),
        ),
    )


async def home(c: Context, w: Writer) -> None:
    """GET / — render the landing page with live community stats."""
    from db import async_session
    from services.stats import homepage_stats

    async with async_session() as db:
        stats = await homepage_stats(db)
    responses.html(w, _landing_page(stats))


async def api_stats(c: Context, w: Writer) -> None:
    """Live community counts as JSON (polled by the homepage counters)."""
    from db import async_session
    from services.stats import homepage_stats

    async with async_session() as db:
        stats = await homepage_stats(db)
    responses.json(w, stats)


async def changelog(c: Context, w: Writer) -> None:
    """Public product-updates page."""
    from views.changelog import render_changelog_page

    responses.html(w, render_changelog_page())


async def privacy(c: Context, w: Writer) -> None:
    """Public privacy policy."""
    from views.legal import render_privacy_page

    responses.html(w, render_privacy_page())


async def terms(c: Context, w: Writer) -> None:
    """Public terms of service."""
    from views.legal import render_terms_page

    responses.html(w, render_terms_page())


async def robots_txt(c: Context, w: Writer) -> None:
    """Crawler rules + the sitemap pointer (absolute, from BASE_URL)."""
    base = settings.base_url.rstrip("/")
    body = f"User-agent: *\nAllow: /\n\nSitemap: {base}/sitemap.xml\n"
    w.respond(body.encode("utf-8"), b"text/plain; charset=utf-8", 200)


_SITEMAP_PATHS = ("/", "/login", "/changelog", "/privacy", "/terms")


async def sitemap_xml(c: Context, w: Writer) -> None:
    """Public-pages-only sitemap — members' pages stay gated and unlisted."""
    base = settings.base_url.rstrip("/")
    urls = "".join(f"  <url><loc>{base}{p}</loc></url>\n" for p in _SITEMAP_PATHS)
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}</urlset>\n"
    )
    w.respond(body.encode("utf-8"), b"application/xml; charset=utf-8", 200)


async def healthz(c: Context, w: Writer) -> None:
    """GET /healthz — liveness probe for deploys and monitors."""
    responses.json(w, {"status": "ok", "service": "shipswipe-server"})


async def not_found(c: Context, w: Writer) -> None:
    """404 for unrouted paths — route middleware never sees these, so the
    baseline security headers are set here directly."""
    set_baseline_headers(w)
    responses.text(w, "Not Found", status=404)


async def favicon(c: Context, w: Writer) -> None:
    """Browsers probe /favicon.ico directly — point them at the static asset."""
    responses.redirect(w, "/static/favicon.ico", status=308)


async def og_image(c: Context, w: Writer) -> None:
    """Serve the social-share cover directly (stable 200, no fingerprint redirect)."""
    w.respond(_og_image_bytes(), b"image/png")


async def login_get(c: Context, w: Writer) -> None:
    """Email-only magic-link login for returning users."""
    from views.login import render_login_page

    responses.html(w, render_login_page(gated=False))


async def bootstrap(app: App, span: Span) -> None:
    """Register routes, middleware, and static assets on the app."""
    from auth.handlers import logout, request_link, verify, verify_post
    from auth.middleware import load_user, origin_check, security_headers
    from handlers.account import account_delete, account_export
    from handlers.deck import deck, swipe, undo
    from handlers.discover import discover
    from handlers.match import connect, interested, intro, matches, reconsider, rejected
    from handlers.profile import profile_get, profile_post

    span.attr("app.name", "shipswipe-server")
    # Unrouted requests (404s) never enter the route middleware chain, so the
    # router's not_found_handler sets the baseline headers itself. Router's
    # not_found_handler kwarg is the hook for this; the App instance arrives
    # framework-built, so it's wired on the live router before registering
    # routes (new nodes inherit it; the pre-existing root needs replacing).
    app._not_found_handler = not_found
    app.root = dataclasses.replace(app.root, not_found_handler=not_found)
    if settings.app_env == "development":
        # Mail capture swallows every outbound email into an in-memory OUTBOX —
        # fine locally, a silent outage if a real deployment forgets APP_ENV.
        print(
            "WARNING: APP_ENV=development — all outbound mail is captured in "
            "memory (OUTBOX); nothing is actually sent.",
            flush=True,
        )
    # Last pushed is outermost: load_user wraps security_headers so the
    # no-store decision can see c.state["user"], and security_headers wraps
    # origin_check so a refused cross-site POST still gets the baseline
    # headers.
    app.push_middleware(origin_check)
    app.push_middleware(security_headers)
    app.push_middleware(load_user)
    app.get("/", home, name="home")
    app.get("/healthz", healthz, name="healthz")
    app.get("/api/stats", api_stats, name="api_stats")
    app.get("/og-image.png", og_image, name="og_image")
    app.get("/favicon.ico", favicon, name="favicon")
    app.get("/login", login_get, name="login")
    app.get("/changelog", changelog, name="changelog")
    app.get("/privacy", privacy, name="privacy")
    app.get("/terms", terms, name="terms")
    app.get("/robots.txt", robots_txt, name="robots_txt")
    app.get("/sitemap.xml", sitemap_xml, name="sitemap_xml")
    app.get("/discover", discover, name="discover")
    app.post("/auth/request-link", request_link, name="auth_request_link")
    app.get("/auth/verify", verify, name="auth_verify")
    app.post("/auth/verify", verify_post, name="auth_verify_post")
    app.post("/auth/logout", logout, name="auth_logout")
    app.get("/profile", profile_get, name="profile")
    app.post("/profile", profile_post, name="profile_post")
    app.get("/account/export", account_export, name="account_export")
    app.post("/account/delete", account_delete, name="account_delete")
    app.get("/deck", deck, name="deck")
    app.post("/swipe", swipe, name="swipe")
    app.post("/undo", undo, name="undo")
    app.get("/matches", matches, name="matches")
    app.get("/interested", interested, name="interested")
    app.get("/rejected", rejected, name="rejected")
    app.post("/reconsider", reconsider, name="reconsider")
    app.post("/connect", connect, name="connect")
    app.post("/intro", intro, name="intro")
    if STATIC_DIR.is_dir():
        app.mount("/static", StaticAssets(STATIC_DIR, name="static"))
