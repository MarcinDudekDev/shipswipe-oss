"""Checkpoint 26 — trust/legal floor.

Public legal pages (/privacy, /terms) linked from every footer, GDPR self-serve
(/account/export JSON download, /account/delete with confirm), and crawlable
robots.txt + sitemap.xml served by the app itself.
"""

import json
import uuid

import sqlalchemy as sa

from conftest import (
    login, make_profile, profile_for_email, seed_like, seed_match,
    seed_user_profile,
)


# ---------- public legal pages ----------

async def test_privacy_page_is_public(client):
    r = await client.get("/privacy")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    assert 'lang="en"' in r.text
    assert r.text.count("<h1") == 1
    # real content, not lorem
    assert "email" in r.text.lower()
    assert "sell" in r.text.lower()


async def test_terms_page_is_public(client):
    r = await client.get("/terms")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    assert 'lang="en"' in r.text
    assert r.text.count("<h1") == 1
    assert "Terms" in r.text


async def test_landing_footer_links_legal_pages(client):
    r = await client.get("/")
    assert r.status_code == 200
    assert 'href="/privacy"' in r.text
    assert 'href="/terms"' in r.text


async def test_changelog_and_login_footers_link_legal_pages(client):
    for path in ("/changelog", "/login"):
        r = await client.get(path)
        assert r.status_code == 200, path
        assert 'href="/privacy"' in r.text, path
        assert 'href="/terms"' in r.text, path


# ---------- robots + sitemap ----------

async def test_robots_txt(client):
    r = await client.get("/robots.txt")
    assert r.status_code == 200
    assert "User-agent: *" in r.text
    assert "Allow: /" in r.text
    assert "Sitemap:" in r.text
    # absolute sitemap URL built from BASE_URL, never localhost-relative
    from config import settings

    base = settings.base_url.rstrip("/")
    assert f"Sitemap: {base}/sitemap.xml" in r.text


async def test_sitemap_xml_lists_public_pages_only(client):
    r = await client.get("/sitemap.xml")
    assert r.status_code == 200
    assert "xml" in r.headers.get("content-type", "")

    from config import settings

    base = settings.base_url.rstrip("/")
    assert f"<loc>{base}/</loc>" in r.text
    for path in ("/login", "/changelog", "/privacy", "/terms"):
        assert f"<loc>{base}{path}</loc>" in r.text
    # login-gated members' pages are not advertised to crawlers
    for gated in ("/discover", "/matches", "/profile", "/account"):
        assert f"{base}{gated}" not in r.text


# ---------- GDPR export ----------

async def test_export_requires_auth(client):
    r = await client.get("/account/export")
    assert r.status_code in (401, 403)


async def test_export_contains_own_data(client, db):
    email = f"{uuid.uuid4().hex}@example.com"
    await login(client, email)
    await make_profile(client, name="Export Me", tags="React,SEO")

    r = await client.get("/account/export")
    assert r.status_code == 200
    assert "application/json" in r.headers.get("content-type", "")
    assert "attachment" in r.headers.get("content-disposition", "")

    data = json.loads(r.text)
    assert data["user"]["email"] == email
    assert data["profile"]["name"] == "Export Me"
    assert data["profile"]["role"] == "builder"
    assert sorted(data["tags"]) == ["React", "SEO"]


async def test_export_includes_swipes_matches_messages(client, db):
    """Export carries the user's activity; partner's email must never leak."""
    from models import Message, User

    email = f"{uuid.uuid4().hex}@example.com"
    await login(client, email)
    await make_profile(client, name="ActiveUser")
    me = await profile_for_email(db, email)

    partner = await seed_user_profile(db, role="marketer", name="PartnerOne")
    partner_email = (
        await db.execute(sa.select(User.email).where(User.id == partner.user_id))
    ).scalar_one()

    match = await seed_match(db, me.id, partner.id)
    await seed_like(db, me.id, partner.id)
    db.add(Message(match_id=match.id, sender_profile_id=me.id, body="let's ship"))
    await db.commit()

    r = await client.get("/account/export")
    assert r.status_code == 200
    data = json.loads(r.text)
    assert data["user"]["email"] == email
    assert len(data["swipes"]) == 1 and data["swipes"][0]["direction"] == "like"
    assert len(data["matches"]) == 1
    assert len(data["messages"]) == 1 and data["messages"][0]["body"] == "let's ship"
    assert partner_email not in r.text


# ---------- GDPR delete ----------

async def test_delete_requires_auth(client):
    r = await client.post("/account/delete", data={"confirm": "DELETE"})
    assert r.status_code in (401, 403)


async def test_delete_requires_typed_confirm(client, db):
    """A bare POST must not nuke the account — the confirm word is required."""
    email = f"{uuid.uuid4().hex}@example.com"
    await login(client, email)
    await make_profile(client, name="CarefulUser")

    r = await client.post("/account/delete", data={"confirm": "nope"})
    assert r.status_code in (400, 422)

    from models import User

    still_there = (
        await db.execute(sa.select(User).where(User.email == email))
    ).scalar_one_or_none()
    assert still_there is not None


async def test_delete_removes_everything_and_relocks_pages(client, db):
    from models import Match, Message, ProfileTag, Swipe, User

    email = f"{uuid.uuid4().hex}@example.com"
    await login(client, email)
    await make_profile(client, name="Soon Gone", tags="React")
    me = await profile_for_email(db, email)

    partner = await seed_user_profile(db, role="marketer", name="SurvivingPartner")
    match = await seed_match(db, me.id, partner.id)
    await seed_like(db, me.id, partner.id)     # my swipe on them
    await seed_like(db, partner.id, me.id)     # their swipe on me (FK target)
    db.add(Message(match_id=match.id, sender_profile_id=me.id, body="bye"))
    db.add(Message(match_id=match.id, sender_profile_id=partner.id, body="ok"))
    await db.commit()

    r = await client.post("/account/delete", data={"confirm": "DELETE"})
    assert r.status_code in (200, 302, 303)

    # every row the account owned (or that referenced its profile) is gone;
    # the partner's user row survives — only the shared match data dies.
    partner_user = (
        await db.execute(sa.select(User).where(User.id == partner.user_id))
    ).scalar_one_or_none()
    assert partner_user is not None

    gone = (
        await db.execute(sa.select(User).where(User.email == email))
    ).scalar_one_or_none()
    assert gone is None
    assert (await db.execute(
        sa.select(sa.func.count()).select_from(ProfileTag))).scalar() == 0
    assert (await db.execute(
        sa.select(sa.func.count()).select_from(Swipe))).scalar() == 0
    assert (await db.execute(
        sa.select(sa.func.count()).select_from(Match))).scalar() == 0
    assert (await db.execute(
        sa.select(sa.func.count()).select_from(Message))).scalar() == 0
    assert await profile_for_email(db, email) is None

    # profile page is gated again — the session is dead
    r = await client.get("/profile")
    assert r.status_code in (401, 403)


async def test_profile_page_has_export_and_delete_controls(client):
    email = f"{uuid.uuid4().hex}@example.com"
    await login(client, email)
    r = await client.get("/profile")
    assert r.status_code == 200
    assert "/account/export" in r.text
    assert "/account/delete" in r.text
