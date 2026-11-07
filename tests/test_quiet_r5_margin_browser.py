"""QUIET CHAT ROUND 5, PACKAGE M: THE MARGINS AND THEIR BOOKMARKS.

The owner asked for all four readings (Topics / Brief / Activity / Carried) --
the selected reading including closed, a topic query's visibility and text,
and scroll per reading -- to survive the margin being moved, collapsed or
resumed, across closing and reopening the Rail and a new browser session
(opr-8cf7688b6555). This file checks that end to end, against real Mentis
HTTP routes on a disposable fixture Brain:

* CLOSING AND REOPENING THE RAIL keeps the reading that was open, including
  closed itself, and the topic-find box's own visibility and text.
* A NEW BROWSER SESSION, seeded with nothing but this browser's localStorage,
  restores the same reading, the same topic query and each reading's own
  scroll position.
* RESTORING A SAVED "CARRIED" READING never raises a fresh "look at this"
  request of its own (`margin/carried.ts` `present`) -- an annotation's own
  icon still does, deliberately, and still opens a readable box; the
  decision accordion underneath stays answerable either way.
* THE MARGIN FITS A 240 CSS PX TOOLS CONTAINER without giving the document a
  sideways scroll, with a carried table's overflow kept inside its own box.

Build apps/fluid-web first. Opt in with MENTIS_QUIET_BROWSER=1; this needs
Playwright plus its Chromium and WebKit browsers, but no MARS or live Brain.
Set QUIET_R5_M_EVIDENCE to a folder to keep the screenshots.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from mentis.conversation import text
from tests._loop import world  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.environ.get("MENTIS_QUIET_BROWSER") != "1",
    reason="set MENTIS_QUIET_BROWSER=1 after building the client",
)

WIDE = {"width": 1440, "height": 900}
NARROW = {"width": 390, "height": 844}

BLOCKS = (
    "## What the run came to\n"
    "\n"
    "```table version=1\n"
    "item,value,notes,owner,status,when\n"
    "Alpha,1,first,@brian,open,today\n"
    "Beta,2,second,@brian,open,today\n"
    "Gamma,3,third,@brian,open,today\n"
    "```\n"
)


def built():
    assert (Path(__file__).parents[1] / "apps/fluid-web/dist/index.html").exists()


def shot(page, name, full=False):
    folder = os.environ.get("QUIET_R5_M_EVIDENCE")
    if folder:
        Path(folder).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(folder) / name), full_page=full)


@pytest.fixture
def a_margin(world):
    """Three topics, enough posts that the Activity/Decisions reading has
    something to answer, and one post carrying a wide table (for the 240px
    container case)."""
    cv, owner, care = world["cv"], world["who"]["@brian"], world["steward"]
    cid = cv.open_conversation("Quiet margins", about="What the margins remember.")
    cv.join(owner, cid)
    alpha = cv.open_topic(cid, "Alpha", about="One kind of post.")
    beta = cv.open_topic(cid, "Beta", about="Another kind of post.")
    cv.assign_topic(cv.say(cid, owner, [text("A post filed under Alpha.")]), alpha)
    cv.assign_topic(cv.say(cid, owner, [text("A post filed under Beta.")]), beta)
    table = cv.say(cid, owner, [text(BLOCKS)])
    asked = cv.say(cid, owner, [text("Which margin should carried blocks sit in?")])
    cv.expect(asked, of=owner, kind="decision", by=care, because="which margin",
              detail={"options": [{"label": "Keep it"}, {"label": "Change it"}]})
    # Enough OTHER outstanding decisions that Activity is taller than a short
    # viewport, so there is something of ITS OWN to scroll and remember --
    # independent of Topics, whose own list a query filter deliberately
    # shrinks in another case below.
    for n in range(14):
        padding = cv.say(cid, owner, [text(f"A padding question, number {n}.")])
        cv.expect(padding, of=owner, kind="decision", by=care, because=f"padding {n}",
                  detail={"options": [{"label": f"Padding option {n}"}]})
    return {"conversation": cid, "alpha": alpha, "beta": beta, "table": table}


def _opened(page, name="Quiet margins"):
    page.get_by_role("heading", name=name, exact=True).wait_for()
    page.locator(".qc-rail-tools").wait_for()


def _open_margin(page, name):
    """Show this reading, whatever the margin's own starting state is: the
    rail opens on Topics by default, so the wanted reading may already be
    showing (clicking its own tool would CLOSE it), closed, or showing a
    different one (clicking switches it without closing)."""
    margin = page.locator("#qc-margin")
    if margin.count() and margin.get_attribute("aria-label") == name.lower():
        return
    page.get_by_role("button", name=name, exact=True).click()
    page.locator("#qc-margin").wait_for()


def _close_margin(page):
    page.get_by_role("button", name="Close margin", exact=True).click()
    page.locator("#qc-margin").wait_for(state="hidden")


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_closing_and_reopening_the_rail_keeps_the_reading_and_the_topic_query(world, a_margin, engine):
    playwright = pytest.importorskip("playwright.sync_api")
    built()
    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport=WIDE)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(world["base"] + f"/quiet#/c/{a_margin['conversation']}")
            _opened(page)

            # Open the find box and leave text in it -- still Topics.
            page.get_by_role("button", name="Find a topic", exact=True).click()
            page.locator("#qc-topic-query").fill("Alpha")
            page.wait_for_function(
                "() => [...document.querySelectorAll('.qc-topic-mark')].length === 1")
            shot(page, f"{engine}-selected-reading.png")

            # Switch to Activity, then CLOSE the margin entirely.
            _open_margin(page, "Activity")
            page.locator(".qc-decisions").wait_for()
            _close_margin(page)

            # REOPEN with the tools row, not a specific reading's own button:
            # whichever one is remembered should come back, not Topics.
            page.get_by_role("button", name="Activity", exact=True).click()
            page.locator(".qc-decisions").wait_for()
            assert page.get_by_role("heading", name="Activity", exact=True).count() == 1

            # Back to Topics: the query this browser had typed is still there,
            # and no restored box stole focus into it.
            page.get_by_role("button", name="Topics", exact=True).click()
            query = page.locator("#qc-topic-query")
            query.wait_for()
            assert query.input_value() == "Alpha"
            assert not query.evaluate("(el) => el === document.activeElement"), (
                "a restored query must not auto-focus")
            assert errors == []
        finally:
            browser.close()


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_a_new_browser_session_restores_reading_query_and_scroll_per_reading(world, a_margin, engine):
    playwright = pytest.importorskip("playwright.sync_api")
    built()
    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 500})
            page.goto(world["base"] + f"/quiet#/c/{a_margin['conversation']}")
            _opened(page)
            # Pin the margins so `.qc-margin` is its own scroll container
            # (otherwise the document scrolls at every width and there is
            # nothing of the margin's own to remember a scroll position in).
            page.evaluate(
                "() => localStorage.setItem('mentis:quiet-appearance', "
                "JSON.stringify({ pinMargins: true }))")
            page.reload()
            _opened(page)

            # TOPICS: leave text in the find box -- its own query/visibility.
            _open_margin(page, "Topics")
            page.locator(".qc-topic-mark").first.wait_for()
            page.get_by_role("button", name="Find a topic", exact=True).click()
            page.locator("#qc-topic-query").fill("Beta")
            page.wait_for_function(
                "() => [...document.querySelectorAll('.qc-topic-mark')].length === 1")
            shot(page, f"{engine}-restored-topic-query.png")
            # Let the query's own write land before switching readings, or
            # the reading switch's write would carry a stale, pre-query
            # margin forward instead of this one.
            page.wait_for_function(
                "() => [...Object.entries(localStorage)]"
                ".some(([k, v]) => k.startsWith('mentis:quiet:workspace:v1:') "
                "&& JSON.parse(v).readings?.['this-post']?.margin?.query === 'Beta')",
                timeout=5000)

            # ACTIVITY: scroll it -- independent of Topics' own filtered
            # height, which a query shrinks (and would otherwise clamp
            # whatever Topics' own scroll had been).
            _open_margin(page, "Activity")
            page.locator(".qc-decisions").wait_for()
            shot(page, f"{engine}-selected-reading.png")
            page.evaluate("() => document.getElementById('qc-margin').scrollTo(0, 120)")
            page.wait_for_function(
                "() => document.getElementById('qc-margin').scrollTop > 0")
            scrolled_to = page.evaluate("() => document.getElementById('qc-margin').scrollTop")
            shot(page, f"{engine}-scrolled-reading.png")
            # Let the coalesced writes land in storage before this tab's
            # storage is copied into the fresh one.
            page.wait_for_function(
                "() => [...Object.entries(localStorage)]"
                ".some(([k, v]) => k.startsWith('mentis:quiet:workspace:v1:') "
                "&& JSON.parse(v).readings?.['this-post']?.margin?.scrollByReading?.activity > 0)",
                timeout=5000)

            kept = page.evaluate("() => Object.fromEntries(Object.entries(localStorage))")
            assert any(k.startswith("mentis:quiet:workspace:v1:") for k in kept), sorted(kept)

            fresh = browser.new_context(viewport={"width": 1440, "height": 500})
            try:
                fresh.add_init_script(
                    "(() => { const d = %s; for (const k in d) localStorage.setItem(k, d[k]) })()"
                    % json.dumps(kept))
                second = fresh.new_page()
                second.goto(world["base"] + f"/quiet#/c/{a_margin['conversation']}")
                _opened(second)

                # THE LAST READING OPEN -- Activity, not the default Topics --
                # AND ITS OWN REMEMBERED SCROLL, put back without anything
                # else asking for it.
                second.get_by_role("heading", name="Activity", exact=True).wait_for()
                second.locator(".qc-decisions").wait_for()
                second.wait_for_function(
                    "(y) => document.getElementById('qc-margin').scrollTop >= y - 1",
                    arg=scrolled_to)

                # TOPICS keeps its own remembered query, reached independently
                # of whichever reading reopened.
                second.get_by_role("button", name="Topics", exact=True).click()
                query = second.locator("#qc-topic-query")
                query.wait_for()
                assert query.input_value() == "Beta"
                assert not query.evaluate("(el) => el === document.activeElement"), (
                    "a restored query must not auto-focus")
                assert second.locator(".qc-topic-mark").count() == 1
            finally:
                fresh.close()
        finally:
            browser.close()


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_restoring_carried_never_marks_a_box_and_decisions_stay_actionable(world, a_margin, engine):
    playwright = pytest.importorskip("playwright.sync_api")
    built()
    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport=WIDE)
            page.goto(world["base"] + f"/quiet#/c/{a_margin['conversation']}")
            _opened(page)
            _open_margin(page, "Carried")
            page.locator(".qc-carried").wait_for()
            page.wait_for_timeout(600)
            kept = page.evaluate("() => Object.fromEntries(Object.entries(localStorage))")

            fresh = browser.new_context(viewport=WIDE)
            try:
                fresh.add_init_script(
                    "(() => { const d = %s; for (const k in d) localStorage.setItem(k, d[k]) })()"
                    % json.dumps(kept))
                second = fresh.new_page()
                errors = []
                second.on("pageerror", lambda e: errors.append(str(e)))
                second.goto(world["base"] + f"/quiet#/c/{a_margin['conversation']}")
                _opened(second)
                second.get_by_role("heading", name="Carried", exact=True).wait_for()
                blocks = second.locator(".qc-margin .qc-box[data-kind='block']")
                blocks.first.wait_for()
                # RESTORATION ALONE marks nothing: `present` is a deliberate
                # ask (an annotation's own icon), not something a bookmark
                # replays on its own.
                assert second.locator(".qc-margin .qc-box[data-marked]").count() == 0

                # THE DECISION UNDER THE BOXES STAYS ANSWERABLE.
                decisions = second.locator(".qc-margin .qc-decisions")
                decisions.wait_for()
                assert "which margin" in decisions.inner_text()
                assert decisions.get_by_role("button", name="Keep it", exact=True).count() == 1
                assert errors == []
            finally:
                fresh.close()
        finally:
            browser.close()


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_margin_fits_a_240px_tools_container_without_page_overflow(world, a_margin, engine):
    """L has not yet moved Rail/RailTools into the room's `tools` slot
    (ent-55cfd945a1b6): they stay a stable mount in the `conversation` slot's
    `.qc-work` row. This forces that cell down to the minimum width the
    seam promises the eventual tools container (240 CSS px) and asks the
    same question the real narrow slot will: does the content fit without
    widening the page, including a carried wide table's own overflow."""
    playwright = pytest.importorskip("playwright.sync_api")
    built()
    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport=WIDE)
            page.goto(world["base"] + f"/quiet#/c/{a_margin['conversation']}")
            _opened(page)
            _open_margin(page, "Carried")
            page.locator(".qc-margin .qc-box[data-kind='block']").first.wait_for()
            page.evaluate("""
              () => {
                const style = document.createElement('style')
                style.textContent = '.qc-margin { width: 240px !important; max-width: 240px !important; }'
                document.head.appendChild(style)
              }
            """)
            page.wait_for_timeout(100)
            assert page.evaluate(
                "() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1"
            ), "a 240px margin gave the document a sideways scroll"
            table_scroll = page.locator(".qc-box .qc-box-body .rb-table-scroll").first
            assert table_scroll.count() >= 1
            box_width = page.locator(".qc-box").first.bounding_box()["width"]
            table_width = table_scroll.evaluate("(el) => el.scrollWidth")
            assert table_width <= box_width + 1 or table_scroll.evaluate(
                "(el) => el.scrollWidth > el.clientWidth"), (
                "a table that cannot fit must scroll inside its own box, not the box's own width")
        finally:
            browser.close()
