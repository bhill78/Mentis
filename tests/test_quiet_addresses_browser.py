"""QUIET CHAT'S ADDRESSES AND THE BROWSER'S HISTORY (owner, 2026-11-20, navigation A1-A4).

What the owner asked for, checked in a browser against the real routes of a disposable fixture
Brain, at BOTH addresses Quiet Chat is served on (`/` and `/quiet2`):

  A1  a Brain record's address survives a refresh, is what "Copy link" copies, and reopens;
      Back returns to where the record was opened from; an unsaved draft is asked about.
  A2  choosing a conversation is an entry of the history with its own address: Back and Forward
      walk the conversations visited, the one already shown adds nothing, a refresh shows the
      conversation switched to, and a composer's draft is still there on the way back.
  A3  Manage Sources and the 3D Brain have addresses: direct, refresh, Back and Forward.
  A4  "More…" under Settings' backgrounds has a Back, by mouse and by keyboard, at 390 px too.

The decisions are pure and unit-tested (`apps/fluid-web/tests/quiet_address_unit.ts`); this is the
thing itself. Build apps/fluid-web first, then opt in with MENTIS_QUIET_BROWSER=1.
"""
from __future__ import annotations

import os
import re
from urllib.parse import parse_qs, urlsplit

import pytest

from mentis import api
from mentis.conversation import text
from tests._loop import post, world  # noqa: F401
from tests.conftest import owner_headers

pytestmark = pytest.mark.skipif(
    os.environ.get("MENTIS_QUIET_BROWSER") != "1",
    reason="build the UI (apps/fluid-web) and set MENTIS_QUIET_BROWSER=1",
)

MS = 20000
#: Chromium unless another engine is asked for (MENTIS_QUIET_ENGINE=webkit): the history is the
#: browser's own, so it is worth walking in more than one.
ENGINE = os.environ.get("MENTIS_QUIET_ENGINE", "chromium")
#: Quiet Chat is served at both; everything here must hold at each.
PATHS = ["/", "/quiet2"]


@pytest.fixture
def places(world, tmp_path):
    cv, owner = world["cv"], world["who"]["@brian"]
    made = {}
    for key in ("one", "two", "three"):
        c = cv.open_conversation(f"Addresses: {key}", about=f"The {key}.")
        cv.join(owner, c)
        cv.say(c, owner, [text(f"A post in conversation {key}.")])
        made[key] = c
    made["rule"] = post(world, "/api/entries", {
        "kind": "rule", "body": {"text": "Ask the owner who runs the deploy step.", "about": "deploys"},
        "attributed_to": owner, "establish": False})["entry"]
    folder = tmp_path / "notes"
    folder.mkdir()
    (folder / "a.md").write_text("A held note.", encoding="utf-8")
    src = api.sources(world["state"].corpus)
    plan = src.preview_new(connector="filesystem", name="Field notes", root=str(folder), include=["**"], exclude=[])
    made["source"] = src.acquire_new(plan["draft"], plan["plan"], connector="filesystem",
                                     actor=owner, written_by="test")["collection"]
    return made


@pytest.fixture
def browser_context(world):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = getattr(p, ENGINE).launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        context.set_extra_http_headers(owner_headers())
        if ENGINE == "chromium":
            context.grant_permissions(["clipboard-read", "clipboard-write"])
        try:
            yield context
        finally:
            browser.close()


@pytest.fixture
def page(browser_context):
    return _new_page(browser_context)


def _new_page(context):
    pg = context.new_page()
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    return pg


def query(page):
    """The address's query, as {name: value}."""
    return {k: v[0] for k, v in parse_qs(urlsplit(page.url).query, keep_blank_values=True).items()}


def path(page):
    return urlsplit(page.url).path


def entries(page):
    return page.evaluate("history.length")


def shows(page, key):
    """Conversation `key` is the one read: its post, its heading, its title."""
    page.get_by_text(f"A post in conversation {key}.", exact=True).wait_for(timeout=MS)
    page.get_by_role("heading", name=f"Addresses: {key}", exact=True).wait_for(timeout=MS)
    page.wait_for_function("t => document.title.startsWith(t)", arg=f"Addresses: {key}", timeout=MS)


def names(page, **want):
    """The address comes to carry exactly these place names (None: absent)."""
    def ok():
        q = query(page)
        return all((k not in q) if v is None else q.get(k) == v for k, v in want.items())
    for _ in range(200):
        if ok():
            return
        page.wait_for_timeout(50)
    raise AssertionError(f"the address is {page.url}, wanted {want}")


def choose(page, key):
    """A press on a conversation in the rail: the real way to switch."""
    page.locator(".q2-markers-left").get_by_role(
        "button", name=re.compile(rf"^Addresses: {key}, ")).first.click()


def focus_is_in(page, selector):
    """The keyboard is in the card: a key pressed now is pressed in it."""
    page.wait_for_function(
        "s => document.querySelector(s)?.contains(document.activeElement)", arg=selector, timeout=MS)


def composer(page):
    return page.locator(".q2-col textarea").first


# -- A2: conversations ---------------------------------------------------------

@pytest.mark.parametrize("at", PATHS)
def test_back_and_forward_walk_the_conversations_visited(world, places, page, at):
    page.goto(world["base"] + at + "?c=" + places["one"])
    shows(page, "one")
    start = entries(page)

    choose(page, "two")
    shows(page, "two")
    names(page, c=places["two"])
    choose(page, "three")
    shows(page, "three")
    names(page, c=places["three"])
    assert path(page) == at
    assert entries(page) == start + 2, "one entry per conversation chosen, no more"

    # THE ONE ALREADY SHOWN ADDS NOTHING, however often it is pressed.
    choose(page, "three")
    choose(page, "three")
    page.wait_for_timeout(200)
    assert entries(page) == start + 2

    page.go_back()
    shows(page, "two")
    names(page, c=places["two"])
    page.go_back()
    shows(page, "one")
    names(page, c=places["one"])
    page.go_forward()
    shows(page, "two")
    names(page, c=places["two"])
    assert entries(page) == start + 2, "walking the history adds nothing to it"
    assert path(page) == at

    # A REFRESH SHOWS THE CONVERSATION SWITCHED TO, not the one first opened.
    page.reload()
    shows(page, "two")
    names(page, c=places["two"])
    assert page.get_by_text("A post in conversation one.", exact=True).count() == 0
    # and the address, opened anywhere else, is that conversation
    other = _new_page(page.context)
    other.goto(page.url)
    shows(other, "two")
    assert page.errors == [] and other.errors == []


@pytest.mark.parametrize("at", PATHS)
def test_the_address_names_the_conversation_the_page_settled_on(world, places, page, at):
    """Opened with no conversation named, the address comes to name the one shown -- in place:
    nothing is added to the history for it."""
    page.goto("about:blank")
    page.goto(world["base"] + at)
    page.locator(".q2-conv-head h1").wait_for(timeout=MS)
    page.wait_for_function("() => new URLSearchParams(location.search).get('c')", timeout=MS)
    shown = query(page)["c"]
    assert path(page) == at
    page.reload()
    page.wait_for_function("() => new URLSearchParams(location.search).get('c')", timeout=MS)
    assert query(page)["c"] == shown
    page.go_back()
    assert page.url == "about:blank", "settling on a conversation added an entry"


def test_a_draft_survives_switching_away_and_coming_back(world, places, page):
    page.goto(world["base"] + "/?c=" + places["one"])
    shows(page, "one")
    composer(page).fill("A thought not yet sent.")
    choose(page, "two")
    shows(page, "two")
    assert composer(page).input_value() == "", "one conversation's draft appeared in another"
    composer(page).fill("And one for the second.")
    page.go_back()
    shows(page, "one")
    page.wait_for_function(
        "() => document.querySelector('.q2-col textarea')?.value === 'A thought not yet sent.'", timeout=MS)
    page.go_forward()
    shows(page, "two")
    page.wait_for_function(
        "() => document.querySelector('.q2-col textarea')?.value === 'And one for the second.'", timeout=MS)
    assert page.errors == []


# -- A1: Brain records ---------------------------------------------------------

@pytest.mark.parametrize("at", PATHS)
def test_a_record_has_an_address_that_survives_refresh_and_reopens(world, places, page, at):
    rule = places["rule"]
    page.goto(world["base"] + at + "?c=" + places["one"])
    shows(page, "one")
    start = entries(page)

    # opened the real way: the Brain button, then its row
    page.get_by_role("button", name="Brain", exact=True).first.click()
    page.get_by_role("tab", name="All").click()
    page.locator(f'.q2-brain-row[data-record="{rule}"]').click()
    record = page.locator(f'.rv[data-record="{rule}"]')
    record.wait_for(timeout=MS)
    names(page, c=places["one"], record=rule)
    assert path(page) == at and entries(page) == start + 1

    # A REFRESH SHOWS THE RECORD AGAIN, on the same address.
    page.reload()
    record.wait_for(timeout=MS)
    names(page, c=places["one"], record=rule)

    # WHAT "COPY LINK" COPIES opens the record in a page of its own. (Only Chromium lets a test
    # read the clipboard; elsewhere the address the link is built from is used.)
    copied = world["base"] + at + "?record=" + rule
    if ENGINE == "chromium":
        record.get_by_role("button", name="More on this record").click()
        page.get_by_role("menuitem", name="Copy link").click()
        page.wait_for_function("async () => (await navigator.clipboard.readText()).includes('record=')", timeout=MS)
        assert page.evaluate("navigator.clipboard.readText()") == copied
    assert urlsplit(copied).path == at
    other = _new_page(page.context)
    other.goto(copied)
    other.locator(f'.rv[data-record="{rule}"]').wait_for(timeout=MS)
    names(other, record=rule)
    other.reload()
    other.locator(f'.rv[data-record="{rule}"]').wait_for(timeout=MS)
    names(other, record=rule)
    other.close()

    # BACK RETURNS TO WHERE IT WAS OPENED FROM, and Forward to the record.
    page.go_back()
    shows(page, "one")
    names(page, c=places["one"], record=None)
    page.go_forward()
    record.wait_for(timeout=MS)
    names(page, record=rule)
    # the page's own Back is the same step, not a new entry
    before = entries(page)
    page.get_by_role("button", name=re.compile("Back to the conversation")).first.click()
    shows(page, "one")
    names(page, record=None)
    assert entries(page) == before
    assert page.errors == []


@pytest.mark.parametrize("at", PATHS)
def test_an_address_naming_a_record_that_is_not_there_says_so(world, places, page, at):
    page.goto(world["base"] + at + "?c=" + places["one"] + "&record=ent-00000000dead")
    shows(page, "one")
    said = page.get_by_role("alert").filter(has_text="Brain record that is not in this Brain")
    said.wait_for(timeout=MS)
    names(page, c=places["one"], record=None)
    assert path(page) == at
    # it does not come back, loop or blank: a refresh is simply the conversation
    page.reload()
    shows(page, "one")
    assert page.get_by_role("alert").filter(has_text="Brain record").count() == 0
    # an id that is not an id at all is said the same way
    page.goto(world["base"] + at + "?c=" + places["one"] + "&record=nonsense")
    shows(page, "one")
    page.get_by_role("alert").filter(has_text="Brain record that is not in this Brain").wait_for(timeout=MS)
    names(page, c=places["one"], record=None)
    page.get_by_role("button", name="Dismiss").click()
    assert page.get_by_role("alert").filter(has_text="Brain record").count() == 0
    assert page.errors == []


def _write_a_rule(page):
    """The compact editor, with words nothing has recorded."""
    page.get_by_role("button", name="Brain", exact=True).first.click()
    page.get_by_role("button", name="Make, import, preview").click()
    page.get_by_role("menuitem", name="Rule…", exact=True).click()
    box = page.locator("[data-author-modal] [data-author] textarea").first
    box.wait_for(timeout=MS)
    box.fill("Never deploy on a Friday.")
    return box


def test_back_asks_before_an_unsaved_record_is_left(world, places, page):
    page.goto(world["base"] + "/?c=" + places["one"])
    shows(page, "one")
    choose(page, "two")
    shows(page, "two")
    box = _write_a_rule(page)

    # THE BROWSER'S BACK would leave the conversation it is being written over.
    page.go_back()
    ask = page.get_by_role("alertdialog")
    ask.wait_for(timeout=MS)
    assert "unfinished" in ask.inner_text()
    ask.get_by_role("button", name="Stay").click()
    ask.wait_for(state="detached", timeout=MS)
    # STAY: still the second conversation, on its address, the words intact
    names(page, c=places["two"])
    shows(page, "two")
    assert box.input_value() == "Never deploy on a Friday."
    assert page.errors == []


# -- A3: Manage Sources --------------------------------------------------------

@pytest.mark.parametrize("at", PATHS)
def test_manage_sources_has_addresses(world, places, page, at):
    source = places["source"]
    page.goto(world["base"] + at + "?c=" + places["one"])
    shows(page, "one")
    start = entries(page)
    card = page.get_by_role("dialog", name="Sources", exact=True)

    page.get_by_role("button", name="Sources", exact=True).first.click()
    card.wait_for(timeout=MS)
    names(page, c=places["one"], sources="all")
    assert entries(page) == start + 1

    # a refresh shows the browser again
    page.reload()
    card.wait_for(timeout=MS)
    names(page, sources="all")

    # a source's own page
    card.locator(f'[data-source="{source}"]').click()
    src_page = page.locator('[data-source-page="source"]')
    src_page.wait_for(timeout=MS)
    page.get_by_role("heading", name="Field notes").first.wait_for(timeout=MS)
    names(page, c=places["one"], sources=source)
    page.reload()
    src_page.wait_for(timeout=MS)
    page.get_by_role("heading", name="Field notes").first.wait_for(timeout=MS)
    names(page, sources=source)

    # A HELD FILE READ IN PLACE over its source is a place too: its address
    # names it, a refresh reads it again, and Back is the source's page
    page.get_by_role("button", name=re.compile(r"^a\.md")).click()
    reading = page.locator('[data-source-page="content"]')
    reading.wait_for(timeout=MS)
    page.get_by_text("A held note.").first.wait_for(timeout=MS)
    names(page, sources=source)
    assert "a.md" in query(page).get("file", ""), page.url
    page.reload()
    reading.wait_for(timeout=MS)
    page.get_by_text("A held note.").first.wait_for(timeout=MS)
    assert "a.md" in query(page).get("file", ""), page.url
    page.go_back()
    src_page.wait_for(timeout=MS)
    names(page, sources=source, file=None)

    # Back: the browser; Back again: the conversation; Forward: the browser
    page.go_back()
    card.wait_for(timeout=MS)
    names(page, sources="all")
    page.go_back()
    card.wait_for(state="hidden", timeout=MS)
    shows(page, "one")
    names(page, sources=None)
    page.go_forward()
    card.wait_for(timeout=MS)
    names(page, sources="all")
    # CLOSING IT is that same step back, not a new entry
    before = entries(page)
    focus_is_in(page, ".q2-src-card")
    page.keyboard.press("Escape")
    card.wait_for(state="hidden", timeout=MS)
    names(page, c=places["one"], sources=None)
    assert entries(page) == before

    # THE BRAIN'S CARD IN ITS PLACE: the address stops naming Sources, and
    # nothing is added for it
    page.get_by_role("button", name="Sources", exact=True).first.click()
    card.wait_for(timeout=MS)
    names(page, sources="all")
    before = entries(page)
    page.locator(".q2-rail-brain").first.click(force=True)
    page.get_by_role("dialog", name="Brain", exact=True).wait_for(timeout=MS)
    card.wait_for(state="hidden", timeout=MS)
    names(page, c=places["one"], sources=None)
    assert entries(page) == before
    page.keyboard.press("Escape")

    # DIRECT: the address alone, in a page of its own
    other = _new_page(page.context)
    other.goto(world["base"] + at + "?c=" + places["two"] + "&sources=" + source)
    other.locator('[data-source-page="source"]').wait_for(timeout=MS)
    other.get_by_role("heading", name="Field notes").first.wait_for(timeout=MS)
    # the page's own Back from there is the Sources browser, with its address
    other.locator("[data-source-back]").click()
    other.get_by_role("dialog", name="Sources", exact=True).wait_for(timeout=MS)
    names(other, c=places["two"], sources="all")
    # closed after a direct open, nothing is behind to go back to: the entry
    # becomes the conversation, and Back does not open it again
    was = entries(other)
    focus_is_in(other, ".q2-src-card")
    other.keyboard.press("Escape")
    other.get_by_role("dialog", name="Sources", exact=True).wait_for(state="hidden", timeout=MS)
    shows(other, "two")
    names(other, sources=None)
    assert entries(other) == was
    assert page.errors == [] and other.errors == []


def test_an_address_naming_a_source_that_is_not_there_says_so(world, places, page):
    page.goto(world["base"] + "/?c=" + places["one"] + "&sources=ent-00000000dead")
    shows(page, "one")
    page.get_by_role("alert").filter(has_text="source that is not in this Brain").wait_for(timeout=MS)
    names(page, c=places["one"], sources=None)
    assert page.errors == []


# -- A3: the 3D Brain ----------------------------------------------------------

@pytest.mark.parametrize("at", PATHS)
def test_the_3d_brain_has_an_address(world, places, page, at):
    page.goto(world["base"] + at + "?c=" + places["one"])
    shows(page, "one")
    start = entries(page)
    stage = page.locator(".q2-space-stage")

    page.get_by_role("button", name="3D Brain", exact=True).first.click()
    stage.wait_for(timeout=MS)
    names(page, c=places["one"], space="1")
    assert path(page) == at and entries(page) == start + 1

    # Back: the conversation; Forward: the same graph again
    page.go_back()
    stage.wait_for(state="detached", timeout=MS)
    shows(page, "one")
    names(page, space=None)
    page.go_forward()
    stage.wait_for(timeout=MS)
    names(page, space="1")

    # WHAT THE GRAPH LEADS TO is a step of the same history: Back from it is
    # the graph again, the same view, on the graph's address
    field = page.locator(".space-field")
    field.wait_for(timeout=MS)
    field.focus()
    page.keyboard.press("Tab")
    page.wait_for_function(
        "() => { const f = document.querySelector('.space-field'); return f && f.dataset.selected }", timeout=MS)
    page.wait_for_timeout(700)
    field.focus()
    page.keyboard.press("Enter")
    page.get_by_role("button", name="Back to 3D Brain", exact=False).first.wait_for(timeout=MS)
    names(page, space=None)
    page.go_back()
    stage.wait_for(timeout=MS)
    names(page, c=places["one"], space="1")
    shown_entries = entries(page)

    # A REFRESH opens the 3D Brain again, in place: nothing is added
    page.reload()
    stage.wait_for(timeout=MS)
    names(page, c=places["one"], space="1")
    assert entries(page) == shown_entries

    # CLOSED, the address stops naming it
    page.get_by_role("button", name="Close the 3D Brain").click()
    stage.wait_for(state="detached", timeout=MS)
    names(page, c=places["one"], space=None)

    # DIRECT: the address alone, in a page of its own
    other = _new_page(page.context)
    other.goto(world["base"] + at + "?c=" + places["two"] + "&space=1")
    other.locator(".q2-space-stage").wait_for(timeout=MS)
    names(other, c=places["two"], space="1")
    assert page.errors == [] and other.errors == []


# -- A4: More backgrounds ------------------------------------------------------

def _backgrounds(page):
    page.get_by_role("button", name="More: Search, Saved passages, Settings").click()
    page.get_by_role("button", name="Settings", exact=True).click()
    page.get_by_role("tab", name="Backgrounds and theme").click()
    more = page.get_by_role("button", name="More…", exact=True)
    more.wait_for(timeout=MS)
    return more


def _in_view(page, locator):
    box = locator.bounding_box()
    size = page.viewport_size
    return bool(box) and box["x"] >= 0 and box["y"] >= 0 and box["x"] + box["width"] <= size["width"] \
        and box["y"] + box["height"] <= size["height"]


@pytest.mark.parametrize("width, height", [(1440, 1000), (390, 800)])
def test_more_backgrounds_has_a_way_back(world, places, page, width, height):
    page.set_viewport_size({"width": width, "height": height})
    page.goto(world["base"] + "/?c=" + places["one"])
    shows(page, "one")
    more = _backgrounds(page)
    settings = page.get_by_role("dialog", name="Settings")
    back = page.locator("[data-look-back]")
    every = page.get_by_role("group", name="Every background")
    scroller = "document.querySelector('.q2-gdock-settings')"
    page.evaluate(f"{scroller}.scrollTop = 40")
    left_at = page.evaluate(f"{scroller}.scrollTop")

    # BY MOUSE: More, then an obvious Back, in view, and the gallery whole
    more.click()
    every.wait_for(timeout=MS)
    assert back.is_visible() and _in_view(page, back), "the way back is not in view"
    assert "Back" in back.inner_text()
    tiles = every.locator("[data-atmosphere-pick]")
    assert tiles.count() >= 3
    panel = settings.bounding_box()
    for i in range(3):
        t = tiles.nth(i).bounding_box()
        assert t["x"] >= panel["x"] - 1 and t["x"] + t["width"] <= panel["x"] + panel["width"] + 1, \
            "a background is cut off at the side of Settings"
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    # scrolled to the end of the gallery, the Back is still in view
    page.evaluate(f"{scroller}.scrollTop = {scroller}.scrollHeight")
    assert page.evaluate(f"{scroller}.scrollTop") > 100, "the gallery did not scroll: nothing was checked"
    assert _in_view(page, back)
    back.click()
    every.wait_for(state="detached", timeout=MS)
    assert settings.is_visible() and more.is_visible(), "Back closed Settings instead of returning to it"
    assert page.evaluate("document.activeElement?.textContent") == "More…", "focus did not return"
    assert page.evaluate(f"{scroller}.scrollTop") == left_at, "Settings was not left where it was scrolled"

    # BY KEYBOARD: Enter opens it with focus on Back; Enter there returns
    page.keyboard.press("Enter")
    every.wait_for(timeout=MS)
    assert page.evaluate("document.activeElement?.hasAttribute('data-look-back')")
    page.keyboard.press("Enter")
    every.wait_for(state="detached", timeout=MS)
    assert page.evaluate("document.activeElement?.textContent") == "More…"
    # ESCAPE leaves the gallery only; Settings stays, and a second Escape closes Settings
    page.keyboard.press("Enter")
    every.wait_for(timeout=MS)
    page.keyboard.press("Escape")
    every.wait_for(state="detached", timeout=MS)
    assert settings.is_visible()
    assert page.evaluate("document.activeElement?.textContent") == "More…"
    assert page.errors == []


# -- 390 px ---------------------------------------------------------------------

def test_the_addresses_at_390_px(world, places, browser_context):
    rule, source = places["rule"], places["source"]
    page = _new_page(browser_context)
    page.set_viewport_size({"width": 390, "height": 800})
    fits = "document.documentElement.scrollWidth <= innerWidth"

    page.goto(world["base"] + "/?c=" + places["one"] + "&record=" + rule)
    page.locator(f'.rv[data-record="{rule}"]').wait_for(timeout=MS)
    assert page.evaluate(fits)
    back = page.get_by_role("button", name=re.compile("Back to the conversation")).first
    assert back.is_visible()
    back.click()
    shows(page, "one")
    names(page, c=places["one"], record=None)
    page.go_back()
    page.locator(f'.rv[data-record="{rule}"]').wait_for(timeout=MS)
    names(page, record=rule)

    page.goto(world["base"] + "/?c=" + places["one"] + "&sources=all")
    card = page.get_by_role("dialog", name="Sources", exact=True)
    card.wait_for(timeout=MS)
    assert page.evaluate(fits)
    card.locator(f'[data-source="{source}"]').click()
    page.locator('[data-source-page="source"]').wait_for(timeout=MS)
    names(page, sources=source)
    assert page.evaluate(fits)
    page.go_back()
    card.wait_for(timeout=MS)
    names(page, sources="all")

    page.goto(world["base"] + "/?c=" + places["one"] + "&space=1")
    page.locator(".q2-space-stage").wait_for(timeout=MS)
    close = page.get_by_role("button", name="Close the 3D Brain")
    assert close.is_visible()
    close.click()
    shows(page, "one")
    names(page, space=None)
    assert page.errors == []


# -- addresses that cannot be taken as written (independent review, 2026-11-20) --

@pytest.mark.parametrize("at", PATHS)
def test_an_address_that_cannot_be_taken_as_written_is_said_and_put_right(world, places, page, at):
    """A name the page cannot read never stays in the address while something else is shown: a
    refresh or a bookmark of what the bar then says is the place on the screen."""
    one, source = places["one"], places["source"]
    base = world["base"] + at + "?c=" + one
    said = page.locator(".q2-notice")

    # A FILE THAT IS NOT A FILE: the source, said, and the address is the source's
    page.goto(base + "&sources=" + source + "&file=garbage")
    page.locator('[data-source-page="source"]').wait_for(timeout=MS)
    said.filter(has_text="names a file in a way that cannot be read").wait_for(timeout=MS)
    names(page, c=one, sources=source, file=None)
    assert path(page) == at
    page.reload()
    page.locator('[data-source-page="source"]').wait_for(timeout=MS)
    page.get_by_role("heading", name="Field notes").first.wait_for(timeout=MS)
    names(page, c=one, sources=source, file=None)
    assert said.filter(has_text="cannot be read").count() == 0, "said again for an address that is now right"

    # A HELD FILE WITH NO SOURCE NAMED: Manage Sources, said, and the address says Manage Sources
    page.goto(base + "&sources=v%2Fadm-000000000000")
    page.get_by_role("dialog", name="Sources", exact=True).wait_for(timeout=MS)
    said.filter(has_text="without saying which source").wait_for(timeout=MS)
    names(page, c=one, sources="all")

    # A POST NUMBER THAT IS NOT ONE: the conversation's latest posts, said, and `at` is gone
    for bad in ("abc", "0", "-3"):
        page.goto(base + "&at=" + bad)
        shows(page, "one")
        page.get_by_role("alert").filter(has_text="post number that is not a number").wait_for(timeout=MS)
        names(page, c=one, at=None)
    page.reload()
    shows(page, "one")
    assert page.get_by_role("alert").filter(has_text="post number").count() == 0
    # ...and a real one is kept, as before
    page.goto(base + "&at=1")
    shows(page, "one")
    names(page, c=one, at="1")
    assert page.get_by_role("alert").filter(has_text="post number").count() == 0
    assert page.errors == []


def test_an_address_naming_a_file_that_is_not_held_says_so(world, places, page):
    """Well formed, but nothing is held under it: the reader says so where the file would be, with
    the way back to its source, on the address asked for -- no loop, no blank, and a refresh the same."""
    one, source = places["one"], places["source"]
    reading = page.locator('[data-source-page="content"]')
    for file, words in ((source + "%2Fo%2Fnope.md", "No observation of nope.md is recorded."),
                        ("v%2Fadm-000000000000", "Could not read adm-000000000000")):
        page.goto(world["base"] + "/?c=" + one + "&sources=" + source + "&file=" + file)
        reading.wait_for(timeout=MS)
        reading.get_by_text(words, exact=False).first.wait_for(timeout=MS)
        was, held = page.url, entries(page)
        page.wait_for_timeout(1200)
        assert page.url == was and entries(page) == held, "the address or the history moved by itself"
        page.reload()
        reading.wait_for(timeout=MS)
        reading.get_by_text(words, exact=False).first.wait_for(timeout=MS)
        assert page.url == was
        # the way back is the source itself, on the source's address
        page.locator("[data-source-back]").click()
        page.locator('[data-source-page="source"]').wait_for(timeout=MS)
        page.get_by_role("heading", name="Field notes").first.wait_for(timeout=MS)
        names(page, c=one, sources=source, file=None)
    assert page.errors == []


def test_a_slow_read_of_the_conversation_left_does_not_take_the_page_back(world, places, page):
    """One, then two, then three at once, with two's read answered only after three was chosen:
    the page and the address end on three, and Back is still two."""
    page.goto(world["base"] + "/?c=" + places["one"])
    shows(page, "one")
    start = entries(page)
    held = []
    page.route(re.compile(r"/api/conversations/" + places["two"] + r"\?batch="), lambda route: held.append(route))
    choose(page, "two")
    names(page, c=places["two"])
    for _ in range(100):
        if held:
            break
        page.wait_for_timeout(50)
    assert held, "the read of the second conversation was never asked for"
    choose(page, "three")
    shows(page, "three")
    names(page, c=places["three"])
    # NOW the second conversation's read answers
    answered = len(held)
    for route in list(held):
        route.continue_()
    assert answered >= 1
    page.unroute_all(behavior="wait")
    page.wait_for_timeout(1200)
    shows(page, "three")
    names(page, c=places["three"])
    assert page.get_by_text("A post in conversation two.", exact=True).count() == 0
    assert entries(page) == start + 2
    page.go_back()
    shows(page, "two")
    names(page, c=places["two"])
    assert page.errors == []


def test_forward_is_still_there_after_stay(world, places, page):
    """Stay on a leave question walks the browser back to where the reader was: nothing ahead of
    that entry is lost, and Forward from it is asked about and then goes."""
    page.goto(world["base"] + "/?c=" + places["one"])
    shows(page, "one")
    choose(page, "two")
    shows(page, "two")
    choose(page, "three")
    shows(page, "three")
    page.go_back()
    shows(page, "two")
    held = entries(page)
    box = _write_a_rule(page)
    ask = page.get_by_role("alertdialog")

    page.go_back()
    ask.wait_for(timeout=MS)
    ask.get_by_role("button", name="Stay").click()
    ask.wait_for(state="detached", timeout=MS)
    names(page, c=places["two"])
    assert box.input_value() == "Never deploy on a Friday."
    assert entries(page) == held, "Stay cut off or added to the history"

    # FORWARD is still the third conversation: asked about, since the words are still unrecorded
    page.go_forward()
    ask.wait_for(timeout=MS)
    ask.get_by_role("button", name="Discard changes and switch").click()
    ask.wait_for(state="detached", timeout=MS)
    shows(page, "three")
    names(page, c=places["three"])
    assert entries(page) == held
    # and Back from there is the second again
    page.go_back()
    names(page, c=places["two"])
    assert page.errors == []
