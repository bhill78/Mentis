"""QUIET CHAT IS WHAT MENTIS OPENS ON; Fluid is the explicit legacy route.

Owner, 2026-11-20: "Quiet Chat is now Mentis's primary interface. Fluid is
legacy. I want Mentis to open directly into Quiet Chat, not Fluid."

Every address is served the same page; `apps/fluid-web/src/entry.ts` decides
what it mounts, and `apps/fluid-web/tests/entry_unit.ts` checks that function
whole. What is checked HERE is the thing itself, in a browser against the real
routes of a disposable fixture Brain:

  - `/` (the address the launcher opens) mounts Quiet Chat, at `/`, with no
    Fluid shell under it;
  - existing `/quiet2` links are untouched;
  - `/fluid` is still Fluid, with its own deep links;
  - a Fluid link that was saved at `/` is handed to `/fluid` with its
    destination, once, and Back does not bounce;
  - an unknown address is not sent to Quiet Chat;
  - a conversation link survives a refresh at either Quiet address.

Build apps/fluid-web first, then opt in with MENTIS_QUIET_BROWSER=1.
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit

import pytest

from mentis.conversation import text
from tests._loop import world  # noqa: F401
from tests.conftest import owner_headers

pytestmark = pytest.mark.skipif(
    os.environ.get("MENTIS_QUIET_BROWSER") != "1",
    reason="build the UI (apps/fluid-web) and set MENTIS_QUIET_BROWSER=1",
)

MS = 20000
#: Quiet Chat's own top bar (in the page; a narrow or loading layout may hide it), and Fluid's
#: own shell. Neither interface draws the other's.
QUIET, FLUID = ".q2-top-brain", ".fw-shell.fx"


@pytest.fixture
def places(world):
    cv, owner = world["cv"], world["who"]["@brian"]
    one = cv.open_conversation("Default interface: one", about="The first.")
    two = cv.open_conversation("Default interface: two", about="The second.")
    for c in (one, two):
        cv.join(owner, c)
    cv.say(one, owner, [text("A post in the first conversation.")])
    cv.say(two, owner, [text("A post in the second conversation.")])
    return {"one": one, "two": two}


@pytest.fixture
def page(world):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        context.set_extra_http_headers(owner_headers())
        pg = context.new_page()
        pg.errors = []
        pg.on("pageerror", lambda e: pg.errors.append(str(e)))
        try:
            yield pg
        finally:
            browser.close()


def where(page):
    u = urlsplit(page.url)
    return u.path, u.query, u.fragment


def is_quiet(page):
    page.locator(QUIET).first.wait_for(state="attached", timeout=MS)
    assert page.locator(FLUID).count() == 0, "Fluid's shell is drawn under Quiet Chat"


def is_fluid(page):
    page.locator(FLUID).wait_for(timeout=MS)
    assert page.locator(QUIET).count() == 0, "Quiet Chat is drawn at a Fluid address"


def test_the_root_is_quiet_chat_itself(world, places, page):
    page.goto(world["base"] + "/")
    is_quiet(page)
    assert where(page)[0] == "/", "the root was sent somewhere else instead of opening Quiet Chat"
    # the conversation it is asked for, and still that one after a refresh
    page.goto(world["base"] + "/?c=" + places["two"])
    is_quiet(page)
    page.get_by_text("A post in the second conversation.", exact=True).wait_for(timeout=MS)
    assert where(page)[0] == "/"
    page.reload()
    is_quiet(page)
    page.get_by_text("A post in the second conversation.", exact=True).wait_for(timeout=MS)
    assert page.get_by_text("A post in the first conversation.", exact=True).count() == 0
    assert page.errors == []


def test_existing_quiet_links_are_untouched(world, places, page):
    page.goto(world["base"] + "/quiet2?c=" + places["one"])
    is_quiet(page)
    page.get_by_text("A post in the first conversation.", exact=True).wait_for(timeout=MS)
    assert where(page)[0] == "/quiet2"
    page.reload()
    is_quiet(page)
    page.get_by_text("A post in the first conversation.", exact=True).wait_for(timeout=MS)
    assert where(page)[0] == "/quiet2"
    assert page.errors == []


def test_fluid_stays_at_its_own_route(world, places, page):
    page.goto(world["base"] + "/fluid")
    is_fluid(page)
    assert where(page)[0] == "/fluid"
    page.goto(world["base"] + "/fluid?c=" + places["two"])
    is_fluid(page)
    page.get_by_text("A post in the second conversation.", exact=True).first.wait_for(timeout=MS)
    assert where(page)[0] == "/fluid" and places["two"] in where(page)[1]
    assert page.errors == []


@pytest.mark.parametrize("saved, lands", [
    ("/?gov=1", ("/fluid", "gov=1", "")),
    ("/?home=1", ("/fluid", "home=1", "")),
    ("/#/brain/space", ("/fluid", "", "/brain/space")),
])
def test_a_fluid_link_saved_at_the_root_keeps_its_destination(world, page, saved, lands):
    page.goto("about:blank")
    page.goto(world["base"] + saved)
    is_fluid(page)
    path, query, fragment = where(page)
    assert path == lands[0]
    assert lands[1] in query and fragment == lands[2], (path, query, fragment)
    # ONCE: it settles, and going Back leaves instead of bouncing through the root again.
    page.wait_for_timeout(1500)
    assert where(page)[0] == "/fluid"
    page.go_back()
    assert page.url == "about:blank", page.url
    assert page.errors == []


def test_a_topic_link_saved_at_the_root_opens_in_fluid_with_its_topic(world, places, page):
    page.goto(world["base"] + "/?c=" + places["one"] + "&t=ent-not-a-topic")
    is_fluid(page)
    path, query, _ = where(page)
    assert path == "/fluid" and places["one"] in query


def test_an_unknown_address_is_not_sent_to_quiet_chat(world, page):
    for path in ("/nonsense", "/quiet2/extra"):
        page.goto(world["base"] + path)
        is_fluid(page)          # what these addresses opened before, unchanged
