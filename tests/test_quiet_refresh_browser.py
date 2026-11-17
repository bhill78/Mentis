"""THE CONVERSATION FOLLOWS THE RECORD: an agent's post appears where it is
being read, without a reload.

The defect (owner, 2026-11-17): "The conversation UI doesn't always refresh
after an agent finishes a run and posts." Quiet Chat Mark 2's flow
(`quiet2/real.ts`, `useRealFlow`) read a conversation when it was opened,
when the reader posted in it themself and when they renamed it -- and at no
other time. Everything else in the interface hears the record move on the
pulse (`/api/pulse`, `fluid/identity/activity.ts`); the flow did not, so an
agent's post sat in the Brain unseen until something else made the page read
again. Measured at the base of this work (d07b1c8): after a post was written
into the conversation on screen, the page asked for the change feed and the
conversation list and NEVER for `/api/conversations/<id>?batch=30`, and the
post had not appeared twelve seconds later.

What is checked here, against real Mentis HTTP routes on a disposable fixture
Brain, in the browsers the owner uses (Chrome and Edge):

  - a post written while the page is open appears, without a reload;
  - THE FINAL POST AFTER THE RUN FINISHES: the run's live half moves when it
    ends and the post lands durably a moment later, so following the live
    half alone is not enough -- this is the owner's own case;
  - A MISSED COMPLETION: pulse beats are dropped across the moment the post
    is written, and the post still arrives once a beat gets through;
  - the reader is not disturbed: an unsent draft, the scroll position, the
    conversation shown and the posts already read above all survive a
    refresh, and a post in ANOTHER conversation changes nothing here;
  - CONVERSATION SWITCHING: the flow follows the conversation now read, not
    the one it was opened on, and a post written while it was away is there
    on return.

No live Brain and no MARS: the fixture Brain of `tests/_loop.py`, whose runs
are `FakeExecution`'s. Build apps/fluid-web first, then opt in with
MENTIS_QUIET_BROWSER=1.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from mentis.conversation import text
from tests._loop import world  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.environ.get("MENTIS_QUIET_BROWSER") != "1",
    reason="build the UI (apps/fluid-web) and set MENTIS_QUIET_BROWSER=1",
)

#: THE BROWSERS THE OWNER TESTS IN on this machine, as Playwright's Chromium
#: channels. WebKit is not asked for here (and is skipped by default --
#: conftest, opr-74d4f3d5f15a).
ENGINES = ["chrome", "msedge"]

#: How long a post written into the Brain may take to appear. The pulse beat
#: is 1.2 s and the flow spaces its own rereads at 1.5 s, so a second or two
#: is the expectation; this is the bound at which it has not happened.
APPEARS_MS = 15000


@pytest.fixture
def flow(world):
    """One conversation being read, one elsewhere, and a carrier to post as."""
    cv, owner, care = world["cv"], world["who"]["@brian"], world["steward"]
    here = cv.open_conversation("Refresh browser: here",
                                about="Where the reader is.")
    elsewhere = cv.open_conversation("Refresh browser: elsewhere",
                                     about="Somewhere else entirely.")
    cv.join(owner, here)
    cv.join(owner, elsewhere)
    cv.join(care, here)
    cv.join(care, elsewhere)
    cv.say(here, owner, [text("Please look into the gate.")])
    cv.say(elsewhere, owner, [text("A note somewhere else.")])
    return {"here": here, "elsewhere": elsewhere, "owner": owner, "care": care}


def _page(playwright, engine, width=1440, height=1000):
    """A page in the owner's browser, with whatever it throws kept."""
    browser = playwright.chromium.launch(channel=engine)
    page = browser.new_page(viewport={"width": width, "height": height})
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    return browser, page, errors


def _open(page, world, conversation, opening):
    """Quiet Chat Mark 2 (`/quiet2`), reading `conversation`."""
    page.goto(world["base"] + f"/quiet2?c={conversation}")
    page.get_by_text(opening, exact=True).wait_for()
    return page


def _said(cv, conversation, by, words, replies_to=None):
    return cv.say(conversation, by, [text(words)], replies_to=replies_to)


def _composer(page):
    """The conversation's composer, open on its draft."""
    box = page.locator(".q2-dock textarea")
    if not box.count():
        page.locator(".q2-dock .fc-unfold").click()
    box.first.wait_for()
    return box.first


def _run_of(world, conversation, carrier, instance="inst-refresh"):
    """A run as dispatch opens it: its start act, held by this process."""
    cv, st = world["cv"], world["state"]
    run = cv.record_act(actor=carrier, act="execution-started",
                        conversation=conversation, turn=None,
                        execution=instance, runtime="claude",
                        because="test run")
    st.agents.agents_open_run(instance, run)
    st.agents._runs[run]["feed"].add(
        "tool_call", {"tool_call_id": "t1", "title": "Read the gate",
                      "kind": "read", "status": "in_progress"}, time.time())
    return run


@pytest.mark.parametrize("engine", ENGINES)
def test_an_agents_post_appears_without_a_reload(world, flow, engine):
    playwright = pytest.importorskip("playwright.sync_api")
    assert (Path(__file__).parents[1] / "apps/fluid-web/dist/index.html").exists()
    cv = world["cv"]
    with playwright.sync_playwright() as p:
        browser, page, errors = _page(p, engine)
        try:
            _open(page, world, flow["here"], "Please look into the gate.")
            loads = page.evaluate("() => performance.getEntriesByType('navigation').length")
            assert page.locator(".q2-post").count() == 1

            _said(cv, flow["here"], flow["care"],
                  "Looked into the gate: here is what I found.")
            page.get_by_text("Looked into the gate: here is what I found.",
                             exact=True).wait_for(timeout=APPEARS_MS)

            # It appeared because the page read again, not because it reloaded.
            assert page.evaluate(
                "() => performance.getEntriesByType('navigation').length") == loads
            assert page.locator(".q2-post").count() == 2
            assert not errors, errors
        finally:
            browser.close()


@pytest.mark.parametrize("engine", ENGINES)
def test_the_final_post_after_the_run_finishes(world, flow, engine):
    """The run ends (the pulse's live half), and only then is its answer in
    the record (the durable half). Following the live half alone would show
    the work go and never the answer; this is the owner's own case."""
    playwright = pytest.importorskip("playwright.sync_api")
    cv, st = world["cv"], world["state"]
    with playwright.sync_playwright() as p:
        browser, page, errors = _page(p, engine)
        try:
            _open(page, world, flow["here"], "Please look into the gate.")

            run = _run_of(world, flow["here"], flow["care"])
            # the page sees somebody working (the live half of the pulse)
            page.locator(".q2-foot-agents .q2-foot-agent").first.wait_for(timeout=APPEARS_MS)

            # it finishes, and its answer is written a moment after
            st.agents.agents_end_run(run)
            page.wait_for_timeout(2000)
            _said(cv, flow["here"], flow["care"],
                  "The gate is closed; the slower check was dropped.")

            page.get_by_text("The gate is closed; the slower check was dropped.",
                             exact=True).wait_for(timeout=APPEARS_MS)
            assert not errors, errors
        finally:
            browser.close()


@pytest.mark.parametrize("engine", ENGINES)
def test_a_missed_pulse_still_brings_the_post(world, flow, engine):
    """A MISSED COMPLETION. Every beat across the moment of the post is
    dropped -- the server was busy, the network blinked. A gap in asking is
    not a change in the record: the first beat that gets through still finds
    the move, and the post arrives."""
    playwright = pytest.importorskip("playwright.sync_api")
    cv = world["cv"]
    with playwright.sync_playwright() as p:
        browser, page, errors = _page(p, engine)
        try:
            _open(page, world, flow["here"], "Please look into the gate.")
            page.route("**/api/pulse*", lambda route: route.abort())
            page.wait_for_timeout(1000)

            _said(cv, flow["here"], flow["care"], "Written while the beats were lost.")
            page.wait_for_timeout(4000)
            assert page.get_by_text("Written while the beats were lost.",
                                    exact=True).count() == 0

            page.unroute("**/api/pulse*")
            page.get_by_text("Written while the beats were lost.",
                             exact=True).wait_for(timeout=APPEARS_MS + 10000)
            assert not errors, errors
        finally:
            browser.close()


@pytest.mark.parametrize("engine", ENGINES)
def test_a_refresh_keeps_the_draft_the_place_and_the_posts_above(world, flow, engine):
    """Nothing the reader was doing is disturbed: the draft they are writing,
    where they are scrolled, the conversation shown, and the posts already
    read above -- a flow is read as its LATEST batch, so reading it again
    would otherwise drop the oldest of them out from above. And a post
    somewhere else does not touch this conversation at all."""
    playwright = pytest.importorskip("playwright.sync_api")
    cv = world["cv"]
    owner, care = flow["owner"], flow["care"]
    for n in range(40):
        _said(cv, flow["here"], owner, f"Filler note {n}, with words enough to scroll.")
    with playwright.sync_playwright() as p:
        browser, page, errors = _page(p, engine, height=900)
        try:
            page.goto(world["base"] + f"/quiet2?c={flow['here']}")
            page.get_by_text("Filler note 39, with words enough to scroll.", exact=True).wait_for()
            # read as the latest batch: 30 threads of the 41 posts
            posts = page.locator(".q2-post").count()
            assert posts == 30, posts
            # the oldest post read: it must not drop out from above on a reread
            oldest = page.locator(".q2-post").first.get_attribute("data-post")

            draft = "A draft nobody has sent yet."
            _composer(page).fill(draft)
            page.locator(".q2-conv").evaluate("e => { e.scrollTop = 300 }")
            page.wait_for_timeout(200)
            was = page.locator(".q2-conv").evaluate("e => e.scrollTop")

            # A POST SOMEWHERE ELSE: nothing here changes.
            _said(cv, flow["elsewhere"], care, "An answer in the other conversation.")
            page.wait_for_timeout(5000)
            assert page.get_by_text("An answer in the other conversation.", exact=True).count() == 0
            assert page.locator(".q2-post").count() == posts
            assert _composer(page).input_value() == draft

            # A POST HERE: it appears, with everything above it still there.
            _said(cv, flow["here"], care, "An answer in this conversation.")
            page.get_by_text("An answer in this conversation.", exact=True).wait_for(timeout=APPEARS_MS)
            assert page.locator(".q2-post").count() == posts + 1
            assert page.locator(".q2-post").first.get_attribute("data-post") == oldest
            assert _composer(page).input_value() == draft
            assert page.get_by_role("heading", name="Refresh browser: here", exact=True).count() == 1
            now = page.locator(".q2-conv").evaluate("e => e.scrollTop")
            assert abs(now - was) < 40, (was, now)
            assert not errors, errors
        finally:
            browser.close()


@pytest.mark.parametrize("engine", ENGINES)
def test_switching_conversations_follows_the_one_now_read(world, flow, engine):
    """The flow follows the conversation shown, not the one it was opened on."""
    playwright = pytest.importorskip("playwright.sync_api")
    cv, care = world["cv"], flow["care"]
    with playwright.sync_playwright() as p:
        browser, page, errors = _page(p, engine)
        try:
            _open(page, world, flow["here"], "Please look into the gate.")
            _open(page, world, flow["elsewhere"], "A note somewhere else.")

            # written in the conversation now read: it appears
            _said(cv, flow["elsewhere"], care, "An answer where the reader now is.")
            page.get_by_text("An answer where the reader now is.", exact=True).wait_for(timeout=APPEARS_MS)
            # written in the one left behind: not drawn here
            _said(cv, flow["here"], care, "An answer where the reader was.")
            page.wait_for_timeout(4000)
            assert page.get_by_text("An answer where the reader was.", exact=True).count() == 0

            # and it is there on return, with the other conversation's gone
            _open(page, world, flow["here"], "An answer where the reader was.")
            assert page.get_by_text("An answer where the reader now is.", exact=True).count() == 0
            assert not errors, errors
        finally:
            browser.close()
