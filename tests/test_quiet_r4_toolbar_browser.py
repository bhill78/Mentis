"""TRACK D (settings strip, pinned toolbar, quick theme, in-content search)
against real Mentis HTTP routes on a disposable fixture Brain.

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


def _a_conversation(world):
    cv, owner = world["cv"], world["who"]["@brian"]
    cid = cv.open_conversation("Quiet toolbar", about="What the strip and search read.")
    cv.join(owner, cid)
    cv.say(cid, owner, [text("A lighthouse on the point, steady in the fog.")])
    cv.say(cid, owner, [text("Nothing of note here.")])
    cv.say(cid, owner, [text("Another lighthouse, further down the coast.")])
    return cid


def _open(page, base, conversation):
    page.goto(base + f"/quiet#/c/{conversation}")
    page.get_by_role("heading", name="Quiet toolbar", exact=True).wait_for()
    page.locator(".qc-post").first.wait_for()


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_the_strip_is_icon_only_and_in_order(world, engine):
    playwright = pytest.importorskip("playwright.sync_api")
    assert (Path(__file__).parents[1] / "apps/fluid-web/dist/index.html").exists()
    conversation = _a_conversation(world)

    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            _open(page, world["base"], conversation)

            # 1. ORDER: Settings, theme, search, pin -- the strip's own DOM
            # order, read directly off .qc-toolbar's children so it cannot
            # be confused with Menu or the brand elsewhere in the header.
            buttons = page.locator(".qc-toolbar > button, .qc-toolbar > .qc-background > button, "
                                    ".qc-toolbar > .qc-search > button")
            labels = buttons.evaluate_all("els => els.map(e => e.getAttribute('aria-label'))")
            assert labels[0] == "Settings"
            assert labels[1].startswith("Theme:")
            assert labels[2] == "Search in this conversation"
            assert labels[3] == "Pin toolbar"

            # 2. ICON-ONLY: no button in the strip carries visible text wider
            # than a single glyph -- none of Settings/theme/search/pin opens
            # a label alongside its icon.
            for i in range(4):
                txt = buttons.nth(i).inner_text().strip()
                assert len(txt) <= 1, f"button {i} ({labels[i]}) is not icon-only: {txt!r}"

            # 3. 32px HIT TARGETS for the three Track D adds (Settings keeps
            # its own existing size).
            for i in (1, 2, 3):
                box = buttons.nth(i).bounding_box()
                assert box["width"] == pytest.approx(32, abs=1)
                assert box["height"] == pytest.approx(32, abs=1)

            assert errors == []
        finally:
            browser.close()


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_the_theme_button_cycles_and_survives_reload(world, engine):
    playwright = pytest.importorskip("playwright.sync_api")
    conversation = _a_conversation(world)

    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            _open(page, world["base"], conversation)

            theme_button = page.get_by_role("button", name="Theme: System", exact=True)
            theme_button.wait_for()
            theme_button.click()
            page.wait_for_function("() => document.documentElement.getAttribute('data-theme') === 'light'")
            page.get_by_role("button", name="Theme: Light", exact=True).wait_for()

            page.get_by_role("button", name="Theme: Light", exact=True).click()
            page.wait_for_function("() => document.documentElement.getAttribute('data-theme') === 'dark'")

            # Persisted the same way the Settings panel's own select is.
            page.reload()
            _open(page, world["base"], conversation)
            assert page.evaluate("document.documentElement.getAttribute('data-theme')") == "dark"
            page.get_by_role("button", name="Theme: Dark", exact=True).wait_for()
            # The Settings panel's own select stays in step with the icon.
            page.get_by_role("button", name="Settings", exact=True).click()
            assert page.get_by_label("Theme", exact=True).input_value() == "dark"
        finally:
            browser.close()


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_pinning_the_toolbar_fixes_it_at_the_right_edge_at_1440_and_persists_but_not_at_390(world, engine):
    playwright = pytest.importorskip("playwright.sync_api")
    conversation = _a_conversation(world)

    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            _open(page, world["base"], conversation)

            toolbar = page.locator(".qc-toolbar")
            assert toolbar.evaluate("el => getComputedStyle(el).position") != "fixed"

            page.get_by_role("button", name="Settings", exact=True).click()
            page.get_by_role("checkbox", name="Pin toolbar", exact=True).check()
            page.wait_for_function(
                "() => getComputedStyle(document.querySelector('.qc-toolbar')).position === 'fixed'")

            # Persisted the same way pinHeader/pinMargins already are.
            page.reload()
            _open(page, world["base"], conversation)
            page.wait_for_function(
                "() => getComputedStyle(document.querySelector('.qc-toolbar')).position === 'fixed'")
            page.get_by_role("button", name="Settings", exact=True).click()
            assert page.get_by_role("checkbox", name="Pin toolbar", exact=True).is_checked()
            page.keyboard.press("Escape")

            # Below 900px the strip folds back into the header: not fixed.
            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_function(
                "() => getComputedStyle(document.querySelector('.qc-toolbar')).position !== 'fixed'")
        finally:
            browser.close()


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_in_content_search_highlights_steps_and_escape_clears(world, engine):
    playwright = pytest.importorskip("playwright.sync_api")
    conversation = _a_conversation(world)

    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            _open(page, world["base"], conversation)

            search_button = page.get_by_role("button", name="Search in this conversation", exact=True)
            search_button.click()
            field = page.get_by_label("Find in this section", exact=True)
            field.wait_for()
            field.fill("lighthouse")

            page.wait_for_function(
                "() => document.querySelector('.fs-count')?.textContent.trim().startsWith('1 of 2')")
            # The matching posts are marked current/hit; the non-matching one dims.
            assert page.locator('.qc-post[data-fs-near], .qc-post[data-fs-hit]').count() >= 1
            dimmed = page.get_by_text("Nothing of note here.").locator("xpath=ancestor::article[contains(@class,'qc-post')]")
            page.wait_for_function(
                "(el) => getComputedStyle(el).opacity !== '1'", arg=dimmed.element_handle())

            field.press("Enter")
            page.wait_for_function(
                "() => document.querySelector('.fs-count')?.textContent.trim().startsWith('2 of 2')")

            page.keyboard.press("Escape")
            assert page.locator(".fs-bar").count() == 0
            page.wait_for_function("() => !document.getElementById('qc-stream')?.hasAttribute('data-fs-on')")
            assert page.locator('.qc-post[data-fs-hit], .qc-post[data-fs-near]').count() == 0
        finally:
            browser.close()


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_ctrl_f_opens_the_same_search(world, engine):
    playwright = pytest.importorskip("playwright.sync_api")
    conversation = _a_conversation(world)

    with playwright.sync_playwright() as p:
        browser = getattr(p, engine).launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            _open(page, world["base"], conversation)
            modifier = "Meta" if engine == "webkit" else "Control"
            page.keyboard.press(f"{modifier}+f")
            page.get_by_label("Find in this section", exact=True).wait_for()
        finally:
            browser.close()
