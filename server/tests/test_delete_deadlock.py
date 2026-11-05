"""Account deletion never deadlocks with swipes that touch the same profile.

A single racer is not enough to expose lock-order bugs, so each trial fires the
delete together with the partner re-liking a profile they had passed on (an
existing swipe row), the owner saving their profile and the owner swiping.
"""

import asyncio
import uuid

from conftest import login, make_profile, profile_for_email, seed_user_profile


def _email() -> str:
    return f"{uuid.uuid4().hex}@example.com"


async def test_delete_with_many_racers_never_crashes(db, schema):
    import main
    from stario.testing import TestClient

    failures = []
    for trial in range(15):
        async with TestClient(main.bootstrap) as a, TestClient(main.bootstrap) as b:
            ea, eb = _email(), _email()
            await login(a, ea)
            await make_profile(a, role="builder", name="A")
            await login(b, eb)
            await make_profile(b, role="marketer", name="B")
            ida = (await profile_for_email(db, ea)).id
            idb = (await profile_for_email(db, eb)).id
            third = (await seed_user_profile(db, "marketer", "C")).id
            await b.post("/swipe", data={"target_id": str(ida), "direction": "pass"})
            await a.post("/swipe", data={"target_id": str(idb), "direction": "like"})
            rs = await asyncio.gather(
                a.post("/account/delete", data={"confirm": "DELETE"}),
                b.post("/swipe", data={"target_id": str(ida), "direction": "like"}),
                b.post("/swipe", data={"target_id": str(ida), "direction": "like"}),
                a.post("/profile", data={"role": "builder", "name": "A", "bio": "b",
                                         "building": "x", "looking_for": "y",
                                         "terms": "rev-share", "tags": "a,b"}),
                a.post("/swipe", data={"target_id": str(third), "direction": "like"}),
            )
            codes = [r.status_code for r in rs]
            if any(c >= 500 for c in codes):
                failures.append((trial, codes))
    assert failures == [], failures
