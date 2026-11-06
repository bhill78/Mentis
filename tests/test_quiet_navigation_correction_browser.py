"""Track 2 corrections against real HTTP routes and a disposable fixture Brain.

Build the UI, then set MENTIS_QUIET_BROWSER=1. No live Brain or MARS is used.
"""
from pathlib import Path
import os

import pytest

from mentis.conversation import text
from tests._loop import world  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.environ.get("MENTIS_QUIET_BROWSER") != "1",
    reason="build the UI and set MENTIS_QUIET_BROWSER=1",
)


@pytest.fixture
def navigation(world):
    cv, owner = world["cv"], world["who"]["@brian"]
    for n in range(7):
        other = cv.open_conversation(f"Navigation filler {n}" + (" long-conversation-name-" * 12 if n == 6 else ""))
        cv.join(owner, other)
        cv.say(other, owner, [text("A short note.")])
    name = "Navigation correction"
    cid = cv.open_conversation(name)
    cv.join(owner, cid)
    quiet = cv.open_topic(cid, "Quiet topic", about="One note")
    busy = cv.open_topic(cid, "Busy topic " + "long-topic-name-" * 15)
    cv.assign_topic(cv.say(cid, owner, [text("Quiet note")]), quiet)
    for n in range(12):
        cv.assign_topic(cv.say(cid, owner, [text(f"Busy note {n}")]), busy)
    return cid, name, quiet, busy


def open_page(world, navigation, browser):
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.goto(world["base"] + f"/quiet#/c/{navigation[0]}")
    page.get_by_role("heading", name=navigation[1], exact=True).wait_for()
    page.locator(".qc-topic-bar").first.wait_for()
    return page


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_upright_lines_hover_and_single_selector(world, navigation, engine):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = open_page(world, navigation, browser)
            assert page.locator(".qc-navigation").count() == 0
            assert page.locator(".qc-nav").count() == 1
            for selector in (".qc-nav-mark-bar", ".qc-topic-bar"):
                boxes = page.locator(selector).evaluate_all(
                    "els => els.map(e => ({w:e.getBoundingClientRect().width,h:e.getBoundingClientRect().height}))")
                assert all(b["h"] > b["w"] > 0 for b in boxes), boxes
                assert len({b["w"] for b in boxes}) > 1, boxes
            for row, label in ((".qc-nav-mark", ".qc-nav-mark-label"),
                               (".qc-topic-mark", ".qc-topic-label")):
                page.mouse.move(700, 10)
                first = page.locator(row).first
                assert first.locator(label).evaluate("e => getComputedStyle(e).visibility") == "hidden"
                first.hover()
                assert first.locator(label).evaluate("e => getComputedStyle(e).visibility") == "visible"
                first.focus()
                assert first.locator(label).evaluate("e => getComputedStyle(e).visibility") == "visible"
                assert first.get_attribute("aria-label")
                page.locator(".qc-brand").focus()
            page.screenshot(path=Path(world["root"]).parent / f"track2-wide-{engine}.png")
        finally:
            browser.close()


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_compact_filters_navigation_and_settings(world, navigation, engine):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = open_page(world, navigation, browser)
            nav = page.locator(".qc-nav")
            assert nav.locator(".qc-nav-mark").count() == 5
            nav.get_by_role("button", name="more", exact=False).click()
            assert nav.locator(".qc-nav-mark").count() > 5
            nav.get_by_role("button", name="Show fewer").click()
            assert nav.locator(".qc-nav-mark").count() == 5
            nav.get_by_role("button", name="Find a conversation").click()
            nav.get_by_role("searchbox").fill("Navigation filler 0")
            assert nav.locator(".qc-nav-mark").count() == 1
            nav.locator(".qc-nav-mark").click()
            page.get_by_role("heading", name="Navigation filler 0", exact=True).wait_for()
            page.goto(world["base"] + f"/quiet#/c/{navigation[0]}")
            page.get_by_role("heading", name=navigation[1], exact=True).wait_for()
            nav.get_by_role("button", name="Find a conversation").click()
            nav.get_by_role("searchbox").fill("no-such-conversation")
            nav.get_by_text("No conversations found.").wait_for()
            nav.get_by_role("searchbox").press("Escape")
            assert nav.get_by_role("searchbox").count() == 0
            assert nav.get_by_role("button", name="Find a conversation").evaluate("e => e === document.activeElement")
            page.get_by_role("button", name="Find a topic").click()
            page.get_by_role("searchbox", name="Find a topic").fill("Quiet")
            assert page.locator(".qc-topic-mark").count() == 1
            page.locator(".qc-topic-mark").click()
            page.wait_for_url(f"**/t/{navigation[2]}")
            page.locator(".qc-topic-mark[aria-current='page']").wait_for()
            page.get_by_role("link", name="All posts", exact=True).click()
            page.wait_for_url(f"**/c/{navigation[0]}")
            settings = page.get_by_label("Settings", exact=True)
            assert not page.get_by_label("Background", exact=True).is_visible()
            settings.click()
            page.get_by_label("Background", exact=True).wait_for(state="visible")
            page.get_by_label("Background", exact=True).select_option("default")
            page.get_by_role("radio", name="Glass", exact=True).click()
            assert page.get_by_role("radio", name="Glass", exact=True).is_checked()
            page.get_by_role("radio", name="Glass", exact=True).press("Escape")
            assert not page.get_by_label("Background", exact=True).is_visible()
            assert settings.evaluate("e => e === document.activeElement")
        finally:
            browser.close()


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_actual_container_width_and_mobile_overflow(world, navigation, engine):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = open_page(world, navigation, browser)
            page.get_by_role("button", name="Find a conversation").click()
            page.get_by_role("button", name="Find a topic").click()
            # Narrow the cells while leaving the viewport wide. A media query
            # alone cannot pass these checks, including labels on engagement.
            for width in (220, 160, 120, 80):
                page.evaluate("w => { for (const s of ['.qc-cell-nav','.qc-margin']) document.querySelector(s).style.width = w+'px' }", width)
                for selector in (".qc-nav", ".qc-margin"):
                    page.locator(selector).hover()
                    assert page.locator(selector).evaluate("e => e.scrollWidth <= e.clientWidth + 1"), (selector, width)
                    bounds = page.locator(selector).evaluate("e => {const r=e.getBoundingClientRect(); return [...e.querySelectorAll('a,input,button')].every(c=>{const b=c.getBoundingClientRect();return b.left>=r.left-1 && b.right<=r.right+1})}")
                    assert bounds, (selector, width)
            page.evaluate("() => { for (const s of ['.qc-cell-nav','.qc-margin']) document.querySelector(s).style.width = '' }")
            for width in (900, 540, 390, 320):
                page.set_viewport_size({"width": width, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), width
                for selector in (".qc-nav", ".qc-margin"):
                    assert page.locator(selector).evaluate("e => e.scrollWidth <= e.clientWidth + 1"), (selector, width)
                page.get_by_label("Settings", exact=True).click()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), ("settings", width)
                page.get_by_label("Settings", exact=True).click()
            page.screenshot(path=Path(world["root"]).parent / f"track2-mobile-{engine}.png", full_page=True)
        finally:
            browser.close()
