"""QUIET CHAT ROUND 5, PACKAGE W2: THE WORKING STAGE, AS IT IS DRAWN.

The claim is that the empty working area is now Fluid's OWN workspace over the
origin conversation's Holder -- not a second arrangement model beside it -- so
what this file checks is the rendered article, against real Mentis HTTP routes
on a disposable fixture Brain:

* THE STAGE DRAWS FLUID'S ZONES beside the Quiet reading, with the origin
  place's own Page sequence, and nothing in it throws. Governance and the post
  Actions are consumed UNCONDITIONALLY by Workspace and its zones, so a
  missing provider is a crash and not a blemish: every case here fails on a
  page error.
* A SECTION'S OWN MENU SPLITS IT AND UNDO TAKES IT BACK. That one gesture goes
  through the frame Layer (the menu is a Sheet), the installed action registry,
  the Holder's own edit and the lifted toast with its action -- four of the
  things W2 mounts -- so it is the honest end-to-end check of all of them.
* A CONVERSATION ZONE DRAWS THE EXPLICIT STAND-IN (F1) and never a second
  reader or composer: there is one Quiet reader, in the reading slot, the
  stand-in keeps its own section frame, and Return to conversation works.
* A FRESH SESSION WITH NOTHING BUT THIS BROWSER'S localStorage comes back to
  the Page that was selected and the trees that were on it.
* AN UNKNOWN PAGE falls back to the conversation visibly -- which can only be
  said once the runtime has hydrated its Pages (`ready`), and is the message
  R's correction gated on exactly that.
* /fluid IS UNCHANGED with the seams omitted: the same fixtures, the shared
  Workspace, Boundary and Holder defaults, and Fluid's own conversation zone
  rather than Quiet's stand-in (the plan's section 4 compatibility case).

HOW THE ROOM AND THE PAGES ARE SEATED. The bootstrap room shows the
conversation alone and parks the working surface -- which main surface is
shown is L's decision to draw -- and the Page strip and arrows are P's and
draw nothing yet. So the cases below seat a saved room bookmark and a saved
arrangement in this browser's own store, exactly as a reviewer's previous
session would have left them, rather than adding a test-only route or
pretending a control exists.

What is NOT claimed here: the floating windows, the Magnet discs and the
object viewer are package O's hosts and are not mounted yet, so this file
checks that their absence is SAID and never reported as a success.

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

#: The envelope's key prefix (quiet/workspace/bookmarks.ts).
ENVELOPE = "mentis:quiet:workspace:v1:"
#: The whole of this browser's local store, and putting it back in another one.
KEPT = "() => Object.fromEntries(Object.entries(localStorage))"
SEED = "(() => { const d = %s; for (const k in d) localStorage.setItem(k, d[k]) })()"

ZONES_ON = (
    "(p) => document.querySelectorAll("
    "  '.qw-stage .wk-page[data-page=\"' + p + '\"] .wk-zone').length"
)


def _zone(zid, name="Stage", show="objects"):
    """One section, as the arrangement format keeps it."""
    z = {"type": "zone", "id": zid, "show": show, "name": name}
    if show == "objects":
        z["slot"] = {"follow": True, "show": "objects", "items": [], "present": "cards"}
    return z


def _layout(pages=()):
    """A place's arrangement, in the one representation the Holder and the
    envelope both use (`toLayout(..., {tab: true})`)."""
    out = {
        "format": "mentis.fluid-arrangement",
        "version": 3,
        "tree": _zone("z-root"),
    }
    if pages:
        out["pages"] = [
            {"id": p, "title": t, "tree": _zone("z-" + p, name="Stage")} for p, t in pages
        ]
    return out


def _a_place(world, name="Quiet working"):
    """A conversation with enough in it to work beside."""
    cv, owner = world["cv"], world["who"]["@brian"]
    cid = cv.open_conversation(name, about="Somewhere to work beside.")
    cv.join(owner, cid)
    for n in range(6):
        cv.say(cid, owner, [text(f"A post to work beside, number {n}.")])
    return cid


def _opened(page, name="Quiet working"):
    page.get_by_role("heading", name=name, exact=True).wait_for()
    page.locator(".qc-post").first.wait_for()


def _errors(page):
    found: list[str] = []
    page.on("pageerror", lambda error: found.append(str(error)))
    return found


def _envelope_key(page, tries=60):
    """The envelope this browser wrote for this origin. Polled, because the
    layout write is coalesced on purpose -- a drag is one arrangement, not
    sixty -- so it is not there on the first paint."""
    for _ in range(tries):
        keys = [k for k in page.evaluate("() => Object.keys(localStorage)")
                if k.startswith(ENVELOPE)]
        if keys:
            return keys[0]
        time.sleep(0.1)
    raise AssertionError("the bookmark wrote no envelope for this origin")


def _seat(page, *, mode="panes", layout=None, selected=None, rooms=("this-post",)):
    """Leave this browser as a previous session would have left it: the room
    the reviewer chose -- which is kept PER PAGE, so every Page they would
    look at gets one -- the arrangement they had, and the Page they were on."""
    key = _envelope_key(page)
    # let the coalesced write settle, so what is seated is not overwritten
    time.sleep(0.8)
    page.evaluate(
        """([key, mode, layout, selected, rooms]) => {
            const e = JSON.parse(localStorage.getItem(key))
            e.rooms = { ...(e.rooms || {}) }
            for (const p of rooms) e.rooms[p] = { mode, readingPx: 420 }
            if (layout) e.layout = layout
            if (selected) e.selectedPage = selected
            localStorage.setItem(key, JSON.stringify(e))
        }""",
        [key, mode, layout, selected, list(rooms)],
    )
    return key


def _in_the_room(world, browser_, cid, *, viewport=None, mode="panes", layout=None,
                 selected=None, at="", name="Quiet working", rooms=("this-post",)):
    """A PREVIOUS SESSION LEFT IT LIKE THIS, and this is the next one.

    The arrangement seated has to be entered as a NEW SESSION's, not as a
    reload's: F9 says this tab's own copy wins a same-tab reload, and the
    Holder writes one as soon as it applies a kind's default layout -- so
    seating a durable layout and reloading would (correctly) keep the first
    visit's arrangement instead. The seating visit and the visit under test
    are therefore two contexts, with this browser's localStorage carried
    between them and nothing else, which is also the owner's own claim
    (opr-8cf7688b6555)."""
    first = browser_.new_context(viewport=viewport or WIDE)
    try:
        page0 = first.new_page()
        page0.goto(world["base"] + f"/quiet#/c/{cid}")
        _opened(page0, name)
        _seat(page0, mode=mode, layout=layout, selected=selected, rooms=rooms)
        kept = page0.evaluate(KEPT)
    finally:
        first.close()
    ctx = browser_.new_context(viewport=viewport or WIDE)
    ctx.add_init_script(SEED % json.dumps(kept))
    page = ctx.new_page()
    errors = _errors(page)
    page.goto(world["base"] + f"/quiet#/c/{cid}{at}")
    _opened(page, name)
    page.locator(".qw-area").wait_for(timeout=15000)
    page.locator(".qw-stage .wk").wait_for(timeout=15000)
    return page, ctx, errors


def _split_the_section(page, on):
    """Split the section on Page `on` through its own actions menu. The ⚙ is
    quiet until the section is pointed at or focused (Fluid's own rule), so
    this points at it first, as a reviewer does."""
    was = page.evaluate(ZONES_ON, on)
    zone = page.locator(f'.qw-stage .wk-page[data-page="{on}"] .wk-zone').first
    zone.wait_for(timeout=15000)
    zone.hover()
    menu = page.locator(f'.qw-stage .wk-page[data-page="{on}"] button.sc-t2').first
    menu.wait_for(timeout=15000)
    menu.click()
    # "Side" -- the host's own way of splitting this section (its registry
    # variant), under the Split action in the menu. Wide the menu is a frame
    # Sheet in the layer; coarse and compact it is the chrome's own bottom
    # sheet, so the control is found by what it IS rather than by where it is
    # drawn.
    side = page.locator('[data-variant="split-row"]').first
    side.wait_for(timeout=15000)
    assert side.get_attribute("aria-disabled") is None, "Split side by side was refused"
    # WHILE IT IS OPEN: wide, that menu is drawn in the frame's own layer,
    # outside the stage -- which is the whole reason the layer is mounted here.
    in_layer = page.evaluate(
        "() => document.querySelector('#fx-layer').childElementCount")
    side.click()
    page.wait_for_function(
        "([p, was]) => document.querySelectorAll("
        "  '.qw-stage .wk-page[data-page=\"' + p + '\"] .wk-zone').length > was",
        arg=[on, was], timeout=15000)
    return was, in_layer


@browser
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
@pytest.mark.parametrize("viewport", [WIDE, NARROW], ids=["1440x900", "390x844"])
def test_the_stage_draws_fluid_zones_over_the_origin_place(world, engine, viewport):
    """THE WORKING AREA IS FLUID'S WORKSPACE, over the ORIGIN place: its Page
    sequence is the arrangement's own list, hydrated by the one entrance, and
    every provider its zones read is real."""
    playwright = pytest.importorskip("playwright.sync_api")
    assert (Path(__file__).parents[1] / "apps/fluid-web/dist/index.html").exists()
    cid = _a_place(world)
    with playwright.sync_playwright() as p:
        browser_ = getattr(p, engine).launch()
        try:
            page, ctx, errors = _in_the_room(
                world, browser_, cid, viewport=viewport,
                layout=_layout([("page-2", "Notes")]))

            assert page.evaluate(ZONES_ON, "this-post") >= 1, "no zone in the stage"
            # THE ONE PAGE LIST: the arrangement's pages are nav's pages, so
            # the stage draws the sequence rather than a copy of it.
            assert page.locator('.qw-stage .wk-page[data-page="page-2"]').count() == 1
            # ONE reader and ONE composer, still in the reading slot.
            assert page.locator("#qc-stream").count() == 1
            assert page.locator(".qw-stage #qc-stream").count() == 0
            assert errors == [], errors
        finally:
            browser_.close()


@browser
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_a_section_menu_splits_the_stage_and_undo_takes_it_back(world, engine):
    """ONE GESTURE THROUGH FOUR MOUNTS: the Layer the menu is drawn in, the
    installed action registry the menu is built from, the Holder's edit, and
    the lifted toast whose Undo takes it back."""
    playwright = pytest.importorskip("playwright.sync_api")
    cid = _a_place(world)
    with playwright.sync_playwright() as p:
        browser_ = getattr(p, engine).launch()
        try:
            page, ctx, errors = _in_the_room(world, browser_, cid)
            was, in_layer = _split_the_section(page, "this-post")
            assert in_layer >= 1, "the section menu was not drawn in the frame's layer"

            undo = page.locator("#toastAct")
            undo.wait_for(timeout=15000)
            assert undo.inner_text().strip() == "Undo"
            undo.click()
            page.wait_for_function(
                "([p, was]) => document.querySelectorAll("
                "  '.qw-stage .wk-page[data-page=\"' + p + '\"] .wk-zone').length === was",
                arg=["this-post", was], timeout=15000)
            assert errors == [], errors
        finally:
            browser_.close()


@browser
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_a_conversation_zone_draws_the_stand_in_and_returns(world, engine):
    """F1: QUIET NEVER LETS THE WORKSPACE TAKE ITS READER. A zone that would
    show the conversation says where the conversation is, keeps its own section
    frame -- so the stored zone, its splits and their Undo are untouched -- and
    its Return to conversation works. No second reader, no second composer."""
    playwright = pytest.importorskip("playwright.sync_api")
    cid = _a_place(world)
    conv = {"format": "mentis.fluid-arrangement", "version": 3,
            "tree": _zone("z-conv", name="Conversation", show="conversation")}
    with playwright.sync_playwright() as p:
        browser_ = getattr(p, engine).launch()
        try:
            page, ctx, errors = _in_the_room(world, browser_, cid, layout=conv)

            stand = page.locator(".qw-conv-stand")
            stand.wait_for(timeout=15000)
            assert "Conversation is in the reading area" in stand.inner_text()
            # Still a section: its own actions are there, so the stored zone
            # and every structural edit on it are exactly what they were.
            assert stand.locator("button.sc-t2").count() == 1
            # Fluid's own conversation host is NOT claimed here.
            assert page.locator('.qw-stage [data-zone="conversation"] #qc-stream').count() == 0
            assert page.locator("#qc-stream").count() == 1
            assert page.locator(".qw-stage .qc-composer").count() == 0

            stand.get_by_role("button", name="Return to conversation").click()
            page.locator("#qc-stream").wait_for()
            assert errors == [], errors
        finally:
            browser_.close()


@browser
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_a_fresh_session_restores_the_selected_page_and_its_trees(world, engine):
    """ACROSS SESSIONS IN THIS BROWSER (opr-8cf7688b6555), with nothing but
    localStorage and the BARE address -- which says nothing itself, so what
    the reader left is what opens: the Page they were on, and the tree on it."""
    playwright = pytest.importorskip("playwright.sync_api")
    cid = _a_place(world)
    with playwright.sync_playwright() as p:
        browser_ = getattr(p, engine).launch()
        try:
            page, ctx, errors = _in_the_room(
                world, browser_, cid, layout=_layout([("page-2", "Notes")]),
                at="/qpage/page-2", rooms=("this-post", "page-2"))
            page.locator('.qw-stage .wk-page[data-page="page-2"]').wait_for(timeout=15000)
            _split_the_section(page, "page-2")
            time.sleep(1.0)  # the coalesced write settles

            kept = page.evaluate(KEPT)
            assert any(k.startswith(ENVELOPE) for k in kept), sorted(kept)
            fresh = browser_.new_context(viewport=WIDE)
            try:
                fresh.add_init_script(SEED % json.dumps(kept))
                second = fresh.new_page()
                errors2 = _errors(second)
                second.goto(world["base"] + f"/quiet#/c/{cid}")
                _opened(second)
                # The Page is the one that was left, and the address says so.
                second.wait_for_function(
                    "() => location.hash.includes('/qpage/page-2')", timeout=15000)
                second.locator('.qw-stage .wk-page[data-page="page-2"]').wait_for(timeout=15000)
                second.wait_for_function(ZONES_ON + " >= 2", arg="page-2", timeout=15000)
                assert errors2 == [], errors2
            finally:
                fresh.close()
            assert errors == [], errors
        finally:
            browser_.close()


@browser
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_an_unknown_page_falls_back_to_the_conversation_once_it_is_decided(world, engine):
    """A PAGE THIS BROWSER DOES NOT HAVE -- another browser's arrangement, or
    one since closed -- is said so, and the conversation is shown. It can only
    be said once the runtime has hydrated its Pages, which is what `ready`
    answers: before that an absence from the list is not an answer, and
    nothing is said and nothing is rewritten."""
    playwright = pytest.importorskip("playwright.sync_api")
    cid = _a_place(world)
    with playwright.sync_playwright() as p:
        browser_ = getattr(p, engine).launch()
        try:
            page = browser_.new_page(viewport=WIDE)
            errors = _errors(page)
            page.goto(world["base"] + f"/quiet#/c/{cid}/qpage/page-404")
            _opened(page)
            page.wait_for_function(
                "() => (document.querySelector('.qc-notice')?.textContent || '')"
                "  .includes('That page is not in this browser')",
                timeout=20000)
            # And the address is put back, not left naming a Page nobody can
            # return to.
            page.wait_for_function(
                "() => !location.hash.includes('/qpage/page-404')", timeout=15000)
            assert page.locator("#qc-stream").count() == 1
            assert errors == [], errors
        finally:
            browser_.close()


@browser
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_no_object_host_is_claimed_before_its_package_lands(world, engine):
    """NO INVISIBLE SUCCESSFUL ACTION. The object viewer, the floating windows
    and the Magnet discs are package O's hosts; until they are mounted the
    stage draws nothing for them and claims nothing about them, and the two
    fixed mount points -- O's area and T's controls -- are there exactly once
    each."""
    playwright = pytest.importorskip("playwright.sync_api")
    cid = _a_place(world)
    with playwright.sync_playwright() as p:
        browser_ = getattr(p, engine).launch()
        try:
            page, ctx, errors = _in_the_room(world, browser_, cid)
            assert page.locator(".qw-hosts").count() == 1
            assert page.evaluate(
                "() => document.querySelector('.qw-hosts').childElementCount") == 0
            assert page.locator('[data-slot="workspaceControls"]').count() == 1
            assert page.locator(".fx-viewer, .fq-floats, .fx-dock").count() == 0
            assert errors == [], errors
        finally:
            browser_.close()


@browser
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
@pytest.mark.parametrize("viewport", [WIDE, NARROW], ids=["1440x900", "390x844"])
def test_the_same_fixtures_still_work_at_fluid_with_the_seams_omitted(world, engine, viewport):
    """THE EXPLICIT /fluid COMPATIBILITY CASE (plan section 4). Default /fluid
    supplies none of W1's optional seams: the place is the conversation nav is
    at, the conversation zone is Fluid's own and never Quiet's stand-in, and
    nothing of Quiet's stage is in that tree."""
    playwright = pytest.importorskip("playwright.sync_api")
    cid = _a_place(world)
    with playwright.sync_playwright() as p:
        browser_ = getattr(p, engine).launch()
        try:
            page = browser_.new_page(viewport=viewport)
            errors = _errors(page)
            page.goto(world["base"] + f"/fluid?c={cid}")
            # Attached, not visible: narrow, /fluid parks the workspace in its
            # own sheet pane until it is asked for, which is Fluid's own
            # behaviour and is deliberately unchanged here.
            page.locator('[aria-label="workspace"]').wait_for(
                state="attached", timeout=30000)
            page.wait_for_function(
                "() => document.querySelectorAll("
                "  '[aria-label=\"workspace\"] .wk-page').length >= 1",
                timeout=30000)
            # Quiet's stand-in and its stage are nowhere in /fluid.
            assert page.locator(".qw-conv-stand").count() == 0
            assert page.locator(".qw-area").count() == 0
            # Fluid's own frame is still the frame: one layer target and its
            # own toast, both mounted by Shell as they always were.
            assert page.locator("#fx-layer").count() == 1
            assert page.locator("#toast").count() == 1
            assert errors == [], errors
        finally:
            browser_.close()
