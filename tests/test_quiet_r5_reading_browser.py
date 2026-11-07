"""QUIET CHAT ROUND 5, PACKAGE R: THE READING COMES BACK.

The owner asked for the reading place to be kept ACROSS SESSIONS IN THIS
BROWSER (opr-8cf7688b6555), so what this file checks is the whole claim end to
end, against real Mentis HTTP routes on a disposable fixture Brain:

* AN OLDER BATCH INSIDE A FILTERED TOPIC comes back -- the topic still
  filtering, the same half of the conversation still loaded, and the post that
  was on the screen back at its own offset, within 4 CSS px once the page has
  settled. Leaving and re-entering, a reload in the same tab, and a NEW SESSION
  with nothing but this browser's localStorage all have to do it.
* A DISTINCT REPLY TARGET SURVIVES. The post being answered in a thread is not
  the post being read; a restored composer answers the one that was chosen, and
  what it actually posts names that parent and that conversation.
* A LATE RESTORE NEVER STEALS THE READER'S SCROLL. Where the data arrives after
  somebody has started reading, their place is theirs; and the reflow
  correction that follows a restore stops the moment they take control.
* A MISSING ANCHOR IS A RECOVERABLE STATE, not a silent jump: the filters and
  the batch are kept, and the reader is told.
* AN EXPLICIT ADDRESS WINS over what the browser remembers, and Back and
  Forward land on the entries they name.
* THE PLACEHOLDER SLOTS ADD NO CONTROLS. The room draws all four of them (F11)
  and the ones nobody owns yet draw nothing a reader could press.

Build apps/fluid-web first. Opt in with MENTIS_QUIET_BROWSER=1; this needs
Playwright plus its Chromium and WebKit browsers, but no MARS or live Brain.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from mentis.conversation import text
from tests._loop import get, world  # noqa: F401

browser = pytest.mark.skipif(
    os.environ.get("MENTIS_QUIET_BROWSER") != "1",
    reason="set MENTIS_QUIET_BROWSER=1 after building the client",
)

WIDE = {"width": 1440, "height": 900}
NARROW = {"width": 390, "height": 844}

#: The post the reader can see, and where it is -- the same rule the reader
#: itself uses (`quiet/reader/scroll.ts`), read off the page as a reader meets
#: it rather than out of the store that recorded it.
VISIBLE = """
() => {
  const stream = document.getElementById('qc-stream')
  if (!stream) return null
  for (const el of stream.querySelectorAll('.qc-post')) {
    const box = el.getBoundingClientRect()
    if (box.bottom - 2 > 0 && box.top + 2 < innerHeight)
      return { post: el.id.slice('qc-post-'.length), top: box.top }
  }
  return null
}
"""

AT = "() => document.scrollingElement.scrollTop"

#: Within 4 CSS px of where that post was, once the page has settled.
SETTLED = """
([post, top]) => {
  const el = document.getElementById('qc-post-' + post)
  return !!el && Math.abs(el.getBoundingClientRect().top - top) <= 4
}
"""


def _a_reading(world, name="Quiet reading"):
    """A conversation long enough to leave a place in: 45 posts filed under one
    topic, so a topic reading pages, plus a thread with a root and six
    replies."""
    cv, owner = world["cv"], world["who"]["@brian"]
    cid = cv.open_conversation(name, about="Long enough to leave a place in.")
    cv.join(owner, cid)
    topic = cv.open_topic(cid, "Reading", about="What is filed here.")
    filed = []
    for n in range(45):
        turn = cv.say(cid, owner, [text(f"A post filed under Reading, number {n}.")])
        cv.assign_topic(turn, topic)
        filed.append(turn)
    root = cv.say(cid, owner, [text("The root of a thread worth coming back to.")])
    chain = [cv.say(cid, owner, [text(f"A reply in the thread, number {n}.")], replies_to=root)
             for n in range(6)]
    return {"conversation": cid, "topic": topic, "filed": filed, "root": root, "chain": chain}


def _elsewhere(world, name="Quiet elsewhere"):
    cv, owner = world["cv"], world["who"]["@brian"]
    cid = cv.open_conversation(name)
    cv.join(owner, cid)
    cv.say(cid, owner, [text("Somewhere else entirely.")])
    return cid


def _opened(page, name):
    page.get_by_role("heading", name=name, exact=True).wait_for()
    page.locator(".qc-post").first.wait_for()


def _still(page, tries=60):
    """Where the reader is once the scrolling has stopped. A position read
    while it is still moving is not a place anybody is at."""
    last = None
    for _ in range(tries):
        at = page.evaluate(AT)
        if at == last:
            return at
        last = at
        time.sleep(0.08)
    return page.evaluate(AT)


def _moved_to(page, y=800):
    """THE READING MOVES, and the coalesced write behind it settles. The
    document is what scrolls at every width, so this is the same movement a
    reader's wheel makes -- `mouse.wheel` and keyboard scrolling of a focused
    container both differ between Chromium and WebKit on Windows, and what
    these cases are about is the place, not the input device."""
    page.wait_for_function(
        "(y) => document.scrollingElement.scrollHeight - window.innerHeight > y",
        arg=y, timeout=15000)
    page.evaluate("(y) => window.scrollTo(0, y)", y)
    time.sleep(0.7)
    return page.evaluate(AT)


def _takes_control(page, y=None):
    """THE READER TAKES CONTROL: a real scrolling keypress, dispatched by the
    browser itself, which is the signal a pending restore gives way to. Where
    `y` is given the reading is moved there as well, because an engine that
    does not scroll a focused container on PageUp would otherwise leave the
    reader where the restore put them."""
    page.evaluate("() => document.getElementById('qc-stream')?.focus({ preventScroll: true })")
    page.keyboard.press("PageUp" if y is not None else "PageDown")
    if y is not None:
        page.evaluate("(y) => window.scrollTo(0, y)", y)
    time.sleep(0.7)
    return _still(page)


def _read_a_topic(world, page, place, name="Quiet reading"):
    """Open the topic, page back to an older batch, and scroll into it."""
    page.goto(world["base"] + f"/quiet#/c/{place['conversation']}/t/{place['topic']}")
    _opened(page, name)
    assert page.locator(".qc-focus").inner_text() == "# Reading"
    page.get_by_role("button", name="Older posts", exact=False).click()
    page.get_by_role("button", name="Latest posts", exact=True).wait_for()
    at = _moved_to(page, 800)
    assert at > 100, "nothing scrolled, so the restoration would prove nothing"
    return page.evaluate(VISIBLE)


def _leave_and_return(world, page, place, name="Quiet reading"):
    """Leave for another conversation, then come back to the BARE address --
    which is the resume entry: nothing in it says where to be."""
    page.goto(world["base"] + f"/quiet#/c/{_elsewhere(world)}")
    page.get_by_role("heading", name="Quiet elsewhere", exact=True).wait_for()
    page.goto(world["base"] + f"/quiet#/c/{place['conversation']}")
    _opened(page, name)


@browser
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
@pytest.mark.parametrize("viewport", [WIDE, NARROW], ids=["1440x900", "390x844"])
def test_an_older_batch_in_a_filtered_topic_comes_back_at_its_offset(world, engine, viewport):
    playwright = pytest.importorskip("playwright.sync_api")
    assert (Path(__file__).parents[1] / "apps/fluid-web/dist/index.html").exists()
    place = _a_reading(world)
    with playwright.sync_playwright() as p:
        browser_ = getattr(p, engine).launch()
        try:
            page = browser_.new_page(viewport=viewport)
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            was = _read_a_topic(world, page, place)
            assert was, "no post was visible to remember"

            _leave_and_return(world, page, place)
            # The topic is still filtering, and the same half is still loaded.
            page.locator(".qc-focus").wait_for()
            assert page.locator(".qc-focus").inner_text() == "# Reading"
            page.get_by_role("button", name="Latest posts", exact=True).wait_for()
            page.wait_for_function(SETTLED, arg=[was["post"], was["top"]], timeout=8000)
            now = page.evaluate(
                "(post) => document.getElementById('qc-post-' + post).getBoundingClientRect().top",
                was["post"])
            assert abs(now - was["top"]) <= 4, (was, now)
            assert errors == [], errors
        finally:
            browser_.close()


@browser
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_a_reload_and_a_new_session_restore_the_same_place(world, engine):
    """A RELOAD in the same tab, and a NEW SESSION with nothing but this
    browser's localStorage -- no tab copy, no server state, no address."""
    playwright = pytest.importorskip("playwright.sync_api")
    place = _a_reading(world)
    with playwright.sync_playwright() as p:
        browser_ = getattr(p, engine).launch()
        try:
            page = browser_.new_page(viewport=WIDE)
            was = _read_a_topic(world, page, place)
            _leave_and_return(world, page, place)
            page.wait_for_function(SETTLED, arg=[was["post"], was["top"]], timeout=8000)

            page.reload()
            _opened(page, "Quiet reading")
            page.get_by_role("button", name="Latest posts", exact=True).wait_for()
            page.wait_for_function(SETTLED, arg=[was["post"], was["top"]], timeout=8000)
            assert page.locator(".qc-focus").inner_text() == "# Reading"

            kept = page.evaluate("() => Object.fromEntries(Object.entries(localStorage))")
            assert any(k.startswith("mentis:quiet:workspace:v1:") for k in kept), sorted(kept)
            fresh = browser_.new_context(viewport=WIDE)
            try:
                fresh.add_init_script(
                    "(() => { const d = %s; for (const k in d) localStorage.setItem(k, d[k]) })()"
                    % json.dumps(kept))
                second = fresh.new_page()
                second.goto(world["base"] + f"/quiet#/c/{place['conversation']}")
                _opened(second, "Quiet reading")
                second.get_by_role("button", name="Latest posts", exact=True).wait_for()
                assert second.locator(".qc-focus").inner_text() == "# Reading"
                second.wait_for_function(SETTLED, arg=[was["post"], was["top"]], timeout=8000)
            finally:
                fresh.close()
        finally:
            browser_.close()


@browser
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_a_restored_thread_replies_to_the_post_that_was_chosen(world, engine):
    """The post being ANSWERED is not the post being READ. A restored composer
    answers the one that was chosen, and what it posts says so."""
    playwright = pytest.importorskip("playwright.sync_api")
    place = _a_reading(world)
    read_post, answer_post = place["chain"][3], place["chain"][1]
    with playwright.sync_playwright() as p:
        browser_ = getattr(p, engine).launch()
        try:
            page = browser_.new_page(viewport=WIDE)
            page.goto(world["base"] + f"/quiet#/c/{place['conversation']}/turn/{read_post}")
            _opened(page, "Quiet reading")
            page.locator(".qc-parent-header").wait_for()
            # Answer a DIFFERENT post from the one the thread is reading.
            reading_says = page.locator("label[for='qc-compose']").inner_text()
            page.locator(f"#qc-post-{answer_post} .qc-post-reply").click()
            page.locator(f"#qc-post-{answer_post}[data-selected]").wait_for()
            page.wait_for_function(
                "(was) => document.querySelector(\"label[for='qc-compose']\").textContent !== was",
                arg=reading_says, timeout=8000)
            chose = page.locator("label[for='qc-compose']").inner_text()
            assert chose.startswith("Replying to #") and chose != reading_says, chose
            reading = page.locator(f"#qc-post-{read_post}").get_attribute("data-selected")
            assert reading is None, "the post being read is not the post being answered"

            _leave_and_return(world, page, place)
            page.locator(".qc-parent-header").wait_for()
            page.locator(f"#qc-post-{answer_post}[data-selected]").wait_for()
            assert page.locator("label[for='qc-compose']").inner_text() == chose, (
                "the restored composer answers the post that was chosen")

            # And what it posts names that parent, in that conversation.
            page.locator("#qc-compose").fill("The reply the restored composer wrote.")
            page.get_by_label("Posting action").select_option("record-only")
            page.locator(".qc-compose-send").click()
            page.wait_for_function("() => document.querySelector('#qc-compose')?.value === ''",
                                   timeout=8000)
            thread = get(world, f"/api/conversations/{place['conversation']}"
                                f"/thread/{place['root']}")
            wrote = [t for t in thread["replies"]
                     if "restored composer wrote" in json.dumps(t.get("parts", []))]
            assert len(wrote) == 1, thread["replies"]
            assert wrote[0]["answering"] == answer_post, wrote[0]
        finally:
            browser_.close()


@browser
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_a_late_restore_never_steals_the_readers_scroll(world, engine):
    """TWO WAYS A RESTORE COULD TAKE SOMEBODY'S PLACE AWAY, and neither may.

    Late data: the reading arrives after somebody has started reading, and the
    restore belongs to the arrival rather than to them. The reflow correction:
    it answers a font or an image settling, and stops the moment they take
    control -- so a viewport change afterwards does not put them back."""
    playwright = pytest.importorskip("playwright.sync_api")
    place = _a_reading(world)
    with playwright.sync_playwright() as p:
        browser_ = getattr(p, engine).launch()
        try:
            page = browser_.new_page(viewport=WIDE)
            was = _read_a_topic(world, page, place)

            # The control: it does restore, to a verified nonzero place.
            _leave_and_return(world, page, place)
            page.wait_for_function(SETTLED, arg=[was["post"], was["top"]], timeout=8000)
            restored = _still(page)
            assert restored > 100, restored

            # The correction stops when the reader takes over: they scroll
            # somewhere else, then the viewport changes under them.
            theirs = _takes_control(page, 180)
            assert abs(theirs - restored) > 50, (theirs, restored)
            # A real layout event on the reading itself -- the kind a font or
            # an image settling makes -- after they have taken control.
            page.evaluate("() => { document.getElementById('qc-stream').style.paddingTop = '60px' }")
            time.sleep(0.5)
            after = page.evaluate(AT)
            assert abs(after - theirs) <= 2, (
                f"a layout event put the reader back: {theirs} -> {after}")

            # Late data: the reading is held up, and the reader scrolls first.
            def slow(route):
                time.sleep(1.2)
                route.continue_()

            page.route("**/api/conversations/*batch=30*", slow)
            try:
                page.goto(world["base"] + f"/quiet#/c/{_elsewhere(world, 'Quiet away')}")
                page.get_by_role("heading", name="Quiet away", exact=True).wait_for()
                page.goto(world["base"] + f"/quiet#/c/{place['conversation']}")
                page.locator("#qc-stream").wait_for()
                _takes_control(page)
                _opened(page, "Quiet reading")
                time.sleep(1.0)
                assert page.evaluate(AT) == 0, (
                    "the restore took the place the reader had taken")
            finally:
                page.unroute("**/api/conversations/*batch=30*")
        finally:
            browser_.close()


@browser
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_an_anchor_that_is_gone_keeps_the_filters_and_says_so(world, engine):
    """A post that is not drawn -- filtered out, not loaded, deleted -- is a
    recoverable state. The topic and the batch are still what they were, the
    reader is at the first available post of that batch, and they are told."""
    playwright = pytest.importorskip("playwright.sync_api")
    place = _a_reading(world)
    with playwright.sync_playwright() as p:
        browser_ = getattr(p, engine).launch()
        try:
            page = browser_.new_page(viewport=WIDE)
            was = _read_a_topic(world, page, place)
            _leave_and_return(world, page, place)
            page.wait_for_function(SETTLED, arg=[was["post"], was["top"]], timeout=8000)
            # Take the anchored post out of the bookmark, as a deletion would.
            # A reload is what makes the store read it again.
            changed = page.evaluate("""(conversation) => {
              const key = Object.keys(localStorage).find(k =>
                k.startsWith('mentis:quiet:workspace:v1:') && k.endsWith(':' + conversation))
              if (!key) return null
              const envelope = JSON.parse(localStorage.getItem(key))
              const reading = envelope.readings['this-post']
              if (!reading || !reading.flow.anchor) return null
              reading.flow.anchor.post = 'ent-nothing-of-the-sort'
              localStorage.setItem(key, JSON.stringify(envelope))
              return reading.flow
            }""", place["conversation"])
            assert changed, "there was no saved reading to take the anchor out of"
            page.reload()
            _opened(page, "Quiet reading")
            assert page.locator(".qc-focus").inner_text() == "# Reading"
            page.get_by_role("button", name="Latest posts", exact=True).wait_for()
            page.get_by_text("not shown here now", exact=False).wait_for(timeout=8000)
            assert page.evaluate(AT) == 0, "the first available post of the saved batch"
        finally:
            browser_.close()


@browser
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_an_explicit_address_wins_and_back_and_forward_land_where_they_name(world, engine):
    playwright = pytest.importorskip("playwright.sync_api")
    place = _a_reading(world)
    away = _elsewhere(world)
    with playwright.sync_playwright() as p:
        browser_ = getattr(p, engine).launch()
        try:
            page = browser_.new_page(viewport=WIDE)
            _read_a_topic(world, page, place)
            page.goto(world["base"] + f"/quiet#/c/{away}")
            page.get_by_role("heading", name="Quiet elsewhere", exact=True).wait_for()

            # DELIBERATE WINS: an address naming a post opens that post's
            # thread, not the topic reading the browser remembers.
            page.goto(world["base"] + f"/quiet#/c/{place['conversation']}"
                                      f"/turn/{place['chain'][2]}")
            _opened(page, "Quiet reading")
            page.locator(".qc-parent-header").wait_for()
            assert page.locator(".qc-focus").count() == 0, "no saved topic was imposed"

            page.go_back()
            page.get_by_role("heading", name="Quiet elsewhere", exact=True).wait_for()
            page.go_forward()
            _opened(page, "Quiet reading")
            page.locator(".qc-parent-header").wait_for()

            # AND THE BARE ENTRY IS STILL THE RESUME ENTRY: re-entering shows
            # the reading that was last left, which is now this thread. (The
            # topic went with the explicit address, which named none: within a
            # reading, a bare address is the reader asking for all posts, and
            # that is deliberate too.)
            _leave_and_return(world, page, place)
            page.locator(".qc-parent-header").wait_for()
            assert page.locator(f"#qc-post-{place['chain'][2]}").count() == 1
        finally:
            browser_.close()


@browser
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_the_room_draws_four_slots_and_no_controls_nobody_owns(world, engine):
    """F11/F27: all four fixed slots are drawn, the ones whose owners have not
    landed draw nothing a reader could press, a parked surface cannot be
    reached by Tab, and ConversationNav and RailTools are mounted exactly
    once each."""
    playwright = pytest.importorskip("playwright.sync_api")
    place = _a_reading(world)
    with playwright.sync_playwright() as p:
        browser_ = getattr(p, engine).launch()
        try:
            page = browser_.new_page(viewport=WIDE)
            page.goto(world["base"] + f"/quiet#/c/{place['conversation']}")
            _opened(page, "Quiet reading")
            for slot in ("conversation", "tools", "working", "pageControls"):
                assert page.locator(f"[data-slot='{slot}']").count() == 1, slot
            assert page.locator(".qc-nav").count() == 1, "one ConversationNav"
            assert page.locator(".qc-rail-tools").count() == 1, "one RailTools"
            assert page.locator("#qc-stream").count() == 1
            assert page.locator(".qc-dock").count() == 1
            assert page.locator("#qc-compose").count() == 1
            # The parked working area is hidden from sight and from focus.
            assert page.locator("[data-slot='working']").is_hidden()
            reachable = page.evaluate("""() => {
              const slot = document.querySelector("[data-slot='working']")
              return [...slot.querySelectorAll('a,button,input,select,textarea,[tabindex]')]
                .filter(el => el.offsetParent !== null).length
            }""")
            assert reachable == 0, "a parked surface must not be reachable"
            # Nothing nobody owns yet offers an affordance.
            assert page.locator("[data-slot='pageControls'] button, "
                                "[data-slot='pageControls'] a").count() == 0
            assert page.get_by_role("button", name="Return to conversation").count() == 0
        finally:
            browser_.close()
