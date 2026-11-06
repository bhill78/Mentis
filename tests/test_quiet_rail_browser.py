"""PACKAGE B: the rail and its topic navigation, against real Mentis HTTP
routes on a disposable fixture Brain.

Build apps/fluid-web first. Opt in with MENTIS_QUIET_BROWSER=1; this needs
Playwright plus its Chromium and WebKit browsers, but no MARS or live Brain.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from mentis.conversation import text
from tests._loop import world  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.environ.get("MENTIS_QUIET_BROWSER") != "1",
    reason="set MENTIS_QUIET_BROWSER=1 after building the client",
)

WIDE = {"width": 1440, "height": 1000}


def _a_conversation_with_topics(world):
    """Three topics with deliberately different turn counts: a quiet one, a
    second EQUALLY quiet one (to isolate selection's own effect from the
    data's), and a busy one."""
    cv, owner = world["cv"], world["who"]["@brian"]
    cid = cv.open_conversation("Quiet rail", about="The margin a rail test reads.")
    cv.join(owner, cid)
    alpha = cv.open_topic(cid, "Alpha", about="One post filed here.")
    beta = cv.open_topic(cid, "Beta", about="Also one post filed here.")
    gamma = cv.open_topic(cid, "Gamma", about="Eight posts filed here.")
    cv.assign_topic(cv.say(cid, owner, [text("The one post under Alpha.")]), alpha)
    cv.assign_topic(cv.say(cid, owner, [text("The one post under Beta.")]), beta)
    for n in range(8):
        cv.assign_topic(cv.say(cid, owner, [text(f"A busy post under Gamma, number {n}.")]), gamma)
    return cid, alpha, beta, gamma


def _open(world, page, conversation):
    page.goto(world["base"] + f"/quiet#/c/{conversation}")
    page.get_by_role("heading", name="Quiet rail", exact=True).wait_for()
    page.locator(".qc-margin").wait_for()
    page.locator(".qc-topic-mark").first.wait_for()


def _marks(page):
    """Each topic mark's accessible name, aria-current and its bar's computed
    box -- the mark's own row is a fixed-height grid cell; the varying
    geometry (thickness, length) is drawn on the child `.qc-topic-bar`."""
    return page.evaluate("""
      () => [...document.querySelectorAll('.qc-topic-mark')].map((el) => {
        const bar = el.querySelector('.qc-topic-bar')
        const box = bar ? bar.getBoundingClientRect() : el.getBoundingClientRect()
        const label = el.querySelector('.qc-topic-label')
        return {
          name: el.getAttribute('aria-label'),
          current: el.getAttribute('aria-current'),
          width: box.width,
          height: box.height,
          labelVisibility: label ? getComputedStyle(label).visibility : null,
        }
      })
    """)


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_marks_are_sized_from_their_own_topics_turns(world, engine):
    playwright = pytest.importorskip("playwright.sync_api")
    assert (Path(__file__).parents[1] / "apps/fluid-web/dist/index.html").exists()
    conversation, alpha, beta, gamma = _a_conversation_with_topics(world)
    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport=WIDE)
            _open(world, page, conversation)
            marks = {m["name"].split(" — ")[0]: m for m in _marks(page)}
            assert set(marks) == {"Alpha", "Beta", "Gamma"}
            # Gamma (8 posts) draws thicker and longer than Alpha (1 post).
            assert marks["Gamma"]["height"] > marks["Alpha"]["height"], marks
            assert marks["Gamma"]["width"] > marks["Alpha"]["width"], marks
            # Two topics with the SAME turn count draw the same mark, neither selected.
            assert marks["Alpha"]["height"] == marks["Beta"]["height"]
            assert marks["Alpha"]["width"] == marks["Beta"]["width"]
        finally:
            browser.close()


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_marks_are_text_free_until_hovered_and_keep_an_accessible_name(world, engine):
    playwright = pytest.importorskip("playwright.sync_api")
    conversation, alpha, beta, gamma = _a_conversation_with_topics(world)
    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport=WIDE)
            _open(world, page, conversation)
            marks = _marks(page)
            # No visible text: every mark's name is carried only in aria-label,
            # and its label is not painted until the mark is reached.
            assert all(m["name"] for m in marks), "a mark has no accessible name"
            assert all(m["labelVisibility"] == "hidden" for m in marks), (
                "a topic's name is visible without hovering or focusing its mark")
            first = page.locator(".qc-topic-mark").first
            first.hover()
            revealed = first.locator(".qc-topic-label")
            assert revealed.evaluate("(el) => getComputedStyle(el).visibility") == "visible"
        finally:
            browser.close()


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_the_selected_topics_mark_is_emphasised_by_computed_size_not_only_colour(world, engine):
    playwright = pytest.importorskip("playwright.sync_api")
    conversation, alpha, beta, gamma = _a_conversation_with_topics(world)
    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport=WIDE)
            # Address Alpha directly: same turn count as Beta, so any difference
            # between the two below is selection's own computed effect, not the data's.
            page.goto(world["base"] + f"/quiet#/c/{conversation}/t/{alpha}")
            page.get_by_role("heading", name="Quiet rail", exact=True).wait_for()
            page.locator(".qc-topic-mark").first.wait_for()
            marks = {m["name"].split(" — ")[0]: m for m in _marks(page)}
            assert marks["Alpha"]["current"] == "page"
            assert marks["Beta"]["current"] is None
            assert marks["Alpha"]["height"] > marks["Beta"]["height"], marks
            assert marks["Alpha"]["width"] > marks["Beta"]["width"], marks
        finally:
            browser.close()


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_the_rails_top_edge_matches_the_headers_lower_edge(world, engine):
    """THE SHARED GRID, NOT A REPOSITION. `.qc-heading` and the work row's
    cells are two of `.qc`'s rows with no gap declared between them, so the
    margin's top is the heading row's bottom without B naming an offset."""
    playwright = pytest.importorskip("playwright.sync_api")
    conversation, *_ = _a_conversation_with_topics(world)
    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport=WIDE)
            _open(world, page, conversation)
            heading = page.locator(".qc-heading").bounding_box()
            margin = page.locator(".qc-margin").bounding_box()
            assert heading and margin, "the heading row and the margin must both exist"
            assert abs((heading["y"] + heading["height"]) - margin["y"]) <= 1, (
                f"the rail's top ({margin['y']}) does not meet the header's "
                f"lower edge ({heading['y'] + heading['height']})")
        finally:
            browser.close()


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_the_rail_tools_sit_outside_the_global_header(world, engine):
    """STRUCTURAL, not visual: Topics / Brief / Activity must not be inside
    `<header class="qc-global">`, which is the form "§3's words --
    subordinate to the global header -- actually take."""
    playwright = pytest.importorskip("playwright.sync_api")
    conversation, *_ = _a_conversation_with_topics(world)
    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport=WIDE)
            _open(world, page, conversation)
            tools = page.get_by_role("navigation", name="Conversation tools")
            tools.wait_for()
            inside = tools.evaluate("(el) => !!el.closest('header.qc-global')")
            assert not inside, "the rail's tools are inside the global header"
            # And they are, in fact, reachable: each control toggles the margin.
            page.get_by_role("button", name="Brief", exact=True).click()
            page.get_by_role("button", name="Close margin").wait_for()
            assert page.locator(".qc-topic-mark").count() == 0
        finally:
            browser.close()


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_conversation_lines_sit_left_of_topic_lines(world, engine):
    """THE CORRECTED CELL TABLE (§4 of ent-a2a1995e9f2c): conversation
    lines are the work row's FIRST cell (A's, left), topic lines the THIRD
    (B's, right). B does not build A's cell -- it is empty until A lands --
    but the geometry already places B strictly to its right."""
    playwright = pytest.importorskip("playwright.sync_api")
    conversation, *_ = _a_conversation_with_topics(world)
    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport=WIDE)
            _open(world, page, conversation)
            nav = page.locator(".qc-cell-nav").bounding_box()
            margin = page.locator(".qc-margin").bounding_box()
            assert nav and margin, "both the nav cell and the margin must exist"
            assert nav["x"] < margin["x"], (
                f"the margin ({margin['x']}) does not sit to the right of "
                f"the conversation-navigation cell ({nav['x']})")
        finally:
            browser.close()
