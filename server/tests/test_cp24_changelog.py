"""Checkpoint 24 — public product-updates / changelog page.

GET /changelog is PUBLIC (no login) and lists shipped releases so early users
can see what changed and we can track updates over time.
"""


async def test_changelog_is_public(client):
    r = await client.get("/changelog")
    assert r.status_code == 200
    assert "What's new" in r.text


async def test_changelog_lists_recent_shipped_changes(client):
    r = await client.get("/changelog")
    body = r.text
    # the two things we just shipped from early-user feedback
    assert "Interested" in body
    assert "Reconsider" in body
    assert "Reject" in body


async def test_changelog_linked_from_landing(client):
    # header nav + footer both point at it (crawlable internal links)
    r = await client.get("/")
    assert r.status_code == 200
    assert r.text.count("/changelog") >= 2


async def test_changelog_linked_from_login(client):
    r = await client.get("/login")
    assert r.status_code == 200
    assert "/changelog" in r.text
